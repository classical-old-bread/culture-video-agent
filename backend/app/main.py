from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from websockets.exceptions import InvalidStatusCode
from websockets.legacy.client import connect as websocket_connect

from app.agent.orchestrator import run_agent, stream_agent
from app.agent.schemas import AgentContext
from app.config import get_settings
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse, TTSRequest
from app.services.calligraphy_service import build_calligraphy_gallery, find_glyph_image
from app.services.tts_service import synthesize_speech
from app.services.video_service import get_video_by_id
from app.services.volcengine_asr_service import (
    build_volcengine_asr_request_frame,
    build_volcengine_audio_frame,
    has_volcengine_asr_config,
    parse_volcengine_asr_response,
    volcengine_asr_headers,
)

settings = get_settings()

app = FastAPI(title="文化问答与本地媒体智能体")

logger = logging.getLogger(__name__)

# Local development CORS; lock this down to production domains before deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}

def _friendly_asr_error(detail: str) -> str:
    if "requested resource not granted" in detail or '"code":403' in detail or "code=403" in detail:
        return (
            "火山语音识别资源未开通或当前 Token 没有流式 ASR 权限。"
            "请在火山引擎控制台开通对应资源，并检查 VOLCENGINE_ASR_APP_ID、"
            "VOLCENGINE_ASR_ACCESS_TOKEN、VOLCENGINE_ASR_RESOURCE_ID。"
        )
    return detail

# Browser audio is proxied through the backend so Volcengine credentials and protocol details stay server-side.
@app.websocket("/api/asr/stream")
async def asr_stream(websocket: WebSocket):
    await websocket.accept()

    # Client disconnects are normal for WebSocket audio sessions; send/close helpers stay best-effort.
    async def safe_send_json(data: dict) -> bool:
        try:
            await websocket.send_json(data)
            return True
        except Exception:
            return False

    async def safe_close() -> None:
        try:
            await websocket.close()
        except Exception:
            pass

    if not has_volcengine_asr_config():
        await safe_send_json(
            {
                "event": "error",
                "detail": (
                    "火山语音识别未配置，请在 backend/.env 填写 "
                    "VOLCENGINE_ASR_APP_ID、VOLCENGINE_ASR_ACCESS_TOKEN。"
                ),
            }
        )
        await safe_close()
        return

    sent_first_frame = False
    sent_final_frame = False
    result_segments: dict[int, str] = {}
    last_transcript = ""
    use_full_asr_result = "/api/v3/" in settings.volcengine_asr_url

    try:
        # Maintain two WebSocket legs: browser -> backend for audio input, backend -> Volcengine for ASR.
        async with websocket_connect(
            settings.volcengine_asr_url,
            extra_headers=volcengine_asr_headers(),
            ping_interval=None,
            open_timeout=8,
            max_size=None,
        ) as volcengine_ws:
            # Volcengine ASR requires a request frame before any audio frames.
            await volcengine_ws.send(build_volcengine_asr_request_frame())

            async def forward_audio() -> None:
                nonlocal sent_first_frame, sent_final_frame
                try:
                    while True:
                        message = await websocket.receive()
                        if message.get("bytes") is not None:
                            audio = message["bytes"] or b""
                            if audio:
                                await volcengine_ws.send(build_volcengine_audio_frame(audio))
                                sent_first_frame = True
                        elif message.get("text") is not None:
                            payload = json.loads(message["text"])
                            if payload.get("event") == "end":
                                await volcengine_ws.send(build_volcengine_audio_frame(b"", final=True))
                                sent_first_frame = True
                                sent_final_frame = True
                                return
                        elif message.get("type") == "websocket.disconnect":
                            return
                except WebSocketDisconnect:
                    return
                except Exception as exc:
                    logger.info("ASR frontend audio forwarding stopped: %s", exc)
                    return

            audio_task = asyncio.create_task(forward_audio())

            async for payload in volcengine_ws:
                code, text, status, serial_number = parse_volcengine_asr_response(payload)
                if code != 0:
                    logger.warning("Volcengine ASR returned error: %s", text)
                    await safe_send_json({"event": "error", "detail": _friendly_asr_error(text)})
                    break

                if text:
                    # v3 ASR often returns cumulative text; older responses may need serial-number stitching.
                    if use_full_asr_result or serial_number is None:
                        transcript = text
                    else:
                        result_segments[serial_number] = text
                        transcript = "".join(result_segments[index] for index in sorted(result_segments))

                    if transcript and transcript != last_transcript:
                        last_transcript = transcript
                        if not await safe_send_json({"event": "result", "text": transcript}):
                            break

                if status == 2:
                    await safe_send_json({"event": "done"})
                    break

            audio_task.cancel()
            try:
                await audio_task
            except asyncio.CancelledError:
                pass

            # If the browser disconnects mid-stream, send a final audio frame when possible so ASR can close cleanly.
            if not sent_final_frame and sent_first_frame:
                try:
                    await volcengine_ws.send(build_volcengine_audio_frame(b"", final=True))
                except Exception:
                    pass
    except WebSocketDisconnect:
        return
    except (ConnectionResetError, TimeoutError, OSError) as exc:
        logger.warning("ASR stream connection failed: %s %r", type(exc).__name__, exc)
        await safe_send_json({"event": "error", "detail": "火山语音识别连接失败，请稍后再试。"})
    except InvalidStatusCode as exc:
        logger.warning(
            "ASR websocket handshake rejected: HTTP %s, url=%s, resource_id=%s",
            exc.status_code,
            settings.volcengine_asr_url,
            settings.volcengine_asr_resource_id,
        )
        await safe_send_json(
            {
                "event": "error",
                "detail": (
                    f"火山语音识别连接被拒绝：HTTP {exc.status_code}。"
                    "请检查 ASR URL、Resource ID 和应用密钥。"
                ),
            }
        )
    except Exception as exc:
        logger.exception("ASR stream failed")
        await safe_send_json({"event": "error", "detail": f"火山语音识别连接失败：{exc}"})
    finally:
        await safe_close()

