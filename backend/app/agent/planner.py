from __future__ import annotations

import json
import re
from typing import Any

from app.agent.llm import invoke_agent_llm, parse_json_object
from app.agent.schemas import AgentContext, AgentNextAction, AgentToolCall, AgentToolResult
from app.agent.tool_registry import TOOL_REGISTRY, get_tool_spec, render_tool_specs_for_planner
from app.services.calligraphy_service import list_calligraphy_authors, list_calligraphy_styles


DEFAULT_FINAL_INSTRUCTION = (
    "根据工具结果用中文自然回答。"
    "如果是作品赏析且工具提供了作品正文，先给正文再给背景和赏析；不要编造不确定的完整文本。"
    "如果工具返回了本地媒体、图片或来源链接，正文不要重复结构化字段里的 URL、文件路径或 ID。"
)


DYNAMIC_NEXT_ACTION_SYSTEM_PROMPT = """你是中文传统文化多工具 Agent 的动态编排器。
你正在执行 Observe-Plan-Act 循环：根据用户原始需求和已观察到的工具结果，决定下一步是否调用工具。

可选动作：
1. call_tools：还需要调用一批工具；这一批可以是 1 个，也可以是多个。
2. finish：已有结果足够，应该进入最终答案综合。

决策规则：
- 工具调用完全由你根据用户需求决定，不要依赖关键词清单。
- 普通寒暄、问候或闲聊只调用 culture_qa_tool，并把用户原话作为 question；不要主动转成书法生成、媒体检索或短剧创作。
- 普通、非时效性的传统文化解释或赏析只调用 culture_qa_tool；不要为了“信息更全面”擅自增加联网搜索、知识库或媒体检索。
- 只有用户明确要求联网、最新/当前信息、网页来源或参考链接时才调用 web_search_tool；未明确要求本地资料时，不要同时增加 knowledge_base_tool。
- 只有用户明确要求本地知识库、项目文档或本地整理资料时才调用 knowledge_base_tool。动态流程中先观察知识库结果：资料足够时可以直接 finish；资料为空或不足且用户未限制“仅本地资料”时，下一轮再调用 culture_qa_tool 补充。
- 只有用户明确要求本地音视频、可播放素材，或询问具体民歌/表演且媒体资源能直接满足需求时才调用 media_search_tool；普通文化概念解释不要调用媒体工具。
- 用户要求生成书法作品时调用 calligraphy_render_tool；参数缺失时保留 null 交给工具追问，不要额外调用搜索或知识库。
- 如果用户要求把某首已知诗词或作品生成书法，但没有直接提供完整正文，先调用 culture_qa_tool 获取可确认准确的【原文】，再让 calligraphy_render_tool 依赖该结果；不要只把题名传给书法工具。
- 每轮可以返回 0 个、1 个或多个工具调用；没有必要调用工具时直接 finish。
- thought_summary 只写一句可展示的决策摘要，不要输出详细推理链、草稿或隐藏思考。
- 同一批工具应尽量互不依赖；如果后续工具依赖前序工具正文，应先调用前序工具，观察结果后下一轮再继续。
- 不要重复调用已经以相同参数执行过的工具。
- 如果用户提出复合需求，要主动拆解并调用多个必要工具。
- 如果已有工具结果已经能回答用户问题，返回 finish。
- 如果工具结果显示配置缺失或资源为空，可以根据用户目标选择降级回答、换用其他工具，或 finish。
- 如果下一步依赖前序工具正文，可以在 args 中使用 text_source 引用前序 step_id，例如 "culture_answer.content"。
- 视频、图片、短剧项目等大对象由系统保存并交给前端展示；你只会看到轻量观察摘要，不需要也不要在最终回答中复述文件路径或 URL。

可用工具：
{{AVAILABLE_TOOLS}}

只返回 JSON：
{
  "action": "call_tools" | "finish",
  "thought_summary": "一句话说明本轮为什么调用这些工具或为什么结束",
  "steps": [
    {
      "id": "stable_step_id",
      "goal": "本步目标",
      "tool_name": "工具名",
      "args": {},
      "depends_on": ["前序step_id"],
      "thought_summary": "可选；本步骤的一句话决策摘要",
      "reason": "调用理由"
    }
  ],
  "final_answer_instruction": "finish 时说明如何综合；call_tools 时可为空",
  "reason": "简短决策理由"
}
"""


def _dynamic_next_action_system_prompt() -> str:
    return DYNAMIC_NEXT_ACTION_SYSTEM_PROMPT.replace("{{AVAILABLE_TOOLS}}", render_tool_specs_for_planner())


