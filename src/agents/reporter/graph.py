from dataclasses import dataclass, field
from typing import Annotated
from langchain.agents import create_agent

from src.agents.common.toolkits.mysql import get_mysql_tools
from src.agents.common import BaseAgent, load_chat_model, BaseContext
from src.agents.common.tools import get_tools_from_context, gen_tool_info, get_buildin_tools
from src.utils import logger
from .middlewares.sql_retrieval_middleware import SqlRetrievalMiddleware
from src.agents.common.middlewares import TaskSkillMiddleware

# _mcp_servers = {"mcp-server-chart": {"command": "npx", "args": ["-y", "@antv/mcp-server-chart"], "transport": "stdio"}}
SQL_PAIRS_KB_ID = "kb_8d6732060fbf23a102aab44a50ffe953"


@dataclass(kw_only=True)
class ReporterContext(BaseContext):
    # 覆盖默认的工具列表，添加 MySQL 工具包
    tools: Annotated[list[dict], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=lambda: [t.name for t in get_mysql_tools()],
        metadata={
            "name": "工具",
            # 添加额外的 MySQL 工具包选项
            "options": lambda: gen_tool_info(get_buildin_tools() + get_mysql_tools()),
            "description": "包含内置的工具，以及用于数据库报表生成的 MySQL 工具包。",
        },
    )
    knowledges: list[str] = field(
        default_factory=list,
        metadata={
            "name": "知识库",
            "options": lambda: [],
            "description": "知识库列表，可以在左侧知识库页面中创建知识库。",
            "type": "list",  # Explicitly mark as list type for frontend if needed
        },
    )


    def __post_init__(self):
        self.mcps = ["mcp-server-chart"]  # 默认启用 Charts MCPs


class SqlReporterAgent(BaseAgent):
    name = "数据库报表助手"
    description = "一个能够生成 SQL 查询报告的智能体助手。同时调用 Charts MCP 生成图表。"
    context_schema = ReporterContext

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        if self.graph:
            return self.graph

        context = self.context_schema.from_file(module_name=self.module_name)
        
        # 创建 SqlReporterAgent
        graph = create_agent(
            model=load_chat_model(context.model),  # 使用 context 中的模型配置
            tools=await get_tools_from_context(context, extra_tools=get_mysql_tools()),
            system_prompt=context.system_prompt,
            middleware=[
                # TaskSkillMiddleware(),
                # SqlRetrievalMiddleware(SQL_PAIRS_KB_ID)
            ],
            checkpointer=await self._get_checkpointer(),
        )

        self.graph = graph
        logger.info("SqlReporterAgent 构建成功")
        return graph
