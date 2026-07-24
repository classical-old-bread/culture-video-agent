from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.services.path_utils import resolve_resource_path
from app.services.video_service import get_video_by_id


router = APIRouter(prefix="/api", tags=["media"])


@router.get("/video/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = get_video_by_id(video_id, db=db)
    if not video:
        raise HTTPException(status_code=404, detail="媒体文件记录不存在。")

    stored_path = video["file_path"] if isinstance(video, dict) else video.file_path
    media_type = video.get("media_type", "audio/mpeg") if isinstance(video, dict) else "video/mp4"

    try:
        file_path = resolve_resource_path(get_settings().media_library_dir, stored_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法媒体文件路径。") from None

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="媒体文件不存在或路径未配置。")

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )

