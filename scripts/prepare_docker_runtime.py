from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_REPLACEMENTS = (
    ("F:\\\\fonts\\\\", ""),
    ("F:/fonts/", ""),
    ("F:\\\\shanbei_videos\\\\deduped_media\\\\", ""),
    ("F:/shanbei_videos/deduped_media/", ""),
    ("F:\\\\shanbei_videos\\\\", ""),
    ("F:/shanbei_videos/", ""),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Docker runtime files and rewrite exported SQL paths to relative paths."
    )
    parser.add_argument(
        "--sql-source",
        default="deploy/mysql/original-export.sql",
        help="Original SQL exported from Navicat.",
    )
    parser.add_argument(
        "--sql-target",
        default="deploy/mysql/01-init.sql",
        help="Output SQL with relative file paths.",
    )
    parser.add_argument(
        "--fonts-source",
        default="F:/fonts",
        help="Original calligraphy font directory.",
    )
    parser.add_argument(
        "--media-source",
        default="F:/shanbei_videos/deduped_media",
        help="Original deduplicated media directory.",
    )
    parser.add_argument(
        "--fonts-target",
        default="runtime/calligraphy_fonts",
        help="Docker runtime calligraphy font directory.",
    )
    parser.add_argument(
        "--media-target",
        default="runtime/media",
        help="Docker runtime media directory.",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Only rewrite the SQL file; do not copy media/font assets.",
    )
    return parser.parse_args()


def rewrite_sql_paths(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"SQL source does not exist: {source}")

    sql = source.read_text(encoding="utf-8")

    for old, new in DEFAULT_REPLACEMENTS:
        sql = sql.replace(old, new)

    # Navicat exports Windows paths as escaped backslashes in SQL strings.
    # After removing fixed drive roots, normalize the rest to portable slash paths.
    sql = sql.replace("\\\\", "/")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sql, encoding="utf-8", newline="")


def copy_directory_contents(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {source}")

    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)


def count_files(path: Path) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file())


def main() -> None:
    args = parse_args()

    sql_source = Path(args.sql_source)
    sql_target = Path(args.sql_target)
    fonts_source = Path(args.fonts_source)
    media_source = Path(args.media_source)
    fonts_target = Path(args.fonts_target)
    media_target = Path(args.media_target)

    print(f"Rewriting SQL paths: {sql_source} -> {sql_target}")
    rewrite_sql_paths(sql_source, sql_target)

    if args.skip_copy:
        print("Skipped asset copy.")
        return

    print(f"Copying calligraphy assets: {fonts_source} -> {fonts_target}")
    copy_directory_contents(fonts_source, fonts_target)

    print(f"Copying media assets: {media_source} -> {media_target}")
    copy_directory_contents(media_source, media_target)

    print("Done.")
    print(f"Calligraphy files: {count_files(fonts_target)}")
    print(f"Media files: {count_files(media_target)}")


if __name__ == "__main__":
    main()

