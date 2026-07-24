from __future__ import annotations

import json
import re
# collections.abc.Iterable 用于标注流式生成函数会逐步 yield 事件。
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from app.agent.agents.domain_registry import get_domain_agent, run_domain_agent
from app.agent.llm import invoke_agent_llm, stream_agent_llm
from app.agent.planner import plan_next_agent_action
from app.agent.schemas import AgentContext, AgentNextAction, AgentPlan, AgentResult, AgentToolCall, AgentToolResult
from app.agent.tool_registry import get_tool_spec


MAX_DYNAMIC_STEPS = 6
MAX_DYNAMIC_TOOL_CALLS = 10


SYNTHESIZER_SYSTEM_PROMPT = """You are a Chinese traditional-culture agent.
Synthesize the final answer from tool results.

Requirements:
- Answer in Chinese.
- Be concise but useful.
- If the answer contains a known poem/work text or the user asks about a work's content, output the work first, before background or analysis. Use this order: 【原文】, 【背景】, 【赏析】, then optional 【可用于书法生成的说明】.
- Under 【原文】 include only the title and the work body. Do not put author names, years, source notes, separators, missing-glyph notices, tool status, background text, or Arabic numerals inside the work text.
- If the full work text is uncertain, do not invent it; say so before giving summary or analysis.
- If web search results are present, cite source URLs in plain text.
- If local knowledge base results are present, cite source file names in plain text. If no local knowledge base results are found, still answer from general DeepSeek knowledge unless the user explicitly required local-only answers.
- If a calligraphy image was generated, mention that it is ready and avoid pretending it was painted by the LLM.
- Never output Markdown image syntax, HTML image tags, or raw calligraphy image URLs. The frontend renders images from structured fields.
- If a tool reports missing input, ask the user for the missing information instead of inventing it.
- Treat local media as supporting cultural resources, not as the core value of the system.
"""


def run_agent(context: AgentContext) -> AgentResult:
    # 非流式总协调器入口。
    # 整体流程是：
    # 1. Planner 先根据用户输入决定需要哪些能力。
    # 2. Coordinator 把每个工具调用交给对应领域 Agent。
    # 3. 如果领域 Agent 需要用户补充信息，直接返回这个提示。
    # 4. 如果领域 Agent 都执行完，再让大模型把结果整理成最终回答。
    plan = AgentPlan()
    tool_results = _execute_dynamic_plan(context, plan)
    answer = _answer_from_tool_results(context, plan, tool_results)
    return _result_from_tools(answer, tool_results)


def stream_agent(context: AgentContext) -> Iterable[tuple[str, dict]]:
    # 流式总协调器入口。
    # 它和 run_agent 做的是同一件事，但不会一次性返回完整结果。
    # 这里会不断 yield 事件：
    # - meta：告诉前端本轮计划了哪些工具、当前响应类型是什么。
    # - tool：告诉前端某个工具执行到了什么状态。
    # - delta：大模型生成的正文片段。
    # - done：本轮回答结束。
    plan = AgentPlan()
    tool_results = []

    yield ("meta", _plan_payload(plan))

    for result in _iter_dynamic_plan_results(context, plan):
        tool_results.append(result)
        yield ("tool", _tool_result_payload(result))

        if result.status == "needs_input":
            yield from _stream_needs_input(result, tool_results)
            return

    # 工具执行完后，先把结构化结果发给前端。
    # 例如媒体工具返回 videos，前端就可以先渲染视频卡片，不必等正文完全生成完。
    if _should_use_tool_answer_directly(tool_results):
        yield from _stream_direct_answer(tool_results)
        yield ("meta", _agent_result_payload(_result_from_tools("", tool_results)))
        yield ("done", {})
        return

    yield from _stream_answer_chunks(context, plan, tool_results)
    yield ("meta", _agent_result_payload(_result_from_tools("", tool_results)))
    yield ("done", {})


def _execute_dynamic_plan(context: AgentContext, plan: AgentPlan) -> list[AgentToolResult]:
    return list(_iter_dynamic_plan_results(context, plan))


