from __future__ import annotations

# Callable 用于标注工具注册表里每个工具函数的统一调用签名。
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.agent.tools.calligraphy_tool import calligraphy_render_tool
from app.agent.tools.culture_qa_tool import culture_qa_tool
from app.agent.tools.knowledge_base_tool import knowledge_base_tool
from app.agent.tools.media_tool import media_search_tool
from app.agent.tools.short_video_tool import short_video_script_tool
from app.agent.tools.web_search_tool import web_search_tool


ToolHandler = Callable[[AgentContext, AgentToolCall], AgentToolResult]


@dataclass(frozen=True)
class ToolArgSpec:
    type: str
    description: str
    required: bool = False
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    nullable: bool = False
    fixed: Any = None

    def planner_type(self) -> str:
        value = self.type
        if self.nullable:
            value = f"{value}|null"
        if self.fixed is not None:
            return repr(self.fixed).lower() if isinstance(self.fixed, bool) else repr(self.fixed)
        return value

@dataclass(frozen=True)
class ToolSpec:
    name: str
    display_name: str
    description: str
    domain_name: str
    domain_display_name: str
    domain_description: str
    args_schema: dict[str, ToolArgSpec]
    handler: ToolHandler
    default_step_id: str
    default_goal: str
    planner_notes: tuple[str, ...] = field(default_factory=tuple)

    def args_for_prompt(self) -> str:
        args = {
            name: spec.planner_type()
            for name, spec in self.args_schema.items()
        }
        return "{" + ", ".join(f'"{name}": {value}' for name, value in args.items()) + "}"

    def prompt_block(self) -> str:
        lines = [
            f"- {self.name}（{self.display_name}）",
            f"  所属领域：{self.domain_display_name}",
            f"  用途：{self.description}",
            f"  args: {self.args_for_prompt()}",
        ]
        lines.extend(f"  注意：{note}" for note in self.planner_notes)
        return "\n".join(lines)

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="culture_qa_tool",
        display_name="文化问答",
        description="用于传统文化、诗词、民俗、书法知识、寒暄问候和文化解释。",
        domain_name="culture_agent",
        domain_display_name="文化问答 Agent",
        domain_description="负责传统文化、诗词典故、民俗背景和常规解释。",
        args_schema={
            "question": ToolArgSpec("string", "用户问题；需要结合最近对话补全代词和省略主语。", required=True),
        },
        handler=culture_qa_tool,
        default_step_id="culture_answer",
        default_goal="回答文化问题或完成内容赏析",
    ),
    ToolSpec(
        name="web_search_tool",
        display_name="联网搜索",
        description="当用户要求联网搜索、来源、参考资料、最新/当前信息或网页内容时使用。",
        domain_name="research_agent",
        domain_display_name="资料检索 Agent",
        domain_description="负责本地知识库和联网搜索，并整理可引用来源。",
        args_schema={
            "query": ToolArgSpec("string", "联网检索查询词。", required=True),
            "max_results": ToolArgSpec("number", "返回结果数量。", default=5, minimum=1, maximum=8),
        },
        handler=web_search_tool,
        default_step_id="web_search",
        default_goal="检索联网资料和来源",
    ),
    ToolSpec(
        name="calligraphy_render_tool",
        display_name="书法生成",
        description="当用户想生成书法图片/书法作品，或正在补全上一轮书法风格/作者选择时使用。",
        domain_name="calligraphy_agent",
        domain_display_name="书法生成 Agent",
        domain_description="负责书法文本、风格、作者选择和图片生成。",
        args_schema={
            "text": ToolArgSpec("string", "要写入书法作品的文本；缺失时传 null。", nullable=True),
            "text_source": ToolArgSpec("string", "依赖前序步骤正文时使用，例如 culture_answer.content。", nullable=True),
            "style": ToolArgSpec("string", "书法风格；缺失时传 null。", nullable=True),
            "author": ToolArgSpec("string", "书法作者；缺失时传 null。", nullable=True),
        },
        handler=calligraphy_render_tool,
        default_step_id="calligraphy_render",
        default_goal="生成书法作品图片",
        planner_notes=(
            "如果文本、风格或作者缺失，对应字段传 null，不要猜测；工具会要求用户补充。",
            "如果用户说“这首诗/上面的内容/刚才那个”，可以把 text 设为 null 或用 text_source 引用前序正文。",
        ),
    ),
    ToolSpec(
        name="media_search_tool",
        display_name="媒体检索",
        description="当本地音视频资源可以丰富回答时使用，尤其是具体民歌、地方音乐、表演形式或可供查看的文化作品。",
        domain_name="media_agent",
        domain_display_name="媒体检索 Agent",
        domain_description="负责本地音频、视频等文化资源检索。",
        args_schema={
            "query": ToolArgSpec("string", "简洁查询词，包含作品/主题名和文化类别。", required=True),
            "auto_play": ToolArgSpec("boolean", "是否自动播放；必须为 false。", default=False, fixed=False),
            "limit": ToolArgSpec("number", "返回资源数量。", default=3, minimum=1, maximum=10),
            "prefer_video": ToolArgSpec("boolean", "是否优先视频资源。", default=True),
        },
        handler=media_search_tool,
        default_step_id="media_search",
        default_goal="检索本地音视频资源",
        planner_notes=("即使用户说播放、听、看，auto_play 也必须设为 false，由界面等待用户点击。",),
    ),
    ToolSpec(
        name="knowledge_base_tool",
        display_name="知识库检索",
        description="当用户要求使用本地整理资料、知识库、项目文档，或明确要求根据本地资料回答时使用。",
        domain_name="research_agent",
        domain_display_name="资料检索 Agent",
        domain_description="负责本地知识库和联网搜索，并整理可引用来源。",
        args_schema={
            "query": ToolArgSpec("string", "本地知识库检索查询词。", required=True),
            "top_k": ToolArgSpec("number", "返回片段数量。", default=4, minimum=1, maximum=12),
        },
        handler=knowledge_base_tool,
        default_step_id="knowledge_search",
        default_goal="检索本地知识库资料",
        planner_notes=("它是证据来源，不是最终兜底工具；通常需要 culture_qa_tool 补充综合回答。",),
    ),
    ToolSpec(
        name="short_video_script_tool",
        display_name="短剧脚本",
        description="当用户要求创作短剧、短视频脚本、动画分镜、小剧场、AI 视频提示词时使用。",
        domain_name="short_video_agent",
        domain_display_name="短视频创作 Agent",
        domain_description="负责短剧脚本、分镜和 AI 视频提示词生成。",
        args_schema={
            "topic": ToolArgSpec("string", "短剧或短视频主题。", required=True),
        },
        handler=short_video_script_tool,
        default_step_id="short_video_script",
        default_goal="生成短剧脚本和分镜方案",
    ),
)


