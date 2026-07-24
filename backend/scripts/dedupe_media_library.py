from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


MEDIA_EXTENSIONS = {
    ".mp3": ("audio", "audio/mpeg"),
    ".mp4": ("video", "video/mp4"),
}

INVALID_FILENAME_CHARS = r'<>:"/\|?*'


@dataclass(frozen=True)
class MediaFile:
    source_path: Path
    relative_path: str
    extension: str
    media_kind: str
    media_type: str
    title: str
    title_key: str
    category: str
    collection: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class OutputMedia:
    media: MediaFile
    output_path: Path
    output_relative_path: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate local folk-song mp3/mp4 media files.")
    default_root = os.getenv("MEDIA_LIBRARY_ROOT", "")
    default_output = os.getenv("MEDIA_DEDUP_OUTPUT_DIR", "deduped_media")
    parser.add_argument(
        "--root",
        default=default_root,
        required=not bool(default_root),
        help="Source media root. Defaults to MEDIA_LIBRARY_ROOT when set.",
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help="Output directory. Relative paths are resolved under --root. Defaults to MEDIA_DEDUP_OUTPUT_DIR or ./deduped_media.",
    )
    parser.add_argument("--max-per-kind", type=int, default=1000, help="Maximum files to keep for mp3 and mp4 each.")
    parser.add_argument("--dry-run", action="store_true", help="Scan and write no files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir = output_dir.resolve()

    if not root.exists():
        raise SystemExit(f"Source root does not exist: {root}")
    if output_dir.exists():
        raise SystemExit(f"Output directory already exists, refusing to overwrite: {output_dir}")
    if args.max_per_kind <= 0:
        raise SystemExit("--max-per-kind must be greater than 0")

    all_media = scan_media_files(root, output_dir)
    selected, duplicates = dedupe_by_title(all_media)
    limited, skipped_by_limit = limit_by_kind_and_category(selected, args.max_per_kind)
    planned = plan_output_files(limited, output_dir)

    print(f"Source root: {root}")
    print(f"Output dir: {output_dir}")
    print(f"Scanned media files: {len(all_media)}")
    print(f"Selected after title dedupe: {len(selected)}")
    print(f"Skipped as duplicates: {len(duplicates)}")
    print(f"Skipped by max-per-kind limit: {len(skipped_by_limit)}")
    for extension in sorted(MEDIA_EXTENSIONS):
        count = sum(1 for item in planned if item.media.extension == extension)
        print(f"Planned {extension}: {count}")

    if args.dry_run:
        print("Dry run complete. No files were copied.")
        return

    write_output(planned, output_dir)
    write_manifest(planned, output_dir / "media_manifest.csv")
    write_duplicate_report(duplicates, output_dir / "duplicates_report.csv")
    write_limit_report(skipped_by_limit, output_dir / "limit_skipped_report.csv")
    write_import_sql(planned, output_dir / "media_import.sql")
    print("Done.")


def scan_media_files(root: Path, output_dir: Path) -> list[MediaFile]:
    files: list[MediaFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if is_relative_to(path.resolve(), output_dir):
            continue

        extension = path.suffix.lower()
        if extension not in MEDIA_EXTENSIONS:
            continue

        media_kind, media_type = MEDIA_EXTENSIONS[extension]
        relative_parts = path.relative_to(root).parts
        collection = relative_parts[0] if len(relative_parts) >= 2 else ""
        category = infer_category(relative_parts)
        title = clean_title(path.stem)
        files.append(
            MediaFile(
                source_path=path,
                relative_path=str(path.relative_to(root)),
                extension=extension,
                media_kind=media_kind,
                media_type=media_type,
                title=title,
                title_key=normalize_title_key(title),
                category=category,
                collection=collection,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return files


def infer_category(relative_parts: tuple[str, ...]) -> str:
    if len(relative_parts) >= 3:
        return relative_parts[-2]
    if len(relative_parts) >= 2:
        return relative_parts[0]
    return "uncategorized"


def clean_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?i)\s*(copy|副本|复制)\s*$", "", text)
    text = re.sub(r"[\s_-]*[（(]\d+[）)]$", "", text)
    return text.strip() or "untitled"


def normalize_title_key(value: str) -> str:
    text = clean_title(value).lower()
    text = re.sub(r"[《》【】\[\]（）()“”\"'‘’\s._\-·,，。:：;；!！?？]+", "", text)
    return text or "untitled"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dedupe_by_title(files: list[MediaFile]) -> tuple[list[MediaFile], list[tuple[MediaFile, MediaFile]]]:
    groups: dict[tuple[str, str], list[MediaFile]] = defaultdict(list)
    for item in files:
        groups[(item.extension, item.title_key)].append(item)

    selected: list[MediaFile] = []
    duplicates: list[tuple[MediaFile, MediaFile]] = []
    for items in groups.values():
        winner = choose_best(items)
        selected.append(winner)
        for item in items:
            if item != winner:
                duplicates.append((winner, item))
    return sorted(selected, key=sort_key), sorted(duplicates, key=lambda pair: sort_key(pair[1]))


def choose_best(items: list[MediaFile]) -> MediaFile:
    return sorted(
        items,
        key=lambda item: (
            -item.size_bytes,
            item.category,
            item.collection,
            item.relative_path.lower(),
        ),
    )[0]


def limit_by_kind_and_category(files: list[MediaFile], max_per_kind: int) -> tuple[list[MediaFile], list[MediaFile]]:
    kept: list[MediaFile] = []
    skipped: list[MediaFile] = []

    for extension in sorted(MEDIA_EXTENSIONS):
        items = [item for item in files if item.extension == extension]
        limited = select_balanced_by_category(items, max_per_kind)
        limited_set = set(limited)
        kept.extend(limited)
        skipped.extend(item for item in items if item not in limited_set)

    return sorted(kept, key=sort_key), sorted(skipped, key=sort_key)


def select_balanced_by_category(items: list[MediaFile], limit: int) -> list[MediaFile]:
    by_category: dict[str, list[MediaFile]] = defaultdict(list)
    for item in sorted(items, key=sort_key):
        by_category[item.category].append(item)

    selected: list[MediaFile] = []
    categories = sorted(by_category)
    while len(selected) < limit:
        added = False
        for category in categories:
            if by_category[category]:
                selected.append(by_category[category].pop(0))
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
    return selected


def plan_output_files(files: list[MediaFile], output_dir: Path) -> list[OutputMedia]:
    planned: list[OutputMedia] = []
    used_names: set[str] = set()
    counters = defaultdict(int)

    for item in sorted(files, key=sort_key):
        counters[item.extension] += 1
        type_dir = "mp3" if item.extension == ".mp3" else "mp4"
        safe_title = safe_filename(item.title)[:90]
        filename = f"{counters[item.extension]:04d}_{safe_title}{item.extension}"
        filename = unique_filename(filename, used_names)
        output_path = output_dir / type_dir / filename
        planned.append(
            OutputMedia(
                media=item,
                output_path=output_path,
                output_relative_path=str(Path(type_dir) / filename).replace("\\", "/"),
            )
        )
    return planned


def safe_filename(value: str) -> str:
    text = "".join("_" if char in INVALID_FILENAME_CHARS else char for char in value)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or "untitled"


def unique_filename(filename: str, used_names: set[str]) -> str:
    if filename.lower() not in used_names:
        used_names.add(filename.lower())
        return filename

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while True:
        candidate = f"{stem}_{index}{suffix}"
        if candidate.lower() not in used_names:
            used_names.add(candidate.lower())
            return candidate
        index += 1


def write_output(planned: list[OutputMedia], output_dir: Path) -> None:
    (output_dir / "mp3").mkdir(parents=True, exist_ok=False)
    (output_dir / "mp4").mkdir(parents=True, exist_ok=False)
    for item in planned:
        shutil.copy2(item.media.source_path, item.output_path)


def write_manifest(planned: list[OutputMedia], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "id",
                "title",
                "category",
                "media_kind",
                "media_type",
                "extension",
                "file_name",
                "deduped_relative_path",
                "deduped_path",
                "source_path",
                "source_relative_path",
                "size_bytes",
                "sha256",
            ]
        )
        for index, item in enumerate(planned, start=1):
            media = item.media
            writer.writerow(
                [
                    index,
                    media.title,
                    media.category,
                    media.media_kind,
                    media.media_type,
                    media.extension,
                    item.output_path.name,
                    item.output_relative_path,
                    str(item.output_path),
                    str(media.source_path),
                    media.relative_path,
                    media.size_bytes,
                    media.sha256,
                ]
            )


def write_duplicate_report(duplicates: list[tuple[MediaFile, MediaFile]], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "extension", "kept_path", "duplicate_path", "kept_sha256", "duplicate_sha256"])
        for kept, duplicate in duplicates:
            writer.writerow(
                [
                    duplicate.title,
                    duplicate.extension,
                    str(kept.source_path),
                    str(duplicate.source_path),
                    kept.sha256,
                    duplicate.sha256,
                ]
            )


def write_limit_report(skipped: list[MediaFile], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["title", "category", "media_kind", "source_path", "size_bytes", "sha256"])
        for item in skipped:
            writer.writerow([item.title, item.category, item.media_kind, str(item.source_path), item.size_bytes, item.sha256])


def write_import_sql(planned: list[OutputMedia], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("CREATE DATABASE IF NOT EXISTS culture_video_agent DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n")
        handle.write("USE culture_video_agent;\n\n")
        handle.write(
            "CREATE TABLE IF NOT EXISTS media_resources (\n"
            "  id INT AUTO_INCREMENT PRIMARY KEY,\n"
            "  title VARCHAR(255) NOT NULL,\n"
            "  category VARCHAR(100) NULL,\n"
            "  media_kind VARCHAR(20) NOT NULL,\n"
            "  media_type VARCHAR(100) NOT NULL,\n"
            "  file_name VARCHAR(255) NOT NULL,\n"
            "  file_path VARCHAR(700) NOT NULL,\n"
            "  source_path VARCHAR(700) NULL,\n"
            "  size_bytes BIGINT NOT NULL,\n"
            "  sha256 CHAR(64) NOT NULL,\n"
            "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n"
            "  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n"
            "  UNIQUE KEY uk_media_sha256_kind (sha256, media_kind),\n"
            "  INDEX idx_media_title (title),\n"
            "  INDEX idx_media_category_kind (category, media_kind)\n"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n\n"
        )
        handle.write("TRUNCATE TABLE media_resources;\n\n")
        handle.write(
            "INSERT INTO media_resources "
            "(title, category, media_kind, media_type, file_name, file_path, source_path, size_bytes, sha256) VALUES\n"
        )
        rows = []
        for item in planned:
            media = item.media
            rows.append(
                "("
                f"{sql_quote(media.title)}, "
                f"{sql_quote(media.category)}, "
                f"{sql_quote(media.media_kind)}, "
                f"{sql_quote(media.media_type)}, "
                f"{sql_quote(item.output_path.name)}, "
                f"{sql_quote(str(item.output_path))}, "
                f"{sql_quote(str(media.source_path))}, "
                f"{media.size_bytes}, "
                f"{sql_quote(media.sha256)}"
                ")"
            )
        handle.write(",\n".join(rows))
        handle.write(";\n")


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sort_key(item: MediaFile) -> tuple[str, str, str, str]:
    return (item.extension, item.category, item.title_key, item.relative_path.lower())


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