def _iter_dynamic_plan_results(context: AgentContext, plan: AgentPlan) -> Iterable[AgentToolResult]:
    tool_results: list[AgentToolResult] = []
    results_by_step: dict[str, AgentToolResult] = {}
    executed_signatures: set[str] = set()
    total_tool_calls = 0
    deferred_calls: list[AgentToolCall] = []

    for step_number in range(1, MAX_DYNAMIC_STEPS + 1):
        if deferred_calls:
            next_action = AgentNextAction(
                action="call_tools",
                tool_calls=deferred_calls,
                thought_summary="Continue with tools that depend on previous observations.",
                reason="Deferred until prerequisite tool results were available.",
            )
            deferred_calls = []
        else:
            next_action = plan_next_agent_action(
                context,
                tool_results,
                step_number=step_number,
                max_steps=MAX_DYNAMIC_STEPS,
                max_tool_calls=max(1, MAX_DYNAMIC_TOOL_CALLS - total_tool_calls),
            )

        if next_action.action == "finish":
            if next_action.final_answer_instruction:
                plan.final_answer_instruction = next_action.final_answer_instruction
            break

        batch_calls = _ordered_tool_calls(AgentPlan(tool_calls=next_action.tool_calls))
        batch_calls = [
            replace(
                call,
                thought_summary=call.thought_summary or next_action.thought_summary,
            )
            for call in batch_calls
        ]
        if not batch_calls:
            break

        executed_this_round = False
        available_at_round_start = set(results_by_step)
        for call in batch_calls:
            if total_tool_calls >= MAX_DYNAMIC_TOOL_CALLS:
                return
            dependencies = [dep for dep in call.depends_on if dep]
            if dependencies and not all(dep in available_at_round_start for dep in dependencies):
                deferred_calls.append(call)
                continue
            if not _dependencies_satisfied(call, results_by_step):
                continue

            call = _prepare_dynamic_call(call, results_by_step, total_tool_calls + 1)
            signature = _tool_call_signature(call)
            if signature in executed_signatures:
                continue

            resolved_call = _resolve_call_args(call, results_by_step)
            result = run_domain_agent(context, resolved_call)
            if result.step_id:
                results_by_step[result.step_id] = result
            tool_results.append(result)
            executed_signatures.add(signature)
            total_tool_calls += 1
            executed_this_round = True
            yield result

            if result.status == "needs_input":
                return

        if not executed_this_round:
            break


def _ordered_tool_calls(plan: AgentPlan) -> list[AgentToolCall]:
    pending = list(plan.tool_calls)
    completed: set[str] = set()
    ordered: list[AgentToolCall] = []

    while pending:
        progressed = False
        remaining = []

        for call in pending:
            dependencies = [dep for dep in call.depends_on if dep]
            if all(dep in completed for dep in dependencies):
                ordered.append(call)
                if call.step_id:
                    completed.add(call.step_id)
                progressed = True
            else:
                remaining.append(call)

        if not progressed:
            # 计划校验阶段已经尽量清理非法依赖；这里保序执行剩余步骤，避免模型输出小瑕疵导致整轮请求中断。
            ordered.extend(remaining)
            break

        pending = remaining

    return ordered


def _prepare_dynamic_call(
    call: AgentToolCall,
    results_by_step: dict[str, AgentToolResult],
    step_number: int,
) -> AgentToolCall:
    existing_step_ids = set(results_by_step)
    step_id = call.step_id or f"dynamic_step_{step_number}"
    if step_id in existing_step_ids:
        step_id = _next_runtime_step_id(existing_step_ids, step_id)
    return replace(call, step_id=step_id)


def _dependencies_satisfied(
    call: AgentToolCall,
    results_by_step: dict[str, AgentToolResult],
) -> bool:
    dependencies = [dep for dep in call.depends_on if dep]
    return all(dep in results_by_step for dep in dependencies)


def _tool_call_signature(call: AgentToolCall) -> str:
    try:
        args = json.dumps(call.args, ensure_ascii=False, sort_keys=True)
    except TypeError:
        args = str(call.args)
    return f"{call.tool_name}:{args}"


