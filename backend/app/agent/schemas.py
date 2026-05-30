from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ToolStatus = Literal["success", "needs_input", "skipped", "error"]

@dataclass
class AgentToolCall:
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass
class AgentPlan:
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    final_answer_instruction: str = ""


@dataclass
class AgentToolResult:
    tool_name: str
    status: ToolStatus
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class AgentResult:
    answer: str
    response_type: str = "agent"
    videos: list[dict[str, Any]] = field(default_factory=list)
    auto_play: bool = False
    calligraphy_image_url: str | None = None
    calligraphy_missing_chars: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentContext:
    message: str
    conversation_context: str | None = None
    calligraphy_source_text: str | None = None
    calligraphy_style: str | None = None
    calligraphy_author: str | None = None
    db: Any = None
