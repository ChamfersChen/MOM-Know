"""Planning and task management middleware for agents."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command
from typing_extensions import NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
    OmitFromInput,
)
from langchain.tools import InjectedToolCallId


class Todo(TypedDict):
    """A single todo item with content and status."""
    todo_id: str

    content: str
    """The content/description of the todo item."""

    status: Literal["pending", "in_progress", "completed"]
    """The current status of the todo item."""


class TasksState(AgentState):
    """State schema for the todo middleware."""

    todos: Annotated[NotRequired[list[Todo]], OmitFromInput]
    """List of todo items for tracking task progress."""

UPDATE_TODO_TOOL_DESCRIPTION = """Use this tool to update a structured todo task list for your current work session. This helps you organize task.

## When to Use This Tool
Use this tool in these scenarios:

- The plan may need future revisions or updates based on results from the first few steps

## How to Use This Tool
2. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation.
3. You can also update future tasks, such as deleting them if they are no longer necessary, or adding new tasks that are necessary. Don't change previously completed tasks.
4. You can make several updates to the todo list at once. For example, when you complete a task, you can mark the next task you need to start as in_progress.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (you can have multiple tasks in_progress at a time if they are not related to each other and can be run in parallel)
   - completed: Task finished successfully

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant from the list entirely
   - IMPORTANT: When you write this todo list, you should mark your first task (or tasks) as in_progress immediately!.
   - IMPORTANT: Unless all tasks are completed, you should always have at least one task in_progress to show the user that you are working on something.

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - When blocked, create a new task describing what needs to be resolved
   - Never mark a task as completed if:
     - There are unresolved issues or errors
     - Work is partial or incomplete
     - You encountered blockers that prevent completion
     - You couldn't find necessary resources or dependencies
     - Quality standards haven't been met

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

**Notice**: Once you complete a step, you must immediately mark that todo item as completed using the `update_todos` tool. Do not wait to mark multiple steps at once

Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully
"""

WRITE_TODOS_TOOL_DESCRIPTION = """Use this tool to create a structured task list for your current work session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.

Only use this tool if you think it will be helpful in staying organized. If the user's request is trivial and takes less than 3 steps, it is better to NOT use this tool and just do the task directly.

## When to Use This Tool
Use this tool in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)

## How to Use This Tool
1. When you start working on a task - Mark it as in_progress BEFORE beginning work.

## When NOT to Use This Tool
It is important to skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

Remember: If you only need to make a few tool calls to complete a task, and it is clear what you need to do, it is better to just do the task directly and NOT call this tool at all."""  # noqa: E501

WRITE_TODOS_SKILL_SYSTEM_PROMPT = """## Task Planning Skills

You can use the tools provided by this skill [`write_todos`, `update_todos`] to help plan and manage complex tasks.
For complex tasks, please use this skill to ensure you track each necessary step and keep the user clearly informed of your progress.
This skill is very helpful for planning complex tasks and breaking down those larger, intricate goals into smaller steps.

A key point is that once you complete a step, you must immediately mark that todo item as completed using the `update_todos` tool. Do not wait to mark multiple steps at once.
For simple tasks that require only a few steps, it's better to achieve the goal directly without using this skill.
Writing todo lists takes time and token count; please use it when it helps manage complex, multi-step problems! However, do not use it for simple requests with few steps."""  # noqa: E501

# WRITE_TODOS_SKILL_SYSTEM_PROMPT = """## 任务规划技能

# 你可以使用此技能提供的工具[`write_todos`, `update_todos`]来帮助规划和管理复杂任务。
# 对于复杂任务，请使用此技能，以确保你跟踪每个必要步骤，并让用户清楚了解你的进展。
# 此技能对于规划复杂任务以及将这些较大的复杂目标拆分为更小的步骤非常有帮助。

# 关键的一点是，一旦你完成某个步骤，就必须使用`update_todos`工具立即将该待办事项标记为已完成。不要等到完成多个步骤后再统一标记。
# 对于只需几个步骤的简单任务，最好直接完成目标，而不要使用此技能。
# 撰写待办事项会花费时间和令牌数，请在它有助于管理复杂多步骤问题时使用！但不要用于简单的少量步骤请求。"""  # noqa: E501


def _format_todos(todos: list[Todo]):
    msg = "Updated todo list to:\n\n"
    # todo_msg = json.dumps(todos, indent=2, ensure_ascii=False)
    todo_msg = "\n".join([f"- Task {idx + 1}\n  'content': '{todo['content']}'\n  'status': '{todo['status']}'" for idx, todo in enumerate(todos)])
    return msg + todo_msg


class TaskSkillMiddleware(AgentMiddleware):
    state_schema = TasksState

    def __init__(
        self,
        *,
        system_prompt: str = WRITE_TODOS_SKILL_SYSTEM_PROMPT,
        write_todo_tool_description: str = WRITE_TODOS_TOOL_DESCRIPTION,
        update_todo_tool_description: str = UPDATE_TODO_TOOL_DESCRIPTION,
    ) -> None:
        """Initialize the `TodoListMiddleware` with optional custom prompts.

        Args:
            system_prompt: Custom system prompt to guide the agent on using the todo
                tool.
            tool_description: Custom description for the `write_todos` tool.
        """
        super().__init__()
        self.system_prompt = system_prompt
        self.write_todo_tool_description = write_todo_tool_description
        self.update_todo_tool_description = update_todo_tool_description

        # Dynamically create the write_todos tool with the custom description
        @tool(description=self.write_todo_tool_description)
        def write_todos(
            todos: list[Todo], tool_call_id: Annotated[str, InjectedToolCallId]
        ) -> Command:
            """Create and manage a structured task list for your current work session."""
            return Command(
                update={
                    "todos": todos,
                    "messages": [
                        ToolMessage(_format_todos(todos), tool_call_id=tool_call_id)
                        # ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
                    ],
                }
            )

        @tool(description=self.write_todo_tool_description)
        def update_todos(
            todos: list[Todo], tool_call_id: Annotated[str, InjectedToolCallId]
        ) -> Command:
            """Create and manage a structured task list for your current work session."""
            return Command(
                update={
                    "todos": todos,
                    "messages": [
                        ToolMessage(_format_todos(todos), tool_call_id=tool_call_id)
                        # ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
                    ],
                }
            )

        self.tools = [write_todos, update_todos]

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        """Update the system message to include the todo system prompt."""
        if request.system_message is not None:
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": f"\n\n{self.system_prompt}"},
            ]
        else:
            new_system_content = [{"type": "text", "text": self.system_prompt}]
        new_system_message = SystemMessage(
            content=cast("list[str | dict[str, str]]", new_system_content)
        )
        return handler(request.override(system_message=new_system_message))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        """Update the system message to include the todo system prompt (async version)."""
        if request.system_message is not None:
            new_system_content = [
                *request.system_message.content_blocks,
                {"type": "text", "text": f"\n\n{self.system_prompt}"},
            ]
        else:
            new_system_content = [{"type": "text", "text": self.system_prompt}]
        new_system_message = SystemMessage(
            content=cast("list[str | dict[str, str]]", new_system_content)
        )
        return await handler(request.override(system_message=new_system_message))
