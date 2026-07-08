from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories.agent_repository import (
    AgentRepository,
    DEFAULT_AGENT_DESCRIPTION,
    DEFAULT_SHARE_CONFIG,
    GENERAL_PURPOSE_AGENT_DESCRIPTION,
    GENERAL_PURPOSE_AGENT_NAME,
    GENERAL_PURPOSE_AGENT_SLUG,
    SUB_AGENT_BACKEND_ID,
    user_can_access_agent,
    user_can_manage_agent,
)
from yuxi.storage.postgres.models_business import Agent, User


class FakeDb:
    def __init__(self):
        self.added = None
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    def add(self, item):
        self.added = item


@pytest.mark.asyncio
async def test_ensure_default_agent_creates_description(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)

    async def get_by_slug(_slug):
        return None

    monkeypatch.setattr(repo, "get_by_slug", get_by_slug)

    agent = await repo.ensure_default_agent()

    assert agent.description == DEFAULT_AGENT_DESCRIPTION
    assert agent.config_json == {"context": {}}
    assert db.added is agent
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(agent)


@pytest.mark.asyncio
async def test_ensure_default_agent_backfills_missing_description(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)
    agent = SimpleNamespace(
        share_config=DEFAULT_SHARE_CONFIG.copy(),
        is_default=True,
        description=None,
        updated_by=None,
        updated_at=None,
    )

    async def get_by_slug(_slug):
        return agent

    monkeypatch.setattr(repo, "get_by_slug", get_by_slug)

    result = await repo.ensure_default_agent(created_by="admin")

    assert result is agent
    assert agent.description == DEFAULT_AGENT_DESCRIPTION
    assert agent.updated_by == "admin"
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(agent)


@pytest.mark.asyncio
async def test_ensure_general_purpose_subagent_creates_empty_config_subagent(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)

    async def get_by_slug(_slug):
        return None

    monkeypatch.setattr(repo, "get_by_slug", get_by_slug)

    agent = await repo.ensure_general_purpose_subagent(created_by="system")

    assert agent.slug == GENERAL_PURPOSE_AGENT_SLUG
    assert agent.name == GENERAL_PURPOSE_AGENT_NAME
    assert agent.description == GENERAL_PURPOSE_AGENT_DESCRIPTION
    assert agent.backend_id == SUB_AGENT_BACKEND_ID
    assert agent.is_subagent is True
    assert agent.is_default is False
    assert agent.config_json == {"context": {}}
    assert agent.share_config == DEFAULT_SHARE_CONFIG
    assert agent.created_by == "system"
    assert db.added is agent
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(agent)


@pytest.mark.asyncio
async def test_ensure_general_purpose_subagent_is_idempotent(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)
    existing = SimpleNamespace(slug=GENERAL_PURPOSE_AGENT_SLUG, config_json={"context": {"model": "custom:model"}})

    async def get_by_slug(_slug):
        return existing

    monkeypatch.setattr(repo, "get_by_slug", get_by_slug)

    agent = await repo.ensure_general_purpose_subagent()

    assert agent is existing
    assert db.added is None
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_agent_for_normal_user_forces_private_share(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)

    async def fake_unique_slug(_slug, _name):
        return "personal-bot"

    monkeypatch.setattr(repo, "_unique_slug", fake_unique_slug)

    creator = User(username="user", uid="user", password_hash="x", role="user", department_id=1)
    agent = await repo.create(
        name="Personal Bot",
        backend_id="ChatbotAgent",
        slug="personal-bot",
        share_config={"access_level": "global", "department_ids": [], "user_uids": []},
        created_by="user",
        creator=creator,
    )

    assert agent.share_config == {"access_level": "user", "department_ids": [], "user_uids": ["user"]}
    assert db.added is agent


def test_shared_agent_is_accessible_but_not_manageable_for_normal_user():
    user = User(username="user", uid="user", password_hash="x", role="user", department_id=1)
    agent = Agent(
        slug="shared-bot",
        name="Shared Bot",
        backend_id="ChatbotAgent",
        created_by="other",
        share_config={"access_level": "user", "department_ids": [], "user_uids": ["user"]},
    )

    assert user_can_access_agent(user, agent) is True
    assert user_can_manage_agent(user, agent) is False


@pytest.mark.asyncio
async def test_create_agent_persists_suggested_questions(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)

    async def fake_unique_slug(_slug, _name):
        return "qa-bot"

    monkeypatch.setattr(repo, "_unique_slug", fake_unique_slug)

    creator = User(username="admin", uid="admin", password_hash="x", role="admin", department_id=1)
    agent = await repo.create(
        name="QA Bot",
        backend_id="ChatbotAgent",
        slug="qa-bot",
        suggested_questions=[
            "  你好，请介绍一下自己  ",
            "你好，请介绍一下自己",
            "",
            "  今天的天气如何？  ",
            None,
        ],
        creator=creator,
    )

    assert agent.suggested_questions == ["你好，请介绍一下自己", "今天的天气如何？"]
    assert db.added is agent
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(agent)


@pytest.mark.asyncio
async def test_create_agent_suggested_questions_caps_at_max_items(monkeypatch):
    db = FakeDb()
    repo = AgentRepository(db)

    async def fake_unique_slug(_slug, _name):
        return "qa-bot"

    monkeypatch.setattr(repo, "_unique_slug", fake_unique_slug)

    creator = User(username="admin", uid="admin", password_hash="x", role="admin", department_id=1)
    payload = [f"问题 {i}" for i in range(30)]
    agent = await repo.create(
        name="QA Bot",
        backend_id="ChatbotAgent",
        slug="qa-bot",
        suggested_questions=payload,
        creator=creator,
    )

    from yuxi.repositories.agent_repository import SUGGESTED_QUESTIONS_MAX_ITEMS

    assert len(agent.suggested_questions) == SUGGESTED_QUESTIONS_MAX_ITEMS
    assert agent.suggested_questions[0] == "问题 0"
    assert agent.suggested_questions[-1] == f"问题 {SUGGESTED_QUESTIONS_MAX_ITEMS - 1}"


@pytest.mark.asyncio
async def test_update_agent_applies_suggested_questions_and_drops_empty_entries():
    db = FakeDb()
    repo = AgentRepository(db)
    agent = Agent(
        slug="qa-bot",
        name="QA Bot",
        backend_id="ChatbotAgent",
        suggested_questions=["旧问题"],
    )

    await repo.update(
        agent,
        suggested_questions=["  新问题  ", "", "  ", "另一个问题", "新问题"],
    )

    assert agent.suggested_questions == ["新问题", "另一个问题"]


@pytest.mark.asyncio
async def test_update_agent_omitted_suggested_questions_does_not_overwrite():
    db = FakeDb()
    repo = AgentRepository(db)
    agent = Agent(
        slug="qa-bot",
        name="QA Bot",
        backend_id="ChatbotAgent",
        suggested_questions=["保留问题"],
    )

    await repo.update(agent, description="新描述")

    assert agent.suggested_questions == ["保留问题"]
