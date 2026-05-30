from __future__ import annotations

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.services.calligraphy_service import (
    build_calligraphy_selection_prompt,
    choose_calligraphy_source,
    find_styles_for_author,
    list_calligraphy_authors,
    render_calligraphy_work,
)


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
            content=build_calligraphy_selection_prompt(style, author),
            data={"text": raw_text, "style": style, "author": author},
        )

    source_text = choose_calligraphy_source(context.message, explicit_text or context.calligraphy_source_text or raw_text)
    result = render_calligraphy_work(
        context.db,
        text=source_text,
        style=style,
        author=author,
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