def plan_next_agent_action(
    context: AgentContext,
    tool_results: list[AgentToolResult],
    *,
    step_number: int,
    max_steps: int,
    max_tool_calls: int,
) -> AgentNextAction:
    if _is_simple_greeting(context.message):
        if tool_results:
            return AgentNextAction(
                action="finish",
                final_answer_instruction="直接返回问候回复，不要扩展成书法、媒体或短剧任务。",
                thought_summary="普通寒暄已完成，可以结束。",
                reason="Simple greeting already handled.",
            )
        return AgentNextAction(
            action="call_tools",
            tool_calls=[
                AgentToolCall(
                    tool_name="culture_qa_tool",
                    args={"question": context.message},
                    reason="普通寒暄直接由文化问答工具回应",
                    thought_summary="识别为普通问候，直接回应。",
                    step_id="greeting",
                    goal="回应用户问候并提示可用能力",
                )
            ],
            thought_summary="识别为普通问候，直接回应。",
            reason="Simple greeting shortcut.",
        )

    prompt = _build_next_action_prompt(
        context,
        tool_results,
        step_number=step_number,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
    )
    try:
        raw = invoke_agent_llm(_dynamic_next_action_system_prompt(), prompt, temperature=0.15)
        data = parse_json_object(raw)
        return _sanitize_next_action(_next_action_from_data(data), context)
    except Exception:
        return AgentNextAction(
            action="finish",
            final_answer_instruction=DEFAULT_FINAL_INSTRUCTION,
            reason="Dynamic planner fallback: finish with available observations.",
        )


def _build_next_action_prompt(
    context: AgentContext,
    tool_results: list[AgentToolResult],
    *,
    step_number: int,
    max_steps: int,
    max_tool_calls: int,
) -> str:
    return (
        f"当前动态步骤：{step_number}/{max_steps}\n\n"
        f"本轮最多可返回工具调用数：{max_tool_calls}\n\n"
        "最近对话上下文：\n"
        f"{context.conversation_context or ''}\n\n"
        "当前用户消息：\n"
        f"{context.message}\n\n"
        "用户已选择的书法参数：\n"
        f"style={context.calligraphy_style or ''}\n"
        f"author={context.calligraphy_author or ''}\n\n"
        "已观察到的工具结果摘要：\n"
        f"{json.dumps(_serialize_tool_results(tool_results), ensure_ascii=False, indent=2)}\n\n"
        "可用书法选项 JSON：\n"
        f"{json.dumps(_available_calligraphy_options(), ensure_ascii=False)}"
    )


def _next_action_from_data(data: dict[str, Any]) -> AgentNextAction:
    action = str(data.get("action") or "").strip().lower()
    if action == "call_tool":
        action = "call_tools"
    if action not in {"call_tools", "finish"}:
        action = "finish"

    tool_calls = []
    thought_summary = _clean_thought_summary(
        data.get("thought_summary")
        or data.get("thought")
        or data.get("decision_summary")
        or data.get("reason")
    )
    raw_steps = data.get("steps") or data.get("tool_calls") or []
    if not raw_steps and (data.get("step") or data.get("tool_call")):
        raw_steps = [data.get("step") or data.get("tool_call")]
    if not isinstance(raw_steps, list):
        raw_steps = []

    for index, step in enumerate(raw_steps, start=1):
        if action != "call_tools" or not isinstance(step, dict):
            continue
        depends_on = step.get("depends_on") or step.get("dependencies") or []
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        if not isinstance(depends_on, list):
            depends_on = []
        args = step.get("args")
        tool_calls.append(
            AgentToolCall(
                tool_name=str(step.get("tool_name") or "").strip(),
                args=args if isinstance(args, dict) else {},
                reason=str(step.get("reason") or data.get("reason") or ""),
                thought_summary=_clean_thought_summary(
                    step.get("thought_summary")
                    or step.get("thought")
                    or thought_summary
                ),
                step_id=_normalize_step_id(step.get("id") or step.get("step_id") or f"dynamic_step_{index}"),
                goal=str(step.get("goal") or step.get("description") or ""),
                depends_on=[
                    _normalize_step_id(dep)
                    for dep in depends_on
                    if _normalize_step_id(dep)
                ],
            )
        )

    return AgentNextAction(
        action=action,
        tool_calls=tool_calls,
        final_answer_instruction=str(data.get("final_answer_instruction") or ""),
        thought_summary=thought_summary,
        reason=str(data.get("reason") or ""),
    )


