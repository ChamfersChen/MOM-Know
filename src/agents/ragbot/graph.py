# from src.rag.dify import DifyProvider
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict
from src import config
from src.agents.common import BaseAgent, load_chat_model
from src.knowledge import knowledge_base
from src.utils import parse_json, format_prompt
from src.utils.logging_config import logger
from pydantic import BaseModel, Field

from dotenv import load_dotenv
load_dotenv()

DB_CHECK_PROMPT = """你是一个知识库判断助手，请根据用户输入的查询内容和知识库描述信息，判断是否需要检索知识库，并返回结果。
{{kb_description}}\n"
请按照如下JSON格式返回结果：\n"
```json\n"
{
  \"need_retrieval\": \"是否需要检索知识库(True, False)\",
  \"kb_names\": [\"知识库名称列表(如果不需要检索则为空)\"]
}
```
# 用户问题
{{query}}"""

class RagState(TypedDict):
    messages: list[str]
    kb_names: list[str] = []


    

class RagbotAgent(BaseAgent):
    name = "知识库问答助手"
    description = "基于知识库的问答智能体。"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm = load_chat_model(config.default_model)  # 实际会被覆盖
        self.llm_no_stream = load_chat_model(config.default_model, stream=False, verbose=False) # .with_structured_output(CheckDB)

    async def get_graph(self, **kwargs):
        """构建图"""
        cpt = await self._get_checkpointer()
        kb_instance = knowledge_base.kb_instances.get("milvus")
        
        def _should_retrieval(state: RagState):
            if not kb_instance:
                return "summary_node"
            return "judge_retrieval_node"


        def _retrieval_node(state: RagState):
            """知识图谱检索节点"""

            messages = state.get("messages",[])
            if not messages:
                return {"messages": messages}
            
            if state["kb_names"]:
                results = []
                for kb_id in state["kb_names"]:
                    chunks = kb_instance.query(messages[-1].content, db_id=kb_id)
                    results.extend([chunk['content'] for chunk in chunks])
            else:
                results = []

            if not results:
                return {"messages": messages}

            _msg = "## 上下文\n"+"\n".join(results) + "\n## 用户需求\n" + messages[-1].content
            messages[-1] = {'role':'user', 'content': _msg}
            return {"messages": messages}

        def _summary_node(state: RagState):
            messages = state.get("messages")
            return {
                "messages": [self.llm.invoke(messages)]
            }

        def _judge_retrieval_node(state: RagState):
            """知识图谱检索节点"""
            messages = state.get("messages",[])
            if not messages:
                return {"messages": messages}
            query = messages[-1].content
            kb_descriptions = []
            map_name_id = {}
            for kb_id, kb_meta in kb_instance.databases_meta.items():
                kb_descriptions.append(f"- {kb_meta['name']}: {kb_meta.get('description', '')}")
                map_name_id[kb_meta['name']] = kb_id
            
            kb_description = "## 知识库描述信息\n"+"\n".join(kb_descriptions)

            res = self.llm_no_stream.invoke(
                format_prompt(
                    DB_CHECK_PROMPT, 
                    {"kb_description": kb_description, "query": query}
                ),
                config={"tags": ["internal"]}
            )
            content = res.content
            data = parse_json(content)
            logger.info(f"LLM Response: {data}")
            kb_names = [map_name_id[n] for n in data.get("kb_names",[])]
            return {"kb_names":kb_names}


        def _build_graph():
            graph = StateGraph(RagState)
            graph.add_node("judge_retrieval_node", _judge_retrieval_node)
            graph.add_node("retrieval_node", _retrieval_node)
            graph.add_node("summary_node", _summary_node)
            # graph.add_edge(START, "judge_retrieval_node")
            graph.add_conditional_edges(START, _should_retrieval, ['summary_node', 'judge_retrieval_node'])
            graph.add_edge("judge_retrieval_node", "retrieval_node")
            graph.add_edge("retrieval_node", "summary_node")
            graph.add_edge("summary_node", END)
            # 编译工作流
            workflow = graph.compile(checkpointer=cpt)
            return workflow

        if self.graph:
            return self.graph

        graph = _build_graph()

        self.graph = graph
        return graph

