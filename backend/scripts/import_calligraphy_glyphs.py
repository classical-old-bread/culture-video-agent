from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build SQL/CSV metadata for calligraphy glyph images.")
    default_root = os.getenv("CALLIGRAPHY_DATASET_DIR", "")
    default_output_dir = os.getenv("CALLIGRAPHY_IMPORT_OUTPUT_DIR", "calligraphy_db_import")
    parser.add_argument(
        "--root",
        default=default_root,
        required=not bool(default_root),
        help="Calligraphy dataset root. Defaults to CALLIGRAPHY_DATASET_DIR when set.",
    )
    parser.add_argument(
        "--output-dir",
        default=default_output_dir,
        help="Directory for generated SQL and CSV files. Defaults to CALLIGRAPHY_IMPORT_OUTPUT_DIR or ./calligraphy_db_import.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir = output_dir.resolve()

    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Calligraphy dataset root does not exist: {root}")

    rows = scan_glyphs(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "calligraphy_glyphs_manifest.csv"
    sql_path = output_dir / "calligraphy_glyphs_import.sql"
    write_manifest(rows, csv_path)
    write_import_sql(rows, sql_path)

    print(f"Root: {root}")
    print(f"Glyph rows: {len(rows)}")
    print(f"CSV: {csv_path}")
    print(f"SQL: {sql_path}")


def scan_glyphs(root: Path) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, str, str, str]] = set()

    for style_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
        for author_dir in sorted((item for item in style_dir.iterdir() if item.is_dir()), key=lambda item: item.name):
            for image_path in sorted(author_dir.iterdir(), key=lambda item: item.name):
                if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
                    continue

                character = character_from_filename(image_path.stem)
                if not character:
                    continue

                key = (character, style_dir.name, author_dir.name, str(image_path))
                if key in seen:
                    continue
                seen.add(key)

                width, height = image_size(image_path)
                rows.append(
                    {
                        "character": character,
                        "style": style_dir.name,
                        "author": author_dir.name,
                        "image_path": str(image_path),
                        "width": width,
                        "height": height,
                    }
                )

    return rows


def character_from_filename(stem: str) -> str | None:
    normalized = stem.strip()
    if len(normalized) == 1 and "\u4e00" <= normalized <= "\u9fff":
        return normalized

    compact = (
        normalized.removeprefix("0x")
        .removeprefix("0X")
        .replace("%", "")
        .replace("_", "")
        .replace("-", "")
        .strip()
    )
    if len(compact) == 4 and all(char in "0123456789abcdefABCDEF" for char in compact):
        try:
            decoded = bytes.fromhex(compact).decode("gb2312")
        except (UnicodeDecodeError, ValueError):
            return None
        if len(decoded) == 1 and "\u4e00" <= decoded <= "\u9fff":
            return decoded
    return None


def image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.width, image.height
    except Exception:
        return None, None


def write_manifest(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["character", "style", "author", "image_path", "width", "height"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_import_sql(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("CREATE DATABASE IF NOT EXISTS culture_video_agent DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n")
        handle.write("USE culture_video_agent;\n\n")
        handle.write(
            "CREATE TABLE IF NOT EXISTS calligraphy_glyphs (\n"
            "  id INT AUTO_INCREMENT PRIMARY KEY,\n"
            "  `character` VARCHAR(16) NOT NULL,\n"
            "  style VARCHAR(64) NOT NULL,\n"
            "  author VARCHAR(64) NOT NULL,\n"
            "  image_path VARCHAR(700) NOT NULL,\n"
            "  width INT NULL,\n"
            "  height INT NULL,\n"
            "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,\n"
            "  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n"
            "  UNIQUE KEY uk_calligraphy_glyph (`character`, style, author),\n"
            "  INDEX idx_calligraphy_lookup (`character`, style, author),\n"
            "  INDEX idx_calligraphy_style_author (style, author)\n"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n\n"
        )
        handle.write("TRUNCATE TABLE calligraphy_glyphs;\n\n")
        if not rows:
            return
        batch_size = 500
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            handle.write(
                "INSERT IGNORE INTO calligraphy_glyphs "
                "(`character`, style, author, image_path, width, height) VALUES\n"
            )
            values = [
                "("
                f"{sql_quote(row['character'])}, "
                f"{sql_quote(row['style'])}, "
                f"{sql_quote(row['author'])}, "
                f"{sql_quote(row['image_path'])}, "
                f"{sql_int(row['width'])}, "
                f"{sql_int(row['height'])}"
                ")"
                for row in batch
            ]
            handle.write(",\n".join(values))
            handle.write(";\n\n")


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_int(value: int | None) -> str:
    return "NULL" if value is None else str(int(value))


if __name__ == "__main__":
    main()
