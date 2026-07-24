from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.models import CalligraphyGlyph
from app.services.path_utils import resolve_resource_path

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageOps = None


PUNCTUATION = set("，。！？；：、,.!?;:《》“”\"'（）()【】[]")
GALLERY_CHARS = "春秋山水月风云书诗礼乐秦汉唐韵雅墨兰竹梅松"
MAX_RENDER_CHARS = 220
DEFAULT_CANVAS_WIDTH = 1100
DEFAULT_CANVAS_HEIGHT = 1600
BACKGROUND_FILENAMES = ("背景.jpg", "background.jpg", "paper.jpg")
TOP_RIGHT_SEAL_FILENAMES = ("引首章_右上.jpg",)
BOTTOM_LEFT_SEAL_FILENAMES = ("压角章_左下.jpg", "压脚章_左下.jpg")


CALLIGRAPHY_TEXT_EXTRACTOR_PROMPT = """你是书法渲染前的文本抽取器，只负责抽取应该写进书法作品的文本。
只返回 JSON，不要解释。
格式：
{"has_work": true, "title": "作品标题或 null", "body": "正文"}
规则：
1. 只抽取题目和正文，不要包含作者、年代、背景、赏析、工具状态或缺字提示。
2. 如果没有可用于书法的正文，返回 {"has_work": false, "title": null, "body": ""}。
3. 不要补全、改写或编造正文。"""


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
    # 书法渲染只需要作品正文；这里会去掉 Markdown、赏析、背景和工具状态等说明性文字。
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result = []
    stop_headers = {"背景", "赏析", "解析", "翻译", "译文", "注释", "说明", "参考链接"}

    for raw_line in text.splitlines():
        line = re.sub(r"[#*_`>]", "", raw_line).strip()
        if not line:
            continue
        header = line.strip("【】[] ：:")
        if header in {"原文", "正文"}:
            continue
        if header in stop_headers:
            break
        if re.search(r"字库缺少|自动留空|calligraphy_render_tool|success", line):
            continue
        line = re.sub(r"^[ \t]*(以下是|这是|题为|标题[:：])", "", line)
        line = re.sub(r"\d{3,4}\s*年?", "", line)
        line = re.sub(r"\d+", "", line)
        line = re.sub(r"[ \t]+", "", line).strip()
        if line:
            result.append(line)

    cleaned = "\n".join(result)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned[:MAX_RENDER_CHARS]


def extract_calligraphy_text_with_llm(text: str) -> str:
    # 优先让模型从长回答中抽取题目和正文；失败时退回规则清洗，保证书法功能仍可用。
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
        if title and not body and _looks_like_title_only_introduction(source, title):
            return ""

        parts = []
        if title:
            parts.append(title if title.startswith("《") and title.endswith("》") else f"《{title.strip('《》')}》")
        if body:
            parts.append(body)
        extracted = clean_calligraphy_text("\n".join(parts))
        if extracted and re.search(r"[\u4e00-\u9fa5]", extracted):
            return extracted
    except Exception:
        pass

    return clean_calligraphy_text(source)


def choose_calligraphy_source(message: str, source_text: str | None) -> str:
    # 如果用户说“把上面的诗生成书法”，前端会把最近助手文本作为 source_text 传入。
    if source_text and source_text.strip():
        return extract_calligraphy_text_with_llm(source_text)

    cleaned = message
    for phrase in [
        "请把",
        "帮我把",
        "把",
        "转成书法",
        "转换成书法",
        "变成书法",
        "写成书法",
        "做成书法",
        "生成书法",
        "书法作品",
        "书法图片",
        "用书法",
        "转书法",
    ]:
        cleaned = cleaned.replace(phrase, "")
    return extract_calligraphy_text_with_llm(cleaned)


def _looks_like_title_only_introduction(source: str, title: str) -> bool:
    title_text = title.strip().strip("《》")
    if not title_text:
        return False
    if not re.search(rf"《?\s*{re.escape(title_text)}\s*》?", source):
        return False
    return bool(
        re.search(
            r"是一首|这首|这阕|介绍|背景|赏析|解析|作者|创作|词中|诗中|全词|表达|展现|如果你|可以",
            source,
        )
    )


def list_calligraphy_styles() -> list[str]:
    with SessionLocal() as db:
        rows = (
            db.query(CalligraphyGlyph.style)
            .distinct()
            .order_by(CalligraphyGlyph.style.asc())
            .all()
        )
    return [row[0] for row in rows if row[0]]


def list_calligraphy_authors(style: str | None = None) -> list[str]:
    with SessionLocal() as db:
        query = db.query(CalligraphyGlyph.author)
        if style:
            query = query.filter(CalligraphyGlyph.style == style)
        rows = query.distinct().order_by(CalligraphyGlyph.author.asc()).all()
    return [row[0] for row in rows if row[0]]


def find_styles_for_author(author: str | None) -> list[str]:
    if not author:
        return []
    with SessionLocal() as db:
        rows = (
            db.query(CalligraphyGlyph.style)
            .filter(CalligraphyGlyph.author == author)
            .distinct()
            .order_by(CalligraphyGlyph.style.asc())
            .all()
        )
    return [row[0] for row in rows if row[0]]


def find_glyph_image(style: str, author: str, char: str) -> Path | None:
    with SessionLocal() as db:
        row = (
            db.query(CalligraphyGlyph)
            .filter(
                CalligraphyGlyph.style == style,
                CalligraphyGlyph.author == author,
                CalligraphyGlyph.character == char,
            )
            .order_by(CalligraphyGlyph.id.asc())
            .first()
        )
    if not row:
        return None
    return resolve_resource_path(get_settings().calligraphy_dataset_dir, row.image_path)


def build_calligraphy_gallery(limit: int = 72) -> list[CalligraphyGalleryItem]:
    items: list[CalligraphyGalleryItem] = []
    seen: set[tuple[str, str, str]] = set()
    with SessionLocal() as db:
        rows = (
            db.query(CalligraphyGlyph)
            .filter(CalligraphyGlyph.character.in_(list(GALLERY_CHARS)))
            .order_by(
                CalligraphyGlyph.style.asc(),
                CalligraphyGlyph.author.asc(),
                CalligraphyGlyph.character.asc(),
            )
            .all()
        )

    for row in rows:
        if len(items) >= limit:
            break
        key = (row.style, row.author, row.character)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            CalligraphyGalleryItem(
                char=row.character,
                style=row.style,
                author=row.author,
                image_url=f"/api/calligraphy-glyph?style={row.style}&author={row.author}&char={row.character}",
                caption=f"{row.style} / {row.author} / {row.character}",
            )
        )
    return items


def render_calligraphy_work(
    db,
    *,
    text: str,
    style: str,
    author: str,
) -> CalligraphyRenderResult:
    # 渲染流程：清洗文本 -> 查字形库 -> 竖排分栏 -> 合成背景、字形和印章 -> 保存 PNG。
    if Image is None or ImageOps is None:
        raise RuntimeError("Calligraphy rendering requires Pillow. Run: pip install Pillow")

    cleaned_text = clean_calligraphy_text(text)
    chars = _iter_render_chars(cleaned_text)
    if not chars:
        raise RuntimeError("No valid text was provided for calligraphy rendering.")

    glyph_paths, missing = _load_glyphs_from_db(chars, style, author)
    columns = _split_columns(cleaned_text)
    if not columns:
        raise RuntimeError("No text is available for layout.")

    width, height = _choose_canvas_size(len(chars))
    canvas = _create_background(width, height)
    _paste_text_columns(canvas, columns, glyph_paths)
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


def _iter_render_chars(text: str) -> list[str]:
    return [char for char in text if char and char not in PUNCTUATION and not char.isspace()]


def _load_glyphs_from_db(chars: list[str], style: str, author: str) -> tuple[dict[str, Path], list[str]]:
    # 字形库以 character/style/author 为查找键；缺字不会阻断渲染，会在结果里返回 missing_chars。
    unique_chars = sorted(set(chars))
    db = SessionLocal()
    try:
        rows = (
            db.query(CalligraphyGlyph)
            .filter(
                CalligraphyGlyph.style == style,
                CalligraphyGlyph.author == author,
                CalligraphyGlyph.character.in_(unique_chars),
            )
            .order_by(CalligraphyGlyph.id.asc())
            .all()
        )
    finally:
        db.close()

    glyph_paths: dict[str, Path] = {}
    settings = get_settings()
    for row in rows:
        glyph_paths.setdefault(
            row.character,
            resolve_resource_path(settings.calligraphy_dataset_dir, row.image_path),
        )

    missing = [char for char in unique_chars if char not in glyph_paths]
    if not rows:
        available_styles = ", ".join(list_calligraphy_styles()[:20]) or "none"
        raise RuntimeError(f"No glyphs found in calligraphy_glyphs. Available styles: {available_styles}")
    return glyph_paths, missing


def _split_columns(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    columns: list[str] = []
    for line in lines or [text]:
        clean_line = "".join(char for char in line if char not in PUNCTUATION and not char.isspace())
        if not clean_line:
            continue
        columns.extend(clean_line[index : index + 14] for index in range(0, len(clean_line), 14))
    return [column for column in columns if column]


def _choose_canvas_size(char_count: int) -> tuple[int, int]:
    if char_count <= 32:
        return 980, 1420
    if char_count <= 90:
        return DEFAULT_CANVAS_WIDTH, DEFAULT_CANVAS_HEIGHT
    if char_count <= 150:
        return 1260, 1780
    return 1420, 2040


def _calligraphy_dataset_root() -> Path:
    return Path(get_settings().calligraphy_dataset_dir).expanduser().resolve()


def _find_asset_file(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = root / name
        if path.exists() and path.is_file():
            return path
    return None


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


def _paste_text_columns(canvas, columns: list[str], glyph_paths: dict[str, Path]) -> None:
    # 中文书法采用从右到左的竖排列布局，列数和格子大小根据画布空间自动收缩。
    width, height = canvas.size
    margin_x = int(width * 0.14)
    margin_top = int(height * 0.12)
    margin_bottom = int(height * 0.14)
    available_width = width - margin_x * 2
    available_height = height - margin_top - margin_bottom
    row_count = max(len(column) for column in columns)
    column_count = len(columns)
    cell_size = int(
        min(
            150,
            available_height / max(1, row_count + 0.18 * max(0, row_count - 1)),
            available_width / max(1, column_count + 0.35 * max(0, column_count - 1)),
        )
    )
    cell_size = max(44, cell_size)
    row_gap = max(6, int(cell_size * 0.12))
    column_gap = max(12, int(cell_size * 0.36))
    text_right = width - margin_x - int(width * 0.08)
    total_height = row_count * cell_size + max(0, row_count - 1) * row_gap
    text_top = margin_top + max(0, (available_height - total_height) // 2)

    for column_index, column in enumerate(columns):
        x = text_right - cell_size - column_index * (cell_size + column_gap)
        for row_index, char in enumerate(column):
            glyph_path = glyph_paths.get(char)
            if not glyph_path:
                continue
            y = text_top + row_index * (cell_size + row_gap)
            _paste_glyph(canvas, glyph_path, x, y, cell_size)


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