def _next_runtime_step_id(existing_step_ids: set[str], base: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", base.lower()).strip("_") or "dynamic_step"
    suffix = 2
    candidate = f"{normalized}_{suffix}"
    while candidate in existing_step_ids:
        suffix += 1
        candidate = f"{normalized}_{suffix}"
    return candidate


def _resolve_call_args(
    call: AgentToolCall,
    results_by_step: dict[str, AgentToolResult],
) -> AgentToolCall:
    args = dict(call.args)

    if call.tool_name == "calligraphy_render_tool" and not args.get("text"):
        source = _resolve_text_source(args.get("text_source"), call.depends_on, results_by_step)
        if source:
            args["text"] = source

    return replace(call, args=args)


def _resolve_text_source(
    text_source: object,
    depends_on: list[str],
    results_by_step: dict[str, AgentToolResult],
) -> str:
    source = _resolve_reference(text_source, results_by_step)
    if source:
        return source

    for step_id in depends_on:
        result = results_by_step.get(step_id)
        if result and result.content:
            return result.content

    for result in reversed(list(results_by_step.values())):
        if result.tool_name in {"culture_qa_tool", "knowledge_base_tool"} and result.content:
            return result.content

    return ""


def _resolve_reference(
    value: object,
    results_by_step: dict[str, AgentToolResult],
) -> str:
    if not value:
        return ""

    reference = str(value).strip().strip("{}")
    if "." not in reference:
        result = results_by_step.get(reference)
        return result.content if result else ""

    step_id, path = reference.split(".", 1)
    result = results_by_step.get(step_id)
    if not result:
        return ""
    if path in {"content", "answer", "text", "poem_text", "result"}:
        return result.content

    current: Any = result.data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return ""

    if isinstance(current, str):
        return current
    if current is None:
        return ""
    return json.dumps(current, ensure_ascii=False)


def _answer_from_tool_results(
    context: AgentContext,
    plan: AgentPlan,
    tool_results: list[AgentToolResult],
) -> str:
    blocking = _first_needs_input(tool_results)
    if blocking:
        return _fallback_answer(tool_results)
    if _should_use_tool_answer_directly(tool_results):
        return _fallback_answer(tool_results)
    return _synthesize_answer(context, tool_results, plan.final_answer_instruction)


def _plan_payload(plan: AgentPlan) -> dict:
    return {
        "type": "agent",
        "videos": [],
        "tool_calls": [
            {
                "agent_name": get_domain_agent(call.tool_name).name,
                "agent_display_name": get_domain_agent(call.tool_name).display_name,
                "step_id": call.step_id,
                "goal": call.goal,
                "thought_summary": call.thought_summary,
                "depends_on": call.depends_on,
                "tool_name": call.tool_name,
                "tool_display_name": _tool_display_name(call.tool_name),
                "args": call.args,
                "reason": call.reason,
            }
            for call in _ordered_tool_calls(plan)
        ],
    }


def _tool_result_payload(result: AgentToolResult) -> dict:
    agent = get_domain_agent(result.tool_name)
    return {
        "agent_name": result.agent_name,
        "agent_display_name": agent.display_name,
        "step_id": result.step_id,
        "goal": result.goal,
        "thought_summary": result.thought_summary,
        "tool_name": result.tool_name,
        "tool_display_name": _tool_display_name(result.tool_name),
        "status": result.status,
        "content": result.content,
        "error": result.error,
    }


def _stream_needs_input(
    result: AgentToolResult,
    tool_results: list[AgentToolResult],
) -> Iterable[tuple[str, dict]]:
    answer = _fallback_answer(tool_results) or result.content
    final = _result_from_tools(answer, tool_results)
    yield ("delta", {"content": answer})
    yield ("meta", _agent_result_payload(final))
    yield ("done", {})


def _stream_direct_answer(tool_results: list[AgentToolResult]) -> Iterable[tuple[str, dict]]:
    answer = _fallback_answer(tool_results)
    if answer:
        yield ("delta", {"content": answer})


def _stream_answer_chunks(
    context: AgentContext,
    plan: AgentPlan,
    tool_results: list[AgentToolResult],
) -> Iterable[tuple[str, dict]]:
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
    serialized = [_model_visible_tool_result(result) for result in tool_results]
    return (
        f"User message:\n{context.message}\n\n"
        f"Final answer instruction:\n{instruction or 'Summarize the tool results.'}\n\n"
        "Tool observations JSON:\n"
        f"{json.dumps(serialized, ensure_ascii=False, indent=2)}\n\n"
        "When a tool result already contains a correctly ordered 【原文】 block, preserve that order in the final answer. "
        "Important: structured fields already include image URLs and media URLs. "
        "Do not repeat them in the natural-language answer."
    )


def _model_visible_tool_result(result: AgentToolResult) -> dict[str, Any]:
    return {
        "tool_name": result.tool_name,
        "agent_name": result.agent_name,
        "step_id": result.step_id,
        "goal": result.goal,
        "thought_summary": result.thought_summary,
        "status": result.status,
        "observation": _model_observation_text(result),
        "data": _model_observation_data(result),
        "error": result.error,
    }


def _model_observation_text(result: AgentToolResult) -> str:
    if result.status == "error":
        return result.error or "Tool call failed."
    if result.tool_name == "media_search_tool":
        videos = result.data.get("videos") or []
        if not videos:
            return "媒体检索完成，但未找到匹配的本地音视频资源。"
        titles = [
            str(item.get("video_name") or item.get("title") or item.get("file_name") or "").strip()
            for item in videos[:5]
            if isinstance(item, dict)
        ]
        titles = [title for title in titles if title]
        return f"媒体检索成功，找到 {len(videos)} 个资源：" + "、".join(titles)
    if result.tool_name == "calligraphy_render_tool":
        if result.status == "needs_input":
            return result.content
        missing = result.data.get("missing_chars") or []
        text = "书法生成成功，图片已通过结构化字段交给前端展示。"
        text += f" 风格：{result.data.get('style') or '未知'}；作者：{result.data.get('author') or '未知'}。"
        if missing:
            text += " 缺字：" + "、".join(str(item) for item in missing[:30])
        return text
    if result.tool_name == "short_video_script_tool":
        project = result.data.get("project") or {}
        scenes = project.get("scenes") or project.get("shots") or []
        return f"短剧脚本生成成功，标题：{project.get('title') or '未命名'}，分镜数量：{len(scenes)}。"
    return _truncate_model_text(result.content, 2200)


def _model_observation_data(result: AgentToolResult) -> dict[str, Any]:
    if result.tool_name == "media_search_tool":
        videos = result.data.get("videos") or []
        return {
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
        return {"title": project.get("title"), "scene_count": len(scenes)}
    if result.tool_name == "web_search_tool":
        results = result.data.get("results") or []
        return {
            "count": len(results),
            "results": [
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": _truncate_model_text(item.get("snippet") or "", 300),
                }
                for item in results[:5]
                if isinstance(item, dict)
            ],
        }
    if result.tool_name == "knowledge_base_tool":
        results = result.data.get("results") or result.data.get("hits") or []
        return {
            "count": len(results) if isinstance(results, list) else 0,
            "enabled": result.data.get("enabled"),
            "status": result.data.get("status"),
        }
    return {}


def _truncate_model_text(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _result_from_tools(answer: str, tool_results: list[AgentToolResult]) -> AgentResult:
    # 把各工具的私有 data 汇总成前端稳定使用的结构化字段。
    # 自然语言 answer 只负责表达，图片、媒体、来源、短剧项目都走结构化字段。
    videos = []
    auto_play = False
    calligraphy_image_url = None
    calligraphy_missing_chars: list[str] = []
    calligraphy_selection = None
    short_video_project = None
    sources = []

    for result in tool_results:
        if result.tool_name == "media_search_tool":
            videos = result.data.get("videos") or videos
            auto_play = bool(result.data.get("auto_play")) if videos else False
        elif result.tool_name == "calligraphy_render_tool":
            calligraphy_image_url = result.data.get("image_url") or calligraphy_image_url
            calligraphy_missing_chars = result.data.get("missing_chars") or calligraphy_missing_chars
            calligraphy_selection = result.data.get("selection") or calligraphy_selection
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
        elif result.tool_name == "short_video_script_tool":
            short_video_project = result.data.get("project") or short_video_project

    response_type = "agent"
    if calligraphy_image_url:
        response_type = "calligraphy"
    elif videos:
        response_type = "text_with_video"
    elif short_video_project:
        response_type = "short_video"

    return AgentResult(
        answer=answer,
        response_type=response_type,
        videos=videos,
        auto_play=auto_play,
        calligraphy_image_url=calligraphy_image_url,
        calligraphy_missing_chars=calligraphy_missing_chars,
        calligraphy_selection=calligraphy_selection,
        short_video_project=short_video_project,
        sources=sources,
        tool_calls=[
            {
                "agent_name": result.agent_name,
                "agent_display_name": get_domain_agent(result.tool_name).display_name,
                "step_id": result.step_id,
                "goal": result.goal,
                "thought_summary": result.thought_summary,
                "tool_name": result.tool_name,
                "tool_display_name": _tool_display_name(result.tool_name),
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
    # 书法和短剧工具本身已经产出完整结果时，避免再让综合模型改写格式。
    completed = [
        result
        for result in tool_results
        if result.status == "success" and result.tool_name != "culture_qa_tool"
    ]
    if len(tool_results) == 1:
        result = tool_results[0]
        if result.tool_name == "culture_qa_tool" and result.data.get("intent") == "greeting":
            return True
    return len(completed) == 1 and completed[0].tool_name in {
        "calligraphy_render_tool",
        "short_video_script_tool",
    }


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
        "calligraphy_selection": result.calligraphy_selection,
        "short_video_project": result.short_video_project,
        "sources": result.sources,
        "tool_calls": result.tool_calls,
    }


def _tool_display_name(tool_name: str) -> str:
    spec = get_tool_spec(tool_name)
    return spec.display_name if spec else tool_name
