from __future__ import annotations

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.services.deepseek_service import generate_answer_with_context


def culture_qa_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    question = str(call.args.get("question") or context.message).strip()
    answer = generate_answer_with_context(_build_contextual_prompt(context, question))
    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=answer,
        data={"question": question},
    )


def _build_contextual_prompt(context: AgentContext, question: str) -> str:
    conversation = context.conversation_context or ""
    return (
        "你正在作为传统文化 Agent 的 culture_qa_tool 回答问题。\n"
        "请严格遵守以下规则：\n"
        "1. 如果用户使用代词或承接上一轮内容，请结合最近对话判断指代对象。\n"
        "2. 如果用户要求已有古典公版作品的正文，且你能确认内容准确，可以先输出正文再解析。\n"
        "3. 如果作品是近现代作品、版权状态不确定，或你不能确认全文准确，不要给出全文或长段原文；"
        "请给出概要、背景、赏析，并提示用户可粘贴原文后再逐句解析或生成书法。\n"
        "4. 不要为了满足书法生成而编造原文。\n\n"
        f"最近对话：\n{conversation}\n\n"
        f"用户当前问题：\n{question}"
    )
