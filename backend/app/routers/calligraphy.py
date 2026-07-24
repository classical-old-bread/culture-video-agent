from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.calligraphy_service import build_calligraphy_gallery, find_glyph_image


router = APIRouter(prefix="/api", tags=["calligraphy"])


@router.get("/calligraphy/{filename}")
def get_calligraphy_image(filename: str):
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名。")

    output_dir = Path(get_settings().calligraphy_output_dir).resolve()
    image_path = (output_dir / filename).resolve()
    if output_dir not in image_path.parents:
        raise HTTPException(status_code=400, detail="非法文件路径。")
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="书法作品不存在或已被清理。")

    return FileResponse(path=str(image_path), media_type="image/png", filename=filename)


@router.get("/calligraphy-gallery")
def get_calligraphy_gallery() -> dict:
    items = build_calligraphy_gallery()
    return {
        "items": [
            {
                "char": item.char,
                "style": item.style,
                "author": item.author,
                "image_url": item.image_url,
                "caption": item.caption,
            }
            for item in items
        ]
    }


@router.get("/calligraphy-glyph")
def get_calligraphy_glyph(style: str, author: str, char: str):
    if len(char) != 1 or any(token in value for value in (style, author, char) for token in ("/", "\\")):
        raise HTTPException(status_code=400, detail="非法字形参数。")

    image_path = find_glyph_image(style, author, char)
    if not image_path or not image_path.exists():
        raise HTTPException(status_code=404, detail="字形图片不存在。")

    return FileResponse(path=str(image_path), media_type="image/png", filename=image_path.name)

