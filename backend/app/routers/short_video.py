from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.short_video_render_service import (
    fetch_short_video_render_status,
    get_short_video_asset_path,
    get_short_video_prototype_frame_path,
    list_short_video_prototype_frames,
    submit_short_video_render,
)


router = APIRouter(prefix="/api/short-video", tags=["short-video"])


class ShortVideoRenderRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=3000)
    duration: int = Field(default=5, ge=3, le=5)
    previous_tail_frame_url: str | None = Field(default=None, max_length=1000)
    character_reference_image_data_url: str | None = Field(default=None, max_length=8_000_000)
    prototype_reference_frame_url: str | None = Field(default=None, max_length=1000)


@router.post("/render")
def submit_render(request: ShortVideoRenderRequest) -> dict:
    try:
        return submit_short_video_render(
            prompt=request.prompt,
            duration=request.duration,
            previous_tail_frame_url=request.previous_tail_frame_url,
            character_reference_image_data_url=request.character_reference_image_data_url,
            prototype_reference_frame_url=request.prototype_reference_frame_url,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/render/{task_id}")
def get_render_status(task_id: str) -> dict:
    try:
        return fetch_short_video_render_status(task_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assets/{kind}/{filename}")
def get_short_video_asset(kind: str, filename: str):
    try:
        path = get_short_video_asset_path(kind, filename)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path)


@router.get("/prototype-frames")
def get_short_video_prototype_frames() -> dict:
    return {"items": list_short_video_prototype_frames()}


@router.get("/prototype-frames/{filename}")
def get_short_video_prototype_frame(filename: str):
    try:
        path = get_short_video_prototype_frame_path(filename)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path)
