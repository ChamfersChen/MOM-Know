from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)
from langchain.messages import HumanMessage

from src.knowledge import knowledge_base
from src.utils import logger


from collections.abc import Awaitable, Callable


class SqlRetrievalMiddleware(AgentMiddleware):
    def __init__(self, db_id: str):
        self.db_id = db_id

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        messages = request.messages
        last_user_message = messages[-1]

        if not isinstance(last_user_message, HumanMessage):
            return await handler(request)

        user_content  = last_user_message.content

        # sql query intention detection
        sql_pair_retrieval = await knowledge_base.aquery(
            user_content, self.db_id, top_k = 3, similarity_threshold=0.6
        )

        sql_pairs = []
        for sql_pair in sql_pair_retrieval:
            sql_pairs.append(sql_pair.get('content'))

        if sql_pairs:
            sql_pair_prompt = "\n - ".join(sql_pairs)
            user_content = f"## SQL问答对建议\n\n{sql_pair_prompt} \n\n## 用户问题\n\n{user_content}"
            request.messages[-1].content = user_content


        logger.debug(f"request.messages: {request.messages}")

        return await handler(request)


