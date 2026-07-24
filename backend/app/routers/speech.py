from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.schemas import TTSRequest
from app.services.tts_service import synthesize_speech


router = APIRouter(prefix="/api", tags=["speech"])


@router.post("/tts")
def text_to_speech(request: TTSRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="语音合成文本不能为空。")

    try:
        audio = synthesize_speech(text)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-cache"},
    )

