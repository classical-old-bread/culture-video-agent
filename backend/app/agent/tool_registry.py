from __future__ import annotations

from collections.abc import Callable

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.agent.tools.calligraphy_tool import calligraphy_render_tool
from app.agent.tools.culture_qa_tool import culture_qa_tool
from app.agent.tools.knowledge_base_tool import knowledge_base_tool
from app.agent.tools.media_tool import media_search_tool
from app.agent.tools.web_search_tool import web_search_tool





ToolHandler = Callable[[AgentContext, AgentToolCall], AgentToolResult]


# Planner output is resolved here so tool names stay decoupled from implementation functions.
TOOL_REGISTRY: dict[str, ToolHandler] = {
    "culture_qa_tool": culture_qa_tool,
    "web_search_tool": web_search_tool,
    "calligraphy_render_tool": calligraphy_render_tool,
    "media_search_tool": media_search_tool,
    "knowledge_base_tool": knowledge_base_tool,
}


def execute_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    handler = TOOL_REGISTRY.get(call.tool_name)
    if not handler:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="error",
            error=f"Unknown tool: {call.tool_name}",
        )
    try:
        return handler(context, call)
    except RuntimeError as exc:
        return AgentToolResult(tool_name=call.tool_name, status="error", error=str(exc))
    except Exception as exc:
        return AgentToolResult(tool_name=call.tool_name, status="error", error=f"{type(exc).__name__}: {exc}")
