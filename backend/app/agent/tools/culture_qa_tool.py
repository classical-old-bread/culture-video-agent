from __future__ import annotations

import re

from app.agent.llm import invoke_agent_llm
from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.config import get_settings
from app.prompts.system_prompt import CULTURE_SYSTEM_PROMPT


def culture_qa_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    question = str(call.args.get("question") or context.message).strip()
    if _is_simple_greeting(question):
        return AgentToolResult(
            tool_name=call.tool_name,
            status="success",
            content="你好，我是传统文化导览员。你可以问传统节日、诗词典故、地方民俗，也可以生成书法作品、短剧脚本或查找本地民歌媒体。",
            data={"question": question, "intent": "greeting"},
        )

    answer = _generate_culture_answer(_build_contextual_prompt(context, question))
    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=answer,
        data={"question": question},
    )


def _generate_culture_answer(prompt: str) -> str:
    settings = get_settings()
    try:
        return invoke_agent_llm(
            CULTURE_SYSTEM_PROMPT,
            prompt,
            temperature=0.7,
            model=settings.deepseek_model,
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("DeepSeek API 调用失败，请检查 API Key、网络和模型配置。") from exc


def _build_contextual_prompt(context: AgentContext, question: str) -> str:
    conversation = context.conversation_context or ""
    return (
        "你正在作为传统文化 Agent 的 culture_qa_tool 回答问题。\n"
        "请严格遵守以下规则：\n"
        "1. 如果用户使用代词或承接上一轮内容，请结合最近对话判断指代对象。\n"
        "2. 如果用户要求已有作品的正文，且你能确认内容准确，可以先输出正文再解析。\n"
        "3. 如果问题同时包含生成书法、写成书法、书法作品等后续制作意图，必须先给出可确认准确的【原文】区块，原文区块只放题名和正文。\n"
        "4. 如果你不能确认全文准确，不要给出全文或长段原文；"
        "请给出概要、背景、赏析，并提示用户可粘贴原文后再逐句解析或生成书法。\n"
        "5. 不要为了满足书法生成而编造原文。\n\n"
        f"最近对话：\n{conversation}\n\n"
        f"用户当前问题：\n{question}"
    )


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
