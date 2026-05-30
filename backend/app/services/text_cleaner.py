from __future__ import annotations

import re


MARKDOWN_SYMBOL_PATTERN = re.compile(r"[*#`>~]")
LINE_BULLET_PATTERN = re.compile(r"(?m)^\s*[-+]\s+")
EXTRA_SPACE_PATTERN = re.compile(r"[ \t]{2,}")
EXTRA_BLANK_LINE_PATTERN = re.compile(r"\n{3,}")


def clean_answer_text(text: str) -> str:
    """清理模型回答中的 Markdown 装饰符号，保留正常中文标点。"""
    if not text:
        return ""

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = LINE_BULLET_PATTERN.sub("", cleaned)
    cleaned = cleaned.replace("|", " ")
    cleaned = MARKDOWN_SYMBOL_PATTERN.sub("", cleaned)
    cleaned = EXTRA_SPACE_PATTERN.sub(" ", cleaned)
    cleaned = EXTRA_BLANK_LINE_PATTERN.sub("\n\n", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.split("\n"))

    return cleaned.strip()


def clean_answer_chunk(text: str) -> str:
    """流式输出时按片段清理 Markdown 装饰符号，不移除正常标点。"""
    if not text:
        return ""

    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = cleaned.replace("|", " ")
    cleaned = MARKDOWN_SYMBOL_PATTERN.sub("", cleaned)
    cleaned = EXTRA_SPACE_PATTERN.sub(" ", cleaned)
    return cleaned
