from __future__ import annotations

import json
import re
from typing import Any, Iterable

# LangChain 消息对象和 OpenAI-compatible ChatOpenAI 封装，用于调用 DeepSeek。
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.services.text_cleaner import clean_answer_chunk, clean_answer_text


def get_agent_llm(
    *,
    temperature: float = 0.2,
    streaming: bool = False,
    model: str | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    api_key = settings.deepseek_api_key
    if not api_key or api_key == "your_deepseek_api_key":
        raise RuntimeError("DeepSeek API Key is not configured.")

    return ChatOpenAI(
        model=model or settings.agent_model,
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        temperature=temperature,
        streaming=streaming,
    )


def invoke_agent_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.2,
    model: str | None = None,
) -> str:
    llm = get_agent_llm(temperature=temperature, model=model)
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])
    return clean_answer_text(str(response.content))


def stream_agent_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.5,
    model: str | None = None,
) -> Iterable[str]:
    llm = get_agent_llm(temperature=temperature, streaming=True, model=model)
    for chunk in llm.stream([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]):
        content = clean_answer_chunk(str(chunk.content or ""))
        if content:
            yield content


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))
