from __future__ import annotations

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.services.short_video_service import format_short_video_project, generate_short_video_project


def short_video_script_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    topic = str(call.args.get("topic") or context.message).strip()
    project = generate_short_video_project(
        topic,
        user_message=context.message,
        character_profile=context.short_video_character_profile,
    )
    markdown = format_short_video_project(project)
    content = f"已生成《{project['title']}》五镜头短剧方案。右侧面板可查看分镜卡片和复制 AI 视频提示词。"
    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=content,
        data={
            "topic": topic,
            "stage": "script_ready",
            "capabilities": ["script", "dialogue", "storyboard"],
            "project": project,
            "markdown": markdown,
        },
    )
