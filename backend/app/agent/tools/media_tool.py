from __future__ import annotations

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.services.video_service import search_videos_by_keywords


def media_search_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    query = str(call.args.get("query") or context.message).strip()
    auto_play = False
    prefer_video = bool(call.args.get("prefer_video", True))
    try:
        limit = int(call.args.get("limit") or 3)
    except (TypeError, ValueError):
        limit = 3

    videos = search_videos_by_keywords([query], limit=max(1, min(limit, 10)), prefer_video=prefer_video)
    if not videos:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="success",
            content="No matching local cultural media was found.",
            data={"query": query, "videos": [], "auto_play": False},
        )

    names = ", ".join(str(video.get("video_name", "")) for video in videos)
    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=f"Matched local cultural media: {names}",
        data={"query": query, "videos": videos, "auto_play": auto_play},
    )
