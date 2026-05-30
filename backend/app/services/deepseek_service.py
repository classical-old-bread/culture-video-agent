from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.prompts.system_prompt import CULTURE_SYSTEM_PROMPT
from app.services.text_cleaner import clean_answer_text


def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    if not settings.deepseek_api_key or settings.deepseek_api_key == "your_deepseek_api_key":
        raise RuntimeError("DeepSeek API Key 未配置，请在 backend/.env 中填写 DEEPSEEK_API_KEY。")

    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        temperature=0.7,
    )


def generate_answer_with_context(prompt: str) -> str:
    try:
        llm = _get_llm()
        response = llm.invoke(
            [
                SystemMessage(content=CULTURE_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        return clean_answer_text(str(response.content))
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("DeepSeek API 调用失败，请检查 API Key、网络和模型配置。") from exc
