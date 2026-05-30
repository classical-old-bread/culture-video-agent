from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings


try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - handled at runtime with a clear message.
    Image = None
    ImageOps = None


PUNCTUATION = set("，。！？；：、,.!?;:《》“”\"'（）()【】[]")
DEFAULT_CANVAS_WIDTH = 1100
DEFAULT_CANVAS_HEIGHT = 1600
MIN_CELL_SIZE = 44
MAX_CELL_SIZE = 170
MAX_CHARS_PER_COLUMN = 14
MAX_RENDER_CHARS = 220
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
BACKGROUND_FILENAMES = ("背景.jpg", "background.jpg", "paper.jpg")
TOP_RIGHT_SEAL_FILENAMES = ("引首章_右上.jpg", "引首章右上.jpg")
BOTTOM_LEFT_SEAL_FILENAMES = ("压脚章_左下.jpg", "压角章_左下.jpg", "压脚章左下.jpg", "压角章左下.jpg")
GALLERY_CHARS = "春秋山水月风云书诗礼乐秦汉唐韵雅墨兰竹梅松"
CALLIGRAPHY_TEXT_EXTRACTOR_PROMPT = """你是书法渲染前的文本抽取器，只负责从输入中抽取应该写进书法作品的文本。
返回 JSON，不要输出解释。

JSON 格式：
{
  "has_work": true,
  "title": "作品题目或 null",
  "body": "正文，保留原有分行"
}

规则：
1. 只抽取题目和正文，不要包含作者、朝代、年份、背景、赏析、解释、参考链接、工具状态或缺字提示。
2. 如果输入包含【原文】、原文、正文等作品区块，只使用该区块中的作品内容。
3. 如果输入是“把这首诗生成书法”这类指令，需要结合输入里的上下文抽取上一段作品；没有正文就返回 has_work=false。
4. 如果输入本身就是用户直接提供的短句或正文，把它作为 body。
5. 不要补全、改写或编造正文。
"""


@dataclass
class CalligraphyRenderResult:
    image_url: str
    style: str
    author: str
    text: str
    missing_chars: list[str]


@dataclass
class CalligraphyGalleryItem:
    char: str
    style: str
    author: str
    image_url: str
    caption: str


def clean_calligraphy_text(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    seen_title = False
    skipped_author = False
    raw_lines = text.splitlines()
    for index, raw_line in enumerate(raw_lines):
        line = re.sub(r"[#*_`>]", "", raw_line).strip()
        if not line:
            continue
        if re.fullmatch(r"[-—_~]{2,}", line):
            continue
        if re.fullmatch(r"【?(原文|正文)】?[:：]?", line):
            continue
        if re.fullmatch(r"【?(背景|赏析|简析|解析|翻译|译文|注释|说明|创作背景|文化背景|相关知识|参考链接|可用于书法生成的说明)】?[:：]?", line):
            break
        if re.match(r"^(这首|这阕|本诗|本词|如果|或者|还可以|您可以|我可以|赏析|说明|解释|简析|背景|创作背景)", line):
            break
        if re.search(r"字库缺少|自动留空|calligraphy_render_tool|success", line):
            continue
        if re.fullmatch(r"[\d\s、,，.。:：;；-]+", line):
            continue
        had_year = bool(re.search(r"[（(]?\s*\d{3,4}\s*年", line))
        line = re.sub(r"[（(]\s*\d{3,4}\s*年?\s*[）)]", "", line)
        line = re.sub(r"\d{3,4}\s*年", "", line)
        line = re.sub(r"\d+", "", line)
        line = re.sub(r"^[ \t]*(以下是|这是|题为|标题[:：])", "", line)
        has_author_label = bool(re.match(r"^(作者|词作者|诗人|作者简介)[:：]\s*", line))
        author_candidate = re.sub(r"^(作者|词作者|诗人|作者简介)[:：]\s*", "", line).strip()
        if (
            seen_title
            and not skipped_author
            and (has_author_label or had_year)
            and re.fullmatch(r"[\u4e00-\u9fa5·]{2,12}", author_candidate)
        ):
            skipped_author = True
            continue
        line = re.sub(r"[ \t]+", "", line).strip()
        if line and line != "年":
            lines.append(line)
            if re.fullmatch(r"《[^》]{1,30}》", line):
                seen_title = True
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_RENDER_CHARS]


