from __future__ import annotations

import requests

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.config import get_settings


def web_search_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    settings = get_settings()
    query = str(call.args.get("query") or context.message).strip()
    max_results = int(call.args.get("max_results") or settings.web_search_max_results)
    max_results = max(1, min(max_results, 8))

    if settings.web_search_provider.lower() != "tavily":
        return AgentToolResult(
            tool_name=call.tool_name,
            status="skipped",
            content=f"Unsupported web search provider: {settings.web_search_provider}",
            data={"query": query, "results": []},
        )

    if not settings.tavily_api_key:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="skipped",
            content="Web search is not configured. Set TAVILY_API_KEY in backend/.env.",
            data={"query": query, "results": []},
        )

    try:
        response = requests.post(
            settings.tavily_search_url,
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=settings.web_search_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="error",
            error=f"Web search request failed: {exc}",
            data={"query": query, "results": []},
        )

    results = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or item.get("snippet") or "",
            }
        )

    content = "\n".join(
        f"{index + 1}. {item['title']} - {item['url']}\n{item['snippet']}"
        for index, item in enumerate(results)
    )
    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=content or "No web search results.",
        data={"query": query, "results": results},
    )
