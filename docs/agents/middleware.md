# 中间件系统

中间件是扩展智能体行为的重要机制。系统基于 LangChain 1.0 的中间件标准，支持在关键节点插入自定义逻辑。

## 核心中间件

### 运行时配置准备

当前版本不再使用单独的旧版运行时配置中间件。内置 Agent 在创建 Graph 前完成运行时配置准备：

- `prepare_agent_runtime_context`：按当前用户权限过滤工具、知识库、MCP 和 Skills，并派生 `_visible_knowledge_bases`、`_prompt_skills`、`_readable_skills`
- `build_prompt_with_context`：基于 Context 生成系统提示词
- `load_chat_model(context.model)`：加载主模型
- `resolve_configured_runtime_tools(context)`：加载已配置的内置工具和 MCP 工具

### save_attachments_to_fs

支持文件上传功能的中间件。如果智能体需要处理用户上传的文档，可以启用此中间件：

```python
from yuxi.agents.middlewares import save_attachments_to_fs
from yuxi.agents.middlewares.knowledge_base import KnowledgeBaseMiddleware
from yuxi.agents.middlewares.skills import SkillsMiddleware

async def get_graph(self):
    graph = create_agent(
        model=load_chat_model("..."),
        tools=tools,
        middleware=[
            save_attachments_to_fs,
            KnowledgeBaseMiddleware(),
            SkillsMiddleware(),
        ],
        checkpointer=await self._get_checkpointer(),
    )
    return graph
```

### 启用文件上传

启用文件上传能力需要两步：

1. 在智能体类中声明 `capabilities = ["file_upload"]`
2. 在 Graph 的 `middleware` 列表中加入 `save_attachments_to_fs`

### KnowledgeBaseMiddleware

根据运行时 `_visible_knowledge_bases` 暴露知识库工具，包括 `list_kbs`、`query_kb`、`find_kb_document`、`open_kb_document` 和 `get_mindmap`。知识库可见范围已经在 Graph 创建前按当前用户和 Agent 配置过滤。

### SkillsMiddleware

负责 Skills 的请求级提示词注入、Skill 激活校验，以及激活后按需加载 `tool_dependencies` 和 `mcp_dependencies`。它读取 `prepare_agent_runtime_context` 派生出的 `_prompt_skills` 与 `_readable_skills`，不会把 Skills 提示永久写回 Context。

### 子智能体与摘要

主 Agent 在配置了子智能体时会挂载 Yuxi task middleware，用真实子 Agent graph 执行任务；子智能体自身不会继续挂载下一层子智能体。长对话压缩使用 DeepAgents 的 SummarizationMiddleware，由 Yuxi 的 `create_summary_middleware` 封装接入。

## 自定义中间件

新增中间件时，将其放入 `backend/package/yuxi/agents/middlewares` 目录，然后在智能体的 `middleware` 列表中引用即可。该目录下已内置知识库挂载（`knowledge_base`）、Skills 注入（`skills`）、附件上下文（`attachment`）、子智能体任务（`subagent_task`）、上下文压缩（`summary`）、动态工具（`dynamic_tool`）等中间件。
