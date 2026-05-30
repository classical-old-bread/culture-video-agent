from __future__ import annotations

import json
import re
from collections.abc import Iterable

from app.agent.llm import invoke_agent_llm, stream_agent_llm
from app.agent.planner import plan_agent_actions
from app.agent.schemas import AgentContext, AgentResult, AgentToolResult
from app.agent.tool_registry import execute_tool

SYNTHESIZER_SYSTEM_PROMPT = """You are a Chinese traditional-culture agent.
Synthesize the final answer from tool results.

Requirements:
- Answer in Chinese.
- Be concise but useful.
- If the answer contains a public-domain classical poem/work text or the user asks about a work's content, output the work first, before background or analysis. Use this order: 【原文】, 【背景】, 【赏析】, then optional 【可用于书法生成的说明】.
- Under 【原文】 include only the title and the work body. Do not put author names, years, source notes, separators, missing-glyph notices, tool status, background text, or Arabic numerals inside the work text.
- If the full work text is uncertain or may be copyrighted, do not invent it; say so before giving summary or analysis.
- If web search results are present, cite source URLs in plain text.
- If local knowledge base results are present, cite source file names in plain text. If no local knowledge base results are found, still answer from general DeepSeek knowledge unless the user explicitly required local-only answers.
- If a calligraphy image was generated, mention that it is ready and avoid pretending it was painted by the LLM.
- Never output Markdown image syntax, HTML image tags, or raw calligraphy image URLs. The frontend renders images from structured fields.
- If a tool reports missing input, ask the user for the missing information instead of inventing it.
- Treat local media as supporting cultural resources, not as the core value of the system.
"""

def run_agent(context: AgentContext) -> AgentResult:
    # Non-streaming path: plan tools, execute them, then synthesize a final answer.
    plan = plan_agent_actions(context)
    tool_results = [execute_tool(context, call) for call in plan.tool_calls]

    blocking = _first_needs_input(tool_results)
    if blocking:
        return _result_from_tools(blocking.content, tool_results)

    if _should_use_tool_answer_directly(tool_results):
        answer = _fallback_answer(tool_results)
    else:
        answer = _synthesize_answer(context, tool_results, plan.final_answer_instruction)
    return _result_from_tools(answer, tool_results)

def stream_agent(context: AgentContext) -> Iterable[tuple[str, dict]]:
    # Streaming path emits plan metadata, tool results, structured fields, and answer deltas.
    plan = plan_agent_actions(context)
    tool_results = []

    yield (
        "meta",
        {
            "type": "agent",
            "videos": [],
            "tool_calls": [
                {"tool_name": call.tool_name, "args": call.args, "reason": call.reason}
                for call in plan.tool_calls
            ],
        },
    )

    for call in plan.tool_calls:
        result = execute_tool(context, call)
        tool_results.append(result)
        yield (
            "tool",
            {
                "tool_name": result.tool_name,
                "status": result.status,
                "content": result.content,
                "error": result.error,
            },
        )

        if result.status == "needs_input":
            final = _result_from_tools(result.content, tool_results)
            yield ("meta", _agent_result_payload(final))
            yield ("delta", {"content": result.content})
            yield ("done", {})
            return

    # Send media/image/source metadata before text generation completes.
    final_base = _result_from_tools("", tool_results)
    yield ("meta", _agent_result_payload(final_base))

    if _should_use_tool_answer_directly(tool_results):
        answer = _fallback_answer(tool_results)
        if answer:
            yield ("delta", {"content": answer})
        yield ("done", {})
        return

    streamed_any = False
    try:
        for chunk in _stream_synthesized_answer(context, tool_results, plan.final_answer_instruction):
            streamed_any = True
            yield ("delta", {"content": chunk})
    except RuntimeError:
        fallback = _fallback_answer(tool_results)
        streamed_any = bool(fallback)
        if fallback:
            yield ("delta", {"content": fallback})

    if not streamed_any:
        yield ("delta", {"content": _fallback_answer(tool_results) or "暂时没有生成有效回答，请稍后再试。"})

    yield ("done", {})

def _synthesize_answer(
    context: AgentContext,
    tool_results: list[AgentToolResult],
    instruction: str,
) -> str:
    prompt = _build_synthesizer_prompt(context, tool_results, instruction)
    try:
        return _clean_final_answer(
            invoke_agent_llm(SYNTHESIZER_SYSTEM_PROMPT, prompt, temperature=0.5)
        )
    except RuntimeError:
        return _fallback_answer(tool_results)

