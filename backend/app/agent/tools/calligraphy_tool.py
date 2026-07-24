from __future__ import annotations

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.services.calligraphy_service import (
    choose_calligraphy_source,
    find_styles_for_author,
    list_calligraphy_styles,
    list_calligraphy_authors,
    render_calligraphy_work,
)


MISSING_SOURCE_TEXT_MESSAGE = "没有识别到可用于书法生成的正文。请提供要写入作品的原文，或先让文化问答给出作品原文后再生成书法。"


def calligraphy_render_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    explicit_text = _clean_optional(call.args.get("text"))
    raw_text = str(explicit_text or context.calligraphy_source_text or context.message).strip()
    style = _clean_optional(call.args.get("style")) or context.calligraphy_style
    author = _clean_optional(call.args.get("author")) or context.calligraphy_author

    if author and not style:
        author_styles = find_styles_for_author(author)
        if len(author_styles) == 1:
            style = author_styles[0]

    if style and author and author not in list_calligraphy_authors(style):
        author_styles = find_styles_for_author(author)
        if len(author_styles) == 1:
            style = author_styles[0]
        else:
            author = None

    if not style or not author:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="needs_input",
            content=_selection_message(style, author),
            data={
                "text": raw_text,
                "style": style,
                "author": author,
                "selection": _selection_payload(style, author),
            },
        )

    source_text = choose_calligraphy_source(context.message, explicit_text or context.calligraphy_source_text or raw_text)
    if not source_text:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="needs_input",
            content=MISSING_SOURCE_TEXT_MESSAGE,
            data={
                "text": "",
                "style": style,
                "author": author,
            },
        )

    try:
        result = render_calligraphy_work(
            context.db,
            text=source_text,
            style=style,
            author=author,
        )
    except RuntimeError as exc:
        if "No valid text" not in str(exc):
            raise
        return AgentToolResult(
            tool_name=call.tool_name,
            status="needs_input",
            content=MISSING_SOURCE_TEXT_MESSAGE,
            data={
                "text": "",
                "style": style,
                "author": author,
            },
        )

    answer = f"已按 {result.style} / {result.author} 风格生成书法作品。"
    if result.missing_chars:
        answer += " 字库缺少部分字符，已自动留空处理：" + "、".join(result.missing_chars[:40])

    return AgentToolResult(
        tool_name=call.tool_name,
        status="success",
        content=answer,
        data={
            "image_url": result.image_url,
            "style": result.style,
            "author": result.author,
            "text": result.text,
            "missing_chars": result.missing_chars,
        },
    )


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "undefined", "string"}:
        return None
    return text


def _selection_message(style: str | None, author: str | None) -> str:
    if not style and not author:
        return "生成书法前，请先选择书法风格和作者。"
    if not style:
        return "生成书法前，还需要选择书法风格。"
    return f"已选择 {style}，还需要选择书法作者。"


def _selection_payload(style: str | None, author: str | None) -> dict:
    styles = list_calligraphy_styles()
    authors = list_calligraphy_authors(style) if style else []
    groups = [
        {
            "style": style_name,
            "authors": list_calligraphy_authors(style_name)[:40],
        }
        for style_name in styles[:30]
    ]
    return {
        "style": style,
        "author": author,
        "needs": "style" if not style else "author",
        "styles": styles[:30],
        "authors": authors[:40],
        "groups": groups,
        "options": [
            {
                "type": "style",
                "label": group["style"],
                "value": group["style"],
                "authors": group["authors"],
            }
            for group in groups
        ]
        if not style
        else [
            {"type": "author", "label": item, "value": item, "style": style}
            for item in authors[:40]
        ],
    }
