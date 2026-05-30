from __future__ import annotations

import json
from typing import Any

from app.agent.llm import invoke_agent_llm, parse_json_object
from app.agent.schemas import AgentContext, AgentPlan, AgentToolCall
from app.agent.tool_registry import TOOL_REGISTRY
from app.services.calligraphy_service import list_calligraphy_authors, list_calligraphy_styles


PLANNER_SYSTEM_PROMPT = """You are the planner for a Chinese traditional-culture tool-using agent.
Return JSON only. Do not answer the user directly.

Your job is to understand the user's intent from the current message and recent conversation, extract structured arguments, and choose the tools needed to complete the task.
Use semantic understanding, not brittle keyword routing. Resolve pronouns and follow-up messages from the conversation context.

Available tools:
1. culture_qa_tool
   Use for traditional culture, poetry, folk customs, calligraphy knowledge, greetings, and cultural explanation.
   args: {"question": string}
2. web_search_tool
   Use when the user asks for online search, sources, references, recent/current information, or web pages.
   args: {"query": string, "max_results": number}
3. calligraphy_render_tool
   Use when the user wants a calligraphy image/work generated or is completing a previous calligraphy style/author selection.
   args: {"text": string|null, "style": string|null, "author": string|null}
4. media_search_tool
   Use when local audio/video works can enrich the answer, especially for a concrete folk song, regional folk music, performance, or cultural work that the user may want to inspect.
   args: {"query": string, "auto_play": boolean, "limit": number, "prefer_video": boolean}
   Always set auto_play to false. The frontend should show media resources and only play after the user clicks.
5. knowledge_base_tool
   Use when the user asks for local curated documents, a knowledge base, project documents, or explicitly says to answer according to local materials.
   args: {"query": string, "top_k": number}

Planning principles:
- For ordinary cultural explanation, call culture_qa_tool.
- knowledge_base_tool is an evidence source, not the final fallback. Whenever you call knowledge_base_tool, also call culture_qa_tool unless the user is only asking whether the local knowledge base contains a document.
- If the user asks about a concrete folk song, folk music category, regional song, or cultural performance and local media could enrich the response, call both culture_qa_tool and media_search_tool.
- For media_search_tool, pass a concise search query containing the work/topic name and cultural category inferred from the user message. Do not include filler words.
- If the user explicitly asks to play, listen, or watch, still set auto_play to false; the UI will wait for a click.
- For calligraphy generation, call calligraphy_render_tool. If text, style, or author is missing, pass null rather than guessing; the tool can ask for missing input.
- For web/current/source requests, call web_search_tool.
- Do not call tools that are not useful for the current task.

Calligraphy rules:
- If the user refers to "this poem/work/above text/previous one", use the provided recent assistant text as the source. You may set text to null; the tool receives that context separately.
- If style or author is missing, still call calligraphy_render_tool with null for the missing fields. The tool will ask for the missing input.
- Use only available calligraphy styles/authors listed in the user prompt. If the user gives an unsupported style or author, pass their value anyway so the tool can validate and ask clearly.

Output shape:
{
  "intent": "short intent label",
  "topic": "main user topic or null",
  "domain": "culture domain inferred from the message or null",
  "tool_calls": [
    {"tool_name": "tool name", "args": {}, "reason": "short reason"}
  ],
  "final_answer_instruction": "how to synthesize the answer"
}
"""


DEFAULT_FINAL_INSTRUCTION = (
    "根据工具结果用中文自然回答。"
    "如果是作品赏析且工具提供了作品正文，先给正文再给背景和赏析；不要编造不确定的完整文本。"
    "如果工具返回了本地媒体、图片或来源链接，正文不要重复结构化字段里的 URL、文件路径或 ID。"
)


def plan_agent_actions(context: AgentContext) -> AgentPlan:
    prompt = _build_planner_prompt(context)
    try:
        raw = invoke_agent_llm(PLANNER_SYSTEM_PROMPT, prompt, temperature=0.1)
        data = parse_json_object(raw)
        return _sanitize_plan(_plan_from_data(data), context)
    except Exception:
        return _fallback_plan(context)