def extract_calligraphy_text_with_llm(text: str) -> str:
    source = text.strip()
    if not source:
        return ""

    try:
        from app.agent.llm import invoke_agent_llm, parse_json_object

        raw = invoke_agent_llm(
            CALLIGRAPHY_TEXT_EXTRACTOR_PROMPT,
            f"输入文本：\n{source[:6000]}",
            temperature=0,
        )
        data = parse_json_object(raw)
        if data.get("has_work") is False:
            return ""

        title = str(data.get("title") or "").strip()
        body = data.get("body") or ""
        if isinstance(body, list):
            body = "\n".join(str(item).strip() for item in body if str(item).strip())
        body = str(body).strip()
        if not body and not title:
            return ""

        parts = []
        if title:
            title = title if title.startswith("《") and title.endswith("》") else f"《{title.strip('《》')}》"
            parts.append(title)
        if body:
            parts.append(body)
        extracted = clean_calligraphy_text("\n".join(parts))
        if extracted and re.search(r"[\u4e00-\u9fa5]", extracted):
            return extracted
    except Exception:
        pass

    return clean_calligraphy_text(source)


def choose_calligraphy_source(message: str, source_text: str | None) -> str:
    if source_text and source_text.strip():
        return extract_calligraphy_text_with_llm(source_text)

    cleaned = message
    for phrase in [
        "请把", "帮我把", "把", "转成书法", "转换成书法", "变成书法", "写成书法",
        "做成书法", "生成书法", "书法作品", "书法图片", "用书法", "转书法",
    ]:
        cleaned = cleaned.replace(phrase, "")
    return extract_calligraphy_text_with_llm(cleaned)


def _iter_render_chars(text: str) -> list[str]:
    return [char for char in text if char and char not in PUNCTUATION and not char.isspace()]


def _calligraphy_dataset_root() -> Path:
    return Path(get_settings().calligraphy_dataset_dir).expanduser().resolve()


def _list_child_dirs(path: Path) -> list[str]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(child.name for child in path.iterdir() if child.is_dir())


def list_calligraphy_styles() -> list[str]:
    return _list_child_dirs(_calligraphy_dataset_root())


def list_calligraphy_authors(style: str | None = None) -> list[str]:
    root = _calligraphy_dataset_root()
    if style:
        style_dir = _find_child_dir(root, style)
        return _list_child_dirs(style_dir) if style_dir else []

    authors: set[str] = set()
    for style_name in list_calligraphy_styles():
        authors.update(_list_child_dirs(root / style_name))
    return sorted(authors)


def find_styles_for_author(author: str | None) -> list[str]:
    if not author:
        return []

    matched_styles = []
    normalized_author = author.casefold()
    for style_name in list_calligraphy_styles():
        if any(item.casefold() == normalized_author for item in list_calligraphy_authors(style_name)):
            matched_styles.append(style_name)
    return matched_styles


def build_calligraphy_selection_prompt(style: str | None, author: str | None) -> str:
    styles = list_calligraphy_styles()
    grouped_options = []
    for style_name in styles:
        authors = list_calligraphy_authors(style_name)
        if authors:
            grouped_options.append(f"{style_name}：{'、'.join(authors)}")

    style_text = "、".join(styles[:20]) if styles else "未检测到风格目录，请先配置 CALLIGRAPHY_DATASET_DIR"
    option_text = "\n".join(grouped_options) if grouped_options else "未检测到作者目录"

    if not style and not author:
        return f"生成书法前需要先选择风格和作者。\n当前可选风格：\n{option_text}"
    if not style:
        return f"生成书法前还需要选择书法风格。当前可选风格：{style_text}。"
    authors = list_calligraphy_authors(style)
    author_text = "、".join(authors[:30]) if authors else "未检测到作者目录"
    return f"生成书法前还需要选择作者。当前 {style} 可选作者：{author_text}。"


def _find_child_dir(parent: Path, name: str | None) -> Path | None:
    if not name or not parent.exists() or not parent.is_dir():
        return None

    normalized_name = name.casefold()
    for child in parent.iterdir():
        if child.is_dir() and child.name.casefold() == normalized_name:
            return child
    return None


