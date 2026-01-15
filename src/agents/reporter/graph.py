from langchain.agents import create_agent

from src.agents.common.middlewares import TaskSkillMiddleware
from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.toolkits.mysql import get_mysql_tools
from src.services.mcp_service import get_mcp_tools
from src.utils import logger
from .middlewares.sql_retrieval_middleware import SqlRetrievalMiddleware
from .context import Context
from .tools import get_tools

# _mcp_servers = {"mcp-server-chart": {"command": "npx", "args": ["-y", "@antv/mcp-server-chart"], "transport": "stdio"}}

SQL_PAIRS_KB_ID = "kb_8d6732060fbf23a102aab44a50ffe953"

class SqlReporterAgent(BaseAgent):
    name = "数据库报表助手"
    description = "一个能够生成 SQL 查询报告的智能体助手。同时调用 Charts MCP 生成图表。"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.context_schema = Context

    async def get_tools(self):
        mysql_tools = get_mysql_tools()
        chart_tools = await get_mcp_tools("mcp-server-chart")
        return mysql_tools + chart_tools

    async def get_graph(self, **kwargs):
        if self.graph:
            return self.graph

        context = self.context_schema.from_file(module_name=self.module_name)

        # 创建 SqlReporterAgent
        graph = create_agent(
            model=load_chat_model(context.model),  # 使用 context 中的模型配置
            system_prompt=context.system_prompt,
            # tools=await self.get_tools(),
            tools=await self.get_tools(context.tools, context.mcps),
            checkpointer=await self._get_checkpointer(),
            middleware=[
                TaskSkillMiddleware(),
                SqlRetrievalMiddleware(SQL_PAIRS_KB_ID)
            ]
        )

        self.graph = graph
        logger.info("SqlReporterAgent 构建成功")
        return graph