def _stream_synthesized_answer(
    context: AgentContext,
    tool_results: list[AgentToolResult],
    instruction: str,
) -> Iterable[str]:
    prompt = _build_synthesizer_prompt(context, tool_results, instruction)
    yield from stream_agent_llm(SYNTHESIZER_SYSTEM_PROMPT, prompt, temperature=0.5)

def _build_synthesizer_prompt(
    context: AgentContext,
    tool_results: list[AgentToolResult],
    instruction: str,
) -> str:
    serialized = [
        {
            "tool_name": result.tool_name,
            "status": result.status,
            "content": result.content,
            "data": result.data,
            "error": result.error,
        }
        for result in tool_results
    ]
    return (
        f"User message:\n{context.message}\n\n"
        f"Final answer instruction:\n{instruction or 'Summarize the tool results.'}\n\n"
        "Tool results JSON:\n"
        f"{json.dumps(serialized, ensure_ascii=False, indent=2)}\n\n"
        "When a tool result already contains a correctly ordered 【原文】 block, preserve that order in the final answer. "
        "Important: structured fields already include image URLs and media URLs. "
        "Do not repeat them in the natural-language answer."
    )

def _result_from_tools(answer: str, tool_results: list[AgentToolResult]) -> AgentResult:
    videos = []
    auto_play = False
    calligraphy_image_url = None
    calligraphy_missing_chars: list[str] = []
    sources = []

    for result in tool_results:
        if result.tool_name == "media_search_tool":
            videos = result.data.get("videos") or videos
            auto_play = bool(result.data.get("auto_play")) if videos else False
        elif result.tool_name == "calligraphy_render_tool":
            calligraphy_image_url = result.data.get("image_url") or calligraphy_image_url
            calligraphy_missing_chars = result.data.get("missing_chars") or calligraphy_missing_chars
        elif result.tool_name == "web_search_tool":
            sources.extend(result.data.get("results") or [])
        elif result.tool_name == "knowledge_base_tool":
            for item in result.data.get("results") or []:
                sources.append(
                    {
                        "title": item.get("source") or "本地知识库",
                        "url": "",
                        "snippet": item.get("content") or "",
                        "score": item.get("score"),
                        "source_type": "knowledge_base",
                    }
                )

    response_type = "agent"
    if calligraphy_image_url:
        response_type = "calligraphy"
    elif videos:
        response_type = "text_with_video"

    return AgentResult(
        answer=answer,
        response_type=response_type,
        videos=videos,
        auto_play=auto_play,
        calligraphy_image_url=calligraphy_image_url,
        calligraphy_missing_chars=calligraphy_missing_chars,
        sources=sources,
        tool_calls=[
            {
                "tool_name": result.tool_name,
                "status": result.status,
                "error": result.error,
            }
            for result in tool_results
        ],
    )

def _first_needs_input(tool_results: list[AgentToolResult]) -> AgentToolResult | None:
    for result in tool_results:
        if result.status == "needs_input":
            return result
    return None

def _should_use_tool_answer_directly(tool_results: list[AgentToolResult]) -> bool:
    completed = [
        result
        for result in tool_results
        if result.status == "success" and result.tool_name != "culture_qa_tool"
    ]
    return len(completed) == 1 and completed[0].tool_name == "calligraphy_render_tool"

def _fallback_answer(tool_results: list[AgentToolResult]) -> str:
    parts = []
    for result in tool_results:
        if result.status in {"success", "needs_input", "skipped"} and result.content:
            parts.append(result.content)
        elif result.status == "error" and result.error:
            parts.append(f"{result.tool_name} 调用失败：{result.error}")
    return _clean_final_answer("\n\n".join(parts).strip())

def _clean_final_answer(answer: str) -> str:
    if not answer:
        return ""
    cleaned = re.sub(r"!\[[^\]]*\]\((?:/api/calligraphy|https?://[^)]*/api/calligraphy)[^)]+\)", "", answer)
    cleaned = re.sub(r"<img[^>]+(?:/api/calligraphy|calligraphy)[^>]*>", "", cleaned, flags=re.I)
    cleaned = re.sub(r"(?m)^\s*(?:/api/calligraphy|https?://\S+/api/calligraphy)/?\S*\s*$", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def _agent_result_payload(result: AgentResult) -> dict:
    return {
        "type": result.response_type,
        "videos": result.videos,
        "auto_play": result.auto_play,
        "calligraphy_image_url": result.calligraphy_image_url,
        "calligraphy_missing_chars": result.calligraphy_missing_chars,
        "sources": result.sources,
        "tool_calls": result.tool_calls,
    }