def _gb2312_filename_stems(char: str) -> set[str]:
    encoded = char.encode("gb2312")
    upper_hex = encoded.hex().upper()
    lower_hex = upper_hex.lower()
    return {
        upper_hex,
        lower_hex,
        f"0x{lower_hex}",
        f"0X{upper_hex}",
        "%".join([upper_hex[index:index + 2] for index in range(0, len(upper_hex), 2)]),
        "%".join([lower_hex[index:index + 2] for index in range(0, len(lower_hex), 2)]),
        "_".join([upper_hex[index:index + 2] for index in range(0, len(upper_hex), 2)]),
        "_".join([lower_hex[index:index + 2] for index in range(0, len(lower_hex), 2)]),
        "-".join([upper_hex[index:index + 2] for index in range(0, len(upper_hex), 2)]),
        "-".join([lower_hex[index:index + 2] for index in range(0, len(lower_hex), 2)]),
    }


@lru_cache(maxsize=32)
def _glyph_index(author_dir: str) -> dict[str, Path]:
    directory = Path(author_dir)
    if not directory.exists() or not directory.is_dir():
        return {}

    return {
        image_path.stem.casefold(): image_path
        for image_path in directory.iterdir()
        if image_path.is_file() and image_path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    }


def _find_glyph_image(author_dir: Path, char: str) -> Path | None:
    try:
        candidate_stems = {stem.casefold() for stem in _gb2312_filename_stems(char)}
    except UnicodeEncodeError:
        return None

    indexed_paths = _glyph_index(str(author_dir))
    for stem in candidate_stems:
        image_path = indexed_paths.get(stem)
        if image_path:
            return image_path
    return None


def find_glyph_image(style: str, author: str, char: str) -> Path | None:
    root = _calligraphy_dataset_root()
    style_dir = _find_child_dir(root, style)
    if not style_dir:
        return None

    author_dir = _find_child_dir(style_dir, author)
    if not author_dir:
        return None

    return _find_glyph_image(author_dir, char)


def build_calligraphy_gallery(limit: int = 72) -> list[CalligraphyGalleryItem]:
    root = _calligraphy_dataset_root()
    if not root.exists() or not root.is_dir():
        return []

    items: list[CalligraphyGalleryItem] = []
    seen: set[tuple[str, str, str]] = set()
    styles = list_calligraphy_styles()

    for style in styles:
        for author in list_calligraphy_authors(style):
            for char in GALLERY_CHARS:
                if len(items) >= limit:
                    return items
                key = (style, author, char)
                if key in seen:
                    continue
                if find_glyph_image(style, author, char):
                    seen.add(key)
                    items.append(
                        CalligraphyGalleryItem(
                            char=char,
                            style=style,
                            author=author,
                            image_url=(
                                f"/api/calligraphy-glyph?"
                                f"style={style}&author={author}&char={char}"
                            ),
                            caption=f"{style} · {author} · {char}",
                        )
                    )

    return items


def _load_glyphs_from_dataset(chars: list[str], style: str, author: str) -> tuple[dict[str, Path], list[str]]:
    root = _calligraphy_dataset_root()
    if not root.exists():
        raise RuntimeError(f"书法数据集目录不存在：{root}。请在 backend/.env 配置 CALLIGRAPHY_DATASET_DIR。")

    style_dir = _find_child_dir(root, style)
    if not style_dir:
        available = "、".join(list_calligraphy_styles()[:20]) or "无"
        raise RuntimeError(f"未找到书法风格目录：{style}。当前可选风格：{available}")

    author_dir = _find_child_dir(style_dir, author)
    if not author_dir:
        available = "、".join(list_calligraphy_authors(style)[:30]) or "无"
        raise RuntimeError(f"未找到 {style} 下的作者目录：{author}。当前可选作者：{available}")

    glyph_paths: dict[str, Path] = {}
    missing: list[str] = []
    for char in sorted(set(chars)):
        glyph_path = _find_glyph_image(author_dir, char)
        if glyph_path:
            glyph_paths[char] = glyph_path
        else:
            missing.append(char)
    return glyph_paths, missing