def _sanitize_next_action(action: AgentNextAction, context: AgentContext) -> AgentNextAction:
    if action.action == "finish":
        return AgentNextAction(
            action="finish",
            final_answer_instruction=action.final_answer_instruction or DEFAULT_FINAL_INSTRUCTION,
            thought_summary=action.thought_summary,
            reason=action.reason,
        )
    if not action.tool_calls:
        return AgentNextAction(
            action="finish",
            final_answer_instruction=action.final_answer_instruction or DEFAULT_FINAL_INSTRUCTION,
            thought_summary=action.thought_summary,
            reason=action.reason or "Dynamic planner returned no tool calls.",
        )
    valid_calls = [call for call in action.tool_calls if call.tool_name in TOOL_REGISTRY]
    sanitized_calls = _sanitize_tool_calls(valid_calls, context)
    if not sanitized_calls:
        return AgentNextAction(
            action="finish",
            final_answer_instruction=action.final_answer_instruction or DEFAULT_FINAL_INSTRUCTION,
            thought_summary=action.thought_summary,
            reason=action.reason or "Dynamic planner returned no allowed tools.",
        )
    return AgentNextAction(
        action="call_tools",
        tool_calls=sanitized_calls,
        final_answer_instruction=action.final_answer_instruction,
        thought_summary=action.thought_summary,
        reason=action.reason,
    )


def _available_calligraphy_options() -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for style in list_calligraphy_styles():
        options[style] = list_calligraphy_authors(style)
    return options


def _sanitize_tool_calls(
    tool_calls: list[AgentToolCall],
    context: AgentContext,
) -> list[AgentToolCall]:
    allowed_tools = set(TOOL_REGISTRY)
    calls = [call for call in tool_calls if call.tool_name in allowed_tools]
    calls = _ensure_unique_step_ids(calls)

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
            text = _clean_optional(call.args.get("text"))
            text_source = _clean_optional(
                call.args.get("text_source")
                or call.args.get("text_ref")
                or call.args.get("source_step")
            )
            if _looks_like_reference(text):
                text_source = text_source or text
                text = None
            call.args["text"] = text
            call.args["text_source"] = text_source
            call.args["style"] = _clean_optional(call.args.get("style") or context.calligraphy_style)
            call.args["author"] = _clean_optional(call.args.get("author") or context.calligraphy_author)
        elif call.tool_name == "short_video_script_tool":
            call.args["topic"] = str(call.args.get("topic") or _short_video_topic(context))

        call.goal = call.goal or call.reason or _default_goal(call.tool_name)

    _link_calligraphy_to_text_sources(calls)

    valid_step_ids = {call.step_id for call in calls if call.step_id}
    for call in calls:
        call.depends_on = [
            dep
            for dep in call.depends_on
            if dep in valid_step_ids and dep != call.step_id
        ]

    return calls


def _link_calligraphy_to_text_sources(calls: list[AgentToolCall]) -> None:
    culture_call = next((call for call in calls if call.tool_name == "culture_qa_tool" and call.step_id), None)
    if not culture_call:
        return

    for call in calls:
        if call.tool_name != "calligraphy_render_tool":
            continue
        if call.args.get("text"):
            continue
        culture_call.args["question"] = _ensure_work_text_for_calligraphy(
            str(culture_call.args.get("question") or "")
        )
        if not call.args.get("text_source"):
            if culture_call.step_id not in call.depends_on:
                call.depends_on.append(culture_call.step_id)
            call.args["text_source"] = f"{culture_call.step_id}.content"
        call.goal = "根据前序文化问答结果提取正文并生成书法作品"
        call.thought_summary = "先观察文化问答输出，再从其中提取可用于书法的正文。"
        call.reason = "书法生成需要以前序文化问答的正文作为输入。"
        call.goal = call.goal or "根据文化问答提取正文并生成书法作品"


def _ensure_work_text_for_calligraphy(question: str) -> str:
    instruction = (
        "请先输出你能确认准确的作品【原文】区块，原文区块只放题名和正文；"
        "再介绍背景和赏析。后续书法生成将只从【原文】区块提取正文。"
    )
    if "【原文】" in question or "后续书法生成" in question:
        return question
    return f"{question}\n\n{instruction}".strip()


def _normalize_step_id(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:50]


def _ensure_unique_step_ids(calls: list[AgentToolCall]) -> list[AgentToolCall]:
    seen: set[str] = set()
    for index, call in enumerate(calls, start=1):
        base = call.step_id or _default_step_id(call.tool_name) or f"step_{index}"
        step_id = _normalize_step_id(base) or f"step_{index}"
        if step_id in seen:
            step_id = _next_step_id(calls[: index - 1], step_id)
        call.step_id = step_id
        seen.add(step_id)
    return calls


def _next_step_id(calls: list[AgentToolCall], base: str) -> str:
    normalized = _normalize_step_id(base) or "step"
    existing = {call.step_id for call in calls}
    if normalized not in existing:
        return normalized
    suffix = 2
    while f"{normalized}_{suffix}" in existing:
        suffix += 1
    return f"{normalized}_{suffix}"


def _default_step_id(tool_name: str) -> str:
    spec = get_tool_spec(tool_name)
    return spec.default_step_id if spec else "tool_step"


