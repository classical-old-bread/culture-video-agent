from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.coordinator import run_agent, stream_agent
from app.agent.schemas import AgentContext
from app.config import get_settings
from app.database import get_db
from app.schemas import ChatRequest, ChatResponse


router = APIRouter(prefix="/api", tags=["chat"])
settings = get_settings()
logger = logging.getLogger(__name__)


def _sse_event(event: str, data: dict) -> str:
    # SSE 每个事件由 event 和 data 两部分组成，前端按事件类型更新工具轨迹和正文。
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _clean_agent_optional(value: str | None) -> str | None:
    # Swagger 示例值或前端空字符串不应进入 Planner，否则会被误当成真实上下文。
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"string", "null", "none", "undefined"}:
        return None
    return cleaned


def _build_agent_context(request: ChatRequest, db: Session) -> AgentContext:
    # AgentContext 聚合一轮对话所需的上下文，后续 Planner、工具和服务层都从这里取数据。
    return AgentContext(
        message=request.message.strip(),
        conversation_context=_clean_agent_optional(request.conversation_context),
        calligraphy_source_text=_clean_agent_optional(request.calligraphy_source_text),
        calligraphy_style=_clean_agent_optional(request.calligraphy_style),
        calligraphy_author=_clean_agent_optional(request.calligraphy_author),
        short_video_character_profile=_clean_agent_optional(request.short_video_character_profile),
        db=db,
    )


def _validate_message(message: str) -> None:
    if not message:
        raise HTTPException(status_code=400, detail="用户输入不能为空。")
    if len(message) > settings.max_message_length:
        raise HTTPException(status_code=400, detail=f"用户输入过长，最大 {settings.max_message_length} 字。")


@router.post("/chat", response_model=ChatResponse)
def agent_chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    message = request.message.strip()
    _validate_message(message)

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
        calligraphy_selection=result.calligraphy_selection,
        short_video_project=result.short_video_project,
        sources=result.sources,
        tool_calls=result.tool_calls,
    )


@router.post("/chat/stream")
def agent_chat_stream(request: ChatRequest, db: Session = Depends(get_db)):
    message = request.message.strip()
    _validate_message(message)

    def event_generator():
        # 后端逐步 yield meta/tool/delta/done，浏览器可以边生成边展示，不必等待整段回答完成。
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