# SSE blocks are streamed as named events consumed by the Vue client.
def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)  # 把 Python 对象序列化成 JSON 字符串
    return f"event: {event}\ndata: {payload}\n\n"

def _clean_agent_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()  # strip() 用来去掉字符串两端的空白字符（空格、制表符 \t、换行 \n、回车等），返回一个新字符串，原字符串不变。
    if not cleaned or cleaned.lower() in {"string", "null", "none", "undefined"}:
        return None
    return cleaned

def _build_agent_context(request: ChatRequest, db: Session) -> AgentContext:
    return AgentContext(
        message=request.message.strip(),
        conversation_context=_clean_agent_optional(request.conversation_context),
        calligraphy_source_text=_clean_agent_optional(request.calligraphy_source_text),
        calligraphy_style=_clean_agent_optional(request.calligraphy_style),
        calligraphy_author=_clean_agent_optional(request.calligraphy_author),
        db=db,
    )

@app.post("/api/chat", response_model=ChatResponse)
def agent_chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="用户输入不能为空。")
    if len(message) > settings.max_message_length:
        raise HTTPException(status_code=400, detail=f"用户输入过长，最多 {settings.max_message_length} 字。")

    try:
        result = run_agent(_build_agent_context(request, db))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        type=result.response_type,
        answer=result.answer,
        videos=result.videos,
        auto_play=result.auto_play,
        calligraphy_image_url=result.calligraphy_image_url,
        calligraphy_missing_chars=result.calligraphy_missing_chars,
        sources=result.sources,
        tool_calls=result.tool_calls,
    )

# Streaming chat sends metadata/tool events before answer deltas so media and tool traces render early.
@app.post("/api/chat/stream")
def agent_chat_stream(request: ChatRequest, db: Session = Depends(get_db)):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="用户输入不能为空。")
    if len(message) > settings.max_message_length:
        raise HTTPException(status_code=400, detail=f"用户输入过长，最多 {settings.max_message_length} 字。")

    def event_generator():
        try:
            for event, data in stream_agent(_build_agent_context(request, db)):
                yield _sse_event(event, data)
        except RuntimeError as exc:
            yield _sse_event("error", {"detail": str(exc)})
        except Exception as exc:
            logger.exception("Agent stream request failed")
            yield _sse_event("error", {"detail": f"Agent 请求处理失败：{exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/tts")
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

@app.get("/api/calligraphy/{filename}")
def get_calligraphy_image(filename: str):
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名。")

    output_dir = Path(settings.calligraphy_output_dir).resolve()
    image_path = (output_dir / filename).resolve()
    if output_dir not in image_path.parents:
        raise HTTPException(status_code=400, detail="非法文件路径。")
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="书法作品不存在或已被清理。")

    return FileResponse(path=str(image_path), media_type="image/png", filename=filename)

@app.get("/api/calligraphy-gallery")
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

@app.get("/api/calligraphy-glyph")
def get_calligraphy_glyph(style: str, author: str, char: str):
    if len(char) != 1 or any(token in value for value in (style, author, char) for token in ("/", "\\")):
        raise HTTPException(status_code=400, detail="非法字形参数。")

    image_path = find_glyph_image(style, author, char)
    if not image_path or not image_path.exists():
        raise HTTPException(status_code=404, detail="字形图片不存在。")

    return FileResponse(path=str(image_path), media_type="image/png", filename=image_path.name)

@app.get("/api/video/{video_id}")
def get_video(video_id: int):
    video = get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="媒体文件记录不存在。")

    file_path = video["file_path"] if isinstance(video, dict) else video.file_path
    media_type = video.get("media_type", "audio/mpeg") if isinstance(video, dict) else "video/mp4"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="媒体文件不存在或路径未配置。")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=os.path.basename(file_path),
    )