def _default_goal(tool_name: str) -> str:
    spec = get_tool_spec(tool_name)
    return spec.default_goal if spec else "执行工具步骤"


def _looks_like_reference(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip()
    return bool(re.fullmatch(r"\{?\{?[a-zA-Z0-9_]+\.(content|answer|text|poem_text|result)\}?\}?", text))


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


def _clean_thought_summary(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "undefined", "string"}:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:160]


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


def _short_video_topic(context: AgentContext) -> str:
    message = context.message.strip()
    quoted = re.findall(r"[“\"']([^”\"']{1,30})[”\"']", message)
    if quoted:
        return quoted[0].strip()
    return message


def _is_simple_greeting(message: str) -> bool:
    text = re.sub(r"[\s，。！？!?,.；;：:、~～]+", "", message.strip().lower())
    if not text:
        return False
    greetings = {
        "你好",
        "您好",
        "你好啊",
        "您好啊",
        "hello",
        "hi",
        "哈喽",
        "嗨",
        "早上好",
        "中午好",
        "下午好",
        "晚上好",
    }
    return text in {item.lower() for item in greetings}


def _serialize_tool_results(results: list[AgentToolResult]) -> list[dict[str, Any]]:
    serialized = []
    for result in results:
        serialized.append(
            {
                "step_id": result.step_id,
                "goal": result.goal,
                "thought_summary": result.thought_summary,
                "tool_name": result.tool_name,
                "status": result.status,
                "observation": _tool_observation_text(result),
                "data": _lightweight_observation_data(result),
                "error": result.error,
            }
        )
    return serialized


def _tool_observation_text(result: AgentToolResult) -> str:
    if result.status == "error":
        return result.error or "Tool call failed."
    if result.tool_name == "media_search_tool":
        videos = result.data.get("videos") or []
        if videos:
            titles = [
                str(item.get("video_name") or item.get("title") or item.get("file_name") or "").strip()
                for item in videos[:5]
            ]
            titles = [title for title in titles if title]
            return f"媒体检索成功，找到 {len(videos)} 个本地音视频资源：" + "、".join(titles)
        return "媒体检索完成，但没有找到匹配的本地音视频资源。"
    if result.tool_name == "calligraphy_render_tool":
        if result.status == "needs_input":
            return result.content
        missing = result.data.get("missing_chars") or []
        details = f"风格：{result.data.get('style') or '未知'}；作者：{result.data.get('author') or '未知'}。"
        if missing:
            details += " 缺字：" + "、".join(str(item) for item in missing[:30])
        return "书法生成工具调用成功，作品图片已交给前端结构化展示。" + details
    if result.tool_name == "short_video_script_tool":
        project = result.data.get("project") or {}
        title = project.get("title") or result.data.get("topic") or ""
        scenes = project.get("scenes") or project.get("shots") or []
        return f"短剧脚本工具调用成功，已生成《{title}》方案，分镜数量：{len(scenes)}。"
    return _truncate_text(result.content, 1600)


def _lightweight_observation_data(result: AgentToolResult) -> dict[str, Any]:
    if result.tool_name == "media_search_tool":
        videos = result.data.get("videos") or []
        return {
            "query": result.data.get("query"),
            "count": len(videos),
            "titles": [
                item.get("video_name") or item.get("title") or item.get("file_name")
                for item in videos[:8]
                if isinstance(item, dict)
            ],
        }
    if result.tool_name == "calligraphy_render_tool":
        return {
            "generated": bool(result.data.get("image_url")),
            "needs_input": result.status == "needs_input",
            "style": result.data.get("style"),
            "author": result.data.get("author"),
            "missing_chars": result.data.get("missing_chars") or [],
        }
    if result.tool_name == "short_video_script_tool":
        project = result.data.get("project") or {}
        scenes = project.get("scenes") or project.get("shots") or []
        return {
            "stage": result.data.get("stage"),
            "title": project.get("title"),
            "scene_count": len(scenes),
            "capabilities": result.data.get("capabilities") or [],
        }
    if result.tool_name == "web_search_tool":
        results = result.data.get("results") or []
        return {
            "query": result.data.get("query"),
            "count": len(results),
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": _truncate_text(item.get("snippet") or "", 300),
                }
                for item in results[:5]
                if isinstance(item, dict)
            ],
        }
    if result.tool_name == "knowledge_base_tool":
        results = result.data.get("results") or result.data.get("hits") or []
        return {
            "query": result.data.get("query"),
            "count": len(results) if isinstance(results, list) else 0,
            "enabled": result.data.get("enabled"),
            "status": result.data.get("status"),
        }
    return _truncate_data(result.data)


def _truncate_data(value: Any, limit: int = 1800) -> Any:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except TypeError:
        text = str(value)
    if len(text) <= limit:
        return value
    return {"summary": _truncate_text(text, limit)}


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
