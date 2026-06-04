from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from yuxi.repositories.agent_repository import (
    AgentRepository,
    DEFAULT_AGENT_DESCRIPTION,
    DEFAULT_SHARE_CONFIG,
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
