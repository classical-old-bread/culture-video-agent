from __future__ import annotations

# dataclass 让 Agent 内部的计划、上下文和结果对象保持轻量结构化。
from dataclasses import dataclass, field
from typing import Any, Literal


ToolStatus = Literal["success", "needs_input", "skipped", "error"]
NextActionType = Literal["call_tools", "finish"]

# default_factory 用来为字段提供“每个实例独立”的默认值工厂，常用于可变类型（list、dict 等），避免所有实例共享同一个对象。
@dataclass
class AgentToolCall:
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    thought_summary: str = ""
    step_id: str = ""
    goal: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class AgentPlan:
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    final_answer_instruction: str = ""


@dataclass
class AgentNextAction:
    action: NextActionType
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    final_answer_instruction: str = ""
    thought_summary: str = ""
    reason: str = ""


@dataclass
class AgentToolResult:
    tool_name: str
    status: ToolStatus
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    agent_name: str = ""
    thought_summary: str = ""
    step_id: str = ""
    goal: str = ""


@dataclass
class AgentResult:
    answer: str
    response_type: str = "agent"
    videos: list[dict[str, Any]] = field(default_factory=list)
    auto_play: bool = False
    calligraphy_image_url: str | None = None
    calligraphy_missing_chars: list[str] = field(default_factory=list)
    calligraphy_selection: dict[str, Any] | None = None
    short_video_project: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentContext:
    message: str
    conversation_context: str | None = None
    calligraphy_source_text: str | None = None
    calligraphy_style: str | None = None
    calligraphy_author: str | None = None
    short_video_character_profile: str | None = None
    db: Any = None
