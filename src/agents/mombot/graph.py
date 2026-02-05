from deepagents.backends import CompositeBackend, StateBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain.agents.middleware import HumanInTheLoopMiddleware
from datetime import datetime

from .context import MOMBotContext

from src.agents.common import BaseAgent, load_chat_model
from src.agents.common.backends.minio_backend import MinIOBackend
from src.agents.common.middlewares import (
    RuntimeConfigMiddleware,
    save_attachments_to_fs,
)
from src.services.mcp_service import get_tools_from_all_servers
from src.agents.common.toolkits.mom.tools import get_mom_tools


class MOMbotAgent(BaseAgent):
    name = "智能体助手"
    description = "基础的对话机器人，可以回答问题，可在配置中启用需要的工具。"
    capabilities = ["file_upload"]  # 支持文件上传功能
    context_schema: type[MOMBotContext] = MOMBotContext  # 智能体上下文 schema

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """构建图"""
        context = self.context_schema()
        all_mcp_tools = (
            await get_tools_from_all_servers()
        )  # 因为异步加载，无法放在 RuntimeConfigMiddleware 的 __init__ 中

        # 使用 create_agent 创建智能体
        # 注意：tools 参数由 RuntimeConfigMiddleware 在 wrap_model_call 中动态设置
        graph = create_agent(
            model=load_chat_model(context.model),
            system_prompt=context.system_prompt,
            middleware=[
                save_attachments_to_fs,  # 附件保存到文件系统
                # FilesystemMiddleware(backend=_create_fs_backend_factory, tool_token_limit_before_evict=5000),
                RuntimeConfigMiddleware(extra_tools=all_mcp_tools + get_mom_tools()),  # 运行时配置应用（模型/工具/知识库/MCP/提示词）
                ModelRetryMiddleware(),  # 模型重试中间件
                HumanInTheLoopMiddleware({ # 人工审批中间件
                    "add_mom_system_news": True
                    # "执行 SQL 查询": True, 
                    # "计算器": True, 
                })
            ],
            checkpointer=await self._get_checkpointer(),
        )

        return graph


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())
