"""主会话 Steer Middleware。"""

from langchain.agents.middleware import AgentMiddleware, hook_config


class SteerMiddleware(AgentMiddleware):
    """在下一次模型调用前结束当前 Run，让队列优先执行 Steer。"""

    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state, runtime):  # noqa: ARG002
        from yuxi.services.agent_request_queue_service import should_end_run_for_steer

        run_id = getattr(runtime.context, "run_id", None)
        if not run_id or not await should_end_run_for_steer(run_id):
            return None
        return {"jump_to": "end"}