def _split_columns(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        compact = "".join(char for char in text if char not in PUNCTUATION and not char.isspace())
        lines = [
            compact[index:index + MAX_CHARS_PER_COLUMN]
            for index in range(0, len(compact), MAX_CHARS_PER_COLUMN)
        ]

    columns: list[str] = []
    for line in lines:
        clean_line = "".join(char for char in line if char not in PUNCTUATION and not char.isspace())
        if not clean_line:
            continue
        if len(clean_line) <= MAX_CHARS_PER_COLUMN:
            columns.append(clean_line)
        else:
            columns.extend(
                clean_line[index:index + MAX_CHARS_PER_COLUMN]
                for index in range(0, len(clean_line), MAX_CHARS_PER_COLUMN)
            )
    return columns


def _find_asset_file(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            return path
    return None


def _white_to_transparency(image, threshold: int = 244):
    rgba = image.convert("RGBA")
    pixels = []
    for red, green, blue, alpha in rgba.getdata():
        if red >= threshold and green >= threshold and blue >= threshold:
            pixels.append((red, green, blue, 0))
        else:
            pixels.append((red, green, blue, alpha))
    rgba.putdata(pixels)
    return rgba


def _trim_transparent(image):
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    return image.crop(bbox) if bbox else image


def _create_background(width: int, height: int):
    root = _calligraphy_dataset_root()
    background_path = _find_asset_file(root, BACKGROUND_FILENAMES)
    if not background_path:
        return Image.new("RGBA", (width, height), (247, 240, 222, 255))

    texture = Image.open(background_path).convert("RGB")
    canvas = Image.new("RGB", (width, height))
    for y in range(0, height, texture.height):
        for x in range(0, width, texture.width):
            canvas.paste(texture, (x, y))
    return canvas.convert("RGBA")


def _prepare_overlay(path: Path, max_size: tuple[int, int]):
    overlay = _white_to_transparency(Image.open(path))
    overlay = _trim_transparent(overlay)
    return ImageOps.contain(overlay, max_size, method=Image.Resampling.LANCZOS)


def _paste_seals(canvas) -> None:
    root = _calligraphy_dataset_root()
    width, height = canvas.size
    margin = max(28, int(min(width, height) * 0.035))

    top_right_path = _find_asset_file(root, TOP_RIGHT_SEAL_FILENAMES)
    if top_right_path:
        seal = _prepare_overlay(top_right_path, (int(width * 0.12), int(height * 0.23)))
        canvas.alpha_composite(seal, (width - margin - seal.width, margin))

    bottom_left_path = _find_asset_file(root, BOTTOM_LEFT_SEAL_FILENAMES)
    if bottom_left_path:
        seal_size = int(min(width, height) * 0.14)
        seal = _prepare_overlay(bottom_left_path, (seal_size, seal_size))
        canvas.alpha_composite(seal, (margin, height - margin - seal.height))


def _clean_column_text(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        clean_line = "".join(char for char in line if char not in PUNCTUATION and not char.isspace())
        if clean_line:
            lines.append(clean_line)
    if lines:
        return lines

    compact = "".join(char for char in text if char not in PUNCTUATION and not char.isspace())
    return [compact] if compact else []


def _split_columns_for_rows(text: str, rows: int) -> list[str]:
    columns = []
    for line in _clean_column_text(text):
        columns.extend(line[index:index + rows] for index in range(0, len(line), rows))
    return [column for column in columns if column]


def _choose_canvas_size(char_count: int) -> tuple[int, int]:
    if char_count <= 32:
        return 980, 1420
    if char_count <= 90:
        return DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT
    if char_count <= 150:
        return 1260, 1780
    return 1420, 2040


def _choose_layout(text: str, char_count: int) -> dict:
    width, height = _choose_canvas_size(char_count)
    margin_x = int(width * 0.14)
    margin_top = int(height * 0.12)
    margin_bottom = int(height * 0.14)
    text_left = margin_x
    text_right = width - margin_x - int(width * 0.08)
    text_top = margin_top
    text_bottom = height - margin_bottom
    available_width = max(1, text_right - text_left)
    available_height = max(1, text_bottom - text_top)

    if char_count <= 8:
        max_cell_size = 118
        row_gap_ratio = 0.72
        column_gap_ratio = 0.95
    elif char_count <= 16:
        max_cell_size = 128
        row_gap_ratio = 0.52
        column_gap_ratio = 0.78
    elif char_count <= 32:
        max_cell_size = 145
        row_gap_ratio = 0.32
        column_gap_ratio = 0.58
    elif char_count <= 90:
        max_cell_size = MAX_CELL_SIZE
        row_gap_ratio = 0.14
        column_gap_ratio = 0.36
    else:
        max_cell_size = MAX_CELL_SIZE
        row_gap_ratio = 0.08
        column_gap_ratio = 0.32

    max_rows = min(max(4, char_count), 26)
    if char_count <= 10:
        row_candidates = [max(1, char_count)]
    else:
        row_candidates = range(3, max_rows + 1)
    best_layout = None
    for rows in row_candidates:
        columns = _split_columns_for_rows(text, rows)
        if not columns:
            continue

        row_count = max(len(column) for column in columns)
        column_count = len(columns)
        cell_by_height = available_height / (row_count + row_gap_ratio * max(0, row_count - 1))
        cell_by_width = available_width / (column_count + column_gap_ratio * max(0, column_count - 1))
        cell_size = int(min(cell_by_height, cell_by_width, max_cell_size))
        if cell_size < MIN_CELL_SIZE:
            continue

        row_gap = max(6, int(cell_size * row_gap_ratio))
        column_gap = max(12, int(cell_size * column_gap_ratio))
        total_text_height = row_count * cell_size + max(0, row_count - 1) * row_gap
        score = cell_size - column_count * 0.08
        if best_layout is None or score > best_layout["score"]:
            best_layout = {
                "score": score,
                "columns": columns,
                "cell_size": cell_size,
                "row_gap": row_gap,
                "column_gap": column_gap,
                "text_left": text_left,
                "text_right": text_right,
                "text_top": text_top + max(0, (available_height - total_text_height) // 2),
                "width": width,
                "height": height,
            }

    if best_layout:
        return best_layout

    columns = _split_columns_for_rows(text, max_rows) or _split_columns(text)
    return {
        "score": 0,
        "columns": columns,
        "cell_size": MIN_CELL_SIZE,
        "row_gap": 4,
        "column_gap": 10,
        "text_left": text_left,
        "text_right": text_right,
        "text_top": text_top,
        "width": width,
        "height": height,
    }


def _paste_glyph(canvas, glyph_path: Path, x: int, y: int, cell_size: int) -> None:
    glyph = Image.open(glyph_path).convert("RGBA")
    glyph = _white_to_transparency(glyph)
    glyph = _trim_transparent(glyph)
    glyph = ImageOps.contain(
        glyph,
        (cell_size, cell_size),
        method=Image.Resampling.LANCZOS,
    )
    offset_x = x + (cell_size - glyph.width) // 2
    offset_y = y + (cell_size - glyph.height) // 2
    canvas.alpha_composite(glyph, (offset_x, offset_y))


def render_calligraphy_work(
    db,
    *,
    text: str,
    style: str,
    author: str,
) -> CalligraphyRenderResult:
    if Image is None or ImageOps is None:
        raise RuntimeError("书法图片拼接需要 Pillow，请先执行：pip install Pillow")

    cleaned_text = clean_calligraphy_text(text)
    chars = _iter_render_chars(cleaned_text)
    if not chars:
        raise RuntimeError("没有可用于生成书法的文字，请先生成或输入古诗、宋词、对联等内容。")

    glyph_paths, missing = _load_glyphs_from_dataset(chars, style, author)
    layout = _choose_layout(cleaned_text, len(chars))
    if not layout["columns"]:
        raise RuntimeError("没有可用于排版的文字。")

    canvas = _create_background(layout["width"], layout["height"])
    cell_size = layout["cell_size"]
    row_gap = layout["row_gap"]
    column_gap = layout["column_gap"]

    for column_index, column in enumerate(layout["columns"]):
        x = layout["text_right"] - cell_size - column_index * (cell_size + column_gap)
        for row_index, char in enumerate(column):
            glyph_path = glyph_paths.get(char)
            if not glyph_path:
                continue
            y = layout["text_top"] + row_index * (cell_size + row_gap)
            _paste_glyph(canvas, glyph_path, x, y, cell_size)

    _paste_seals(canvas)

    settings = get_settings()
    output_dir = Path(settings.calligraphy_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.png"
    output_path = output_dir / filename
    canvas.convert("RGB").save(output_path, "PNG")

    return CalligraphyRenderResult(
        image_url=f"/api/calligraphy/{filename}",
        style=style,
        author=author,
        text=cleaned_text,
        missing_chars=missing,
    )