def _build_planner_prompt(context: AgentContext) -> str:
    return (
        "Recent conversation context:\n"
        f"{context.conversation_context or ''}\n\n"
        "Recent assistant text that may contain a work to reuse for calligraphy:\n"
        f"{context.calligraphy_source_text or ''}\n\n"
        "Current user message:\n"
        f"{context.message}\n\n"
        "User-selected calligraphy hints, if any:\n"
        f"style={context.calligraphy_style or ''}\n"
        f"author={context.calligraphy_author or ''}\n\n"
        "Available calligraphy options JSON:\n"
        f"{json.dumps(_available_calligraphy_options(), ensure_ascii=False)}"
    )


def _available_calligraphy_options() -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for style in list_calligraphy_styles():
        options[style] = list_calligraphy_authors(style)
    return options


def _plan_from_data(data: dict[str, Any]) -> AgentPlan:
    calls = []
    for item in data.get("tool_calls") or []:
        if not isinstance(item, dict):
            continue
        tool_name = str(item.get("tool_name") or "").strip()
        args = item.get("args")
        calls.append(
            AgentToolCall(
                tool_name=tool_name,
                args=args if isinstance(args, dict) else {},
                reason=str(item.get("reason") or ""),
            )
        )

    return AgentPlan(
        tool_calls=calls,
        final_answer_instruction=str(data.get("final_answer_instruction") or DEFAULT_FINAL_INSTRUCTION),
    )


def _sanitize_plan(plan: AgentPlan, context: AgentContext) -> AgentPlan:
    allowed_tools = set(TOOL_REGISTRY)
    calls = [call for call in plan.tool_calls if call.tool_name in allowed_tools]

    for call in calls:
        if call.tool_name == "culture_qa_tool":
            call.args["question"] = str(call.args.get("question") or _contextual_question(context))
        elif call.tool_name == "web_search_tool":
            call.args["query"] = str(call.args.get("query") or context.message)
            call.args["max_results"] = _bounded_int(call.args.get("max_results"), default=5, minimum=1, maximum=8)
        elif call.tool_name == "media_search_tool":
            call.args["query"] = str(call.args.get("query") or context.message)
            call.args["auto_play"] = False
            call.args["limit"] = _bounded_int(call.args.get("limit"), default=3, minimum=1, maximum=10)
            call.args["prefer_video"] = bool(call.args.get("prefer_video", True))
        elif call.tool_name == "knowledge_base_tool":
            call.args["query"] = str(call.args.get("query") or context.message)
            call.args["top_k"] = _bounded_int(call.args.get("top_k"), default=4, minimum=1, maximum=12)
        elif call.tool_name == "calligraphy_render_tool":
            call.args["text"] = _clean_optional(call.args.get("text"))
            call.args["style"] = _clean_optional(call.args.get("style") or context.calligraphy_style)
            call.args["author"] = _clean_optional(call.args.get("author") or context.calligraphy_author)

    if any(call.tool_name == "knowledge_base_tool" for call in calls) and not any(
        call.tool_name == "culture_qa_tool" for call in calls
    ):
        calls.append(
            AgentToolCall(
                "culture_qa_tool",
                {"question": _contextual_question(context)},
                "DeepSeek fallback when local knowledge base is empty or insufficient",
            )
        )

    if not calls:
        calls = [
            AgentToolCall(
                "culture_qa_tool",
                {"question": _contextual_question(context)},
                "planner fallback",
            )
        ]

    return AgentPlan(tool_calls=calls, final_answer_instruction=plan.final_answer_instruction or DEFAULT_FINAL_INSTRUCTION)


def _fallback_plan(context: AgentContext) -> AgentPlan:
    return AgentPlan(
        tool_calls=[
            AgentToolCall(
                "culture_qa_tool",
                {"question": _contextual_question(context)},
                "planner fallback",
            )
        ],
        final_answer_instruction=DEFAULT_FINAL_INSTRUCTION,
    )


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "undefined", "string"}:
        return None
    return text


def _contextual_question(context: AgentContext) -> str:
    if not context.conversation_context:
        return context.message
    return (
        "最近对话：\n"
        f"{context.conversation_context}\n\n"
        "用户当前问题：\n"
        f"{context.message}\n\n"
        "请结合最近对话理解代词或省略主语后回答。"
    )
