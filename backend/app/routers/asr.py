from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import InvalidStatusCode
from websockets.legacy.client import connect as websocket_connect

from app.config import get_settings
from app.services.volcengine_asr_service import (
    build_volcengine_asr_request_frame,
    build_volcengine_audio_frame,
    has_volcengine_asr_config,
    parse_volcengine_asr_response,
    volcengine_asr_headers,
)


router = APIRouter(prefix="/api", tags=["asr"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _friendly_asr_error(detail: str) -> str:
    if "requested resource not granted" in detail or '"code":403' in detail or "code=403" in detail:
        return (
            "火山语音识别资源未开通，或当前 Token 没有流式 ASR 权限。"
            "请在火山引擎控制台开通对应资源，并检查 VOLCENGINE_ASR_APP_ID、"
            "VOLCENGINE_ASR_ACCESS_TOKEN、VOLCENGINE_ASR_RESOURCE_ID。"
        )
    return detail


@router.websocket("/asr/stream")
async def asr_stream(websocket: WebSocket):
    await websocket.accept()

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
        async with websocket_connect(
            settings.volcengine_asr_url,
            extra_headers=volcengine_asr_headers(),
            ping_interval=None,
            open_timeout=8,
            max_size=None,
        ) as volcengine_ws:
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

            audio_task = asyncio.create_task(forward_audio())

            async for payload in volcengine_ws:
                code, text, status, serial_number = parse_volcengine_asr_response(payload)
                if code != 0:
                    logger.warning("Volcengine ASR returned error: %s", text)
                    await safe_send_json({"event": "error", "detail": _friendly_asr_error(text)})
                    break

                if text:
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

