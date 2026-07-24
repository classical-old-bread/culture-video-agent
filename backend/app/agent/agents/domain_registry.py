from __future__ import annotations

from dataclasses import dataclass

from app.agent.schemas import AgentContext, AgentToolCall, AgentToolResult
from app.agent.tool_registry import execute_tool, iter_tool_specs


@dataclass(frozen=True)
class DomainAgent:
    name: str
    display_name: str
    description: str
    tool_names: tuple[str, ...]

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in self.tool_names

    def run(self, context: AgentContext, call: AgentToolCall) -> AgentToolResult:
        result = execute_tool(context, call)
        result.agent_name = self.name
        result.thought_summary = call.thought_summary
        result.step_id = call.step_id
        result.goal = call.goal
        return result


def _build_domain_agents() -> tuple[DomainAgent, ...]:
    domains: dict[str, dict[str, object]] = {}
    for spec in iter_tool_specs():
        domain = domains.setdefault(
            spec.domain_name,
            {
                "display_name": spec.domain_display_name,
                "description": spec.domain_description,
                "tool_names": [],
            },
        )
        tool_names = domain["tool_names"]
        if isinstance(tool_names, list):
            tool_names.append(spec.name)

    return tuple(
        DomainAgent(
            name=name,
            display_name=str(data["display_name"]),
            description=str(data["description"]),
            tool_names=tuple(data["tool_names"]) if isinstance(data["tool_names"], list) else (),
        )
        for name, data in domains.items()
    )


DOMAIN_AGENTS: tuple[DomainAgent, ...] = _build_domain_agents()


def get_domain_agent(tool_name: str) -> DomainAgent:
    for agent in DOMAIN_AGENTS:
        if agent.can_handle(tool_name):
            return agent
    return DomainAgent(
        name="tool_agent",
        display_name="通用工具 Agent",
        description="负责执行未显式归类的工具。",
        tool_names=(tool_name,),
    )


def run_domain_agent(context: AgentContext, call: AgentToolCall) -> AgentToolResult:
    return get_domain_agent(call.tool_name).run(context, call)
