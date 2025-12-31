from dataclasses import dataclass, field
from typing import Annotated

from src.agents.common import BaseContext, gen_tool_info
from src.agents.common.mcp import MCP_SERVERS
from src.knowledge import knowledge_base

from .tools import get_tools


@dataclass(kw_only=True)
class Context(BaseContext):
    tools: Annotated[list[dict], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=list,
        metadata={
            "name": "工具",
            "options": lambda: gen_tool_info(get_tools()),  # 这里的选择是所有的工具
            "description": "内置的部分工具，包含 common 工具和本智能体的特有工具（不含 MCP）。",
        },
    )

    mcps: list[str] = field(
        default_factory=list,
        metadata={
            "name": "MCP服务器",
            "options": lambda: list(MCP_SERVERS.keys()),
            "description": (
                "MCP服务器列表，建议使用支持 SSE 的 MCP 服务器，"
                "如果需要使用 uvx 或 npx 运行的服务器，也请在项目外部启动 MCP 服务器，并在项目中配置 MCP 服务器。"
            ),
        },
    )
