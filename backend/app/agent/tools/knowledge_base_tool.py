from __future__ import annotations

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.config import get_settings
from app.services.rag_service import search_knowledge_base


def knowledge_base_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    query = str(call.args.get("query") or context.message).strip()
    try:
        top_k = int(call.args.get("top_k") or get_settings().knowledge_base_top_k)
    except (TypeError, ValueError):
        top_k = get_settings().knowledge_base_top_k
    result = search_knowledge_base(query, top_k=top_k)

    if not result.has_hits:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="skipped",
            content=(
                result.message
                + " 本轮会继续使用 DeepSeek 的通用文化知识回答；"
                "除非用户明确要求只能依据本地知识库，否则不要因为知识库为空而拒答。"
            ),
            data={
                **result.to_dict(),
                "enabled": result.status not in {"not_ready", "dependency_missing"},
            },
        )

    formatted_hits = "\n\n".join(
        (
            f"[资料 {index}] 来源：{hit.source}；相关度："
            f"{hit.score if hit.score is not None else 'unknown'}\n{hit.content}"
        )
        for index, hit in enumerate(result.hits, start=1)
    )
    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=(
            "以下是从本地知识库检索到的资料片段。"
            "回答时优先参考这些资料；如果资料不足，可以结合 DeepSeek 通用知识补充，并说明依据。\n\n"
            f"{formatted_hits}"
        ),
        data={**result.to_dict(), "enabled": True},
    )