TOOL_REGISTRY: dict[str, ToolHandler] = {
    spec.name: spec.handler
    for spec in TOOL_SPECS
}

TOOL_SPEC_REGISTRY: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in TOOL_SPECS
}


def get_tool_spec(tool_name: str) -> ToolSpec | None:
    return TOOL_SPEC_REGISTRY.get(tool_name)


def iter_tool_specs() -> tuple[ToolSpec, ...]:
    return TOOL_SPECS


def render_tool_specs_for_planner() -> str:
    return "\n".join(spec.prompt_block() for spec in TOOL_SPECS)


def execute_tool(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    # 工具注册表是 Agent 编排层和具体业务能力之间的边界。
    # 这里统一把异常转换成 AgentToolResult，避免单个工具失败中断整轮请求。
    spec = get_tool_spec(call.tool_name)
    if not spec:
        return AgentToolResult(
            tool_name=call.tool_name,
            status="error",
            error=f"Unknown tool: {call.tool_name}",
        )
    try:
        return spec.handler(context, call)
    except RuntimeError as exc:
        return AgentToolResult(tool_name=call.tool_name, status="error", error=str(exc))
    except Exception as exc:
        return AgentToolResult(tool_name=call.tool_name, status="error", error=f"{type(exc).__name__}: {exc}")
