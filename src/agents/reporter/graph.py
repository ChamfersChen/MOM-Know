from langchain.agents import create_agent

from src.agents.common.middlewares import TaskSkillMiddleware
from src.agents.common import BaseAgent, get_mcp_tools, load_chat_model
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

    async def get_tools(self, tools: list[str] = None, mcps=None, knowledges=None, **kwargs):
        # 1. 基础工具 (从 context.tools 中筛选)
        all_basic_tools = get_tools()
        selected_tools = []

        if tools:
            # 创建工具映射表
            tools_map = {t.name: t for t in all_basic_tools}
            for tool_name in tools:
                if tool_name in tools_map:
                    selected_tools.append(tools_map[tool_name])
        else:
            selected_tools = all_basic_tools

        # 2. MCP 工具
        if mcps:
            for server_name in mcps:
                mcp_tools = await get_mcp_tools(server_name)
                selected_tools.extend(mcp_tools)

        return selected_tools

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
