from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import yuxi.services.agent_run_service as agent_run_service


@pytest.mark.asyncio
async def test_stream_agent_run_events_emits_error_on_db_error(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def fake_session_ctx():
        yield object()

    class BrokenRepo:
        def __init__(self, db):
            self.db = db

        async def get_run_for_user(self, run_id: str, uid: str):
            del run_id, uid
            raise RuntimeError("db down")

    monkeypatch.setattr(agent_run_service.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", BrokenRepo)

    chunks = []
    async for chunk in agent_run_service.stream_agent_run_events(
        run_id="run-1",
        after_seq="0",
        current_uid="user-1",
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].startswith("event: error")
    assert '"reason": "db_error"' in chunks[0]


@pytest.mark.asyncio
async def test_stream_agent_run_events_reads_redis_and_ends_on_end_event(monkeypatch: pytest.MonkeyPatch):
    @asynccontextmanager
    async def fake_session_ctx():
        yield object()

    class Repo:
        def __init__(self, db):
            self.db = db

        async def get_run_for_user(self, run_id: str, uid: str):
            del run_id, uid
            return SimpleNamespace(status="completed", thread_id="thread-1")

    calls = {"count": 0}

    async def fake_list_events(run_id: str, *, after_seq: str, limit: int):
        del run_id, after_seq, limit
        calls["count"] += 1
        if calls["count"] == 1:
            return [
                {
                    "seq": "1700000000000-0",
                    "event_type": "messages",
                    "payload": {
                        "schema_version": 1,
                        "run_id": "run-1",
                        "thread_id": "thread-1",
                        "event": "messages",
                        "payload": {"items": [{"status": "loading", "response": "你"}]},
                        "created_at": "2026-05-27T00:00:00+00:00",
                    },
                    "ts": 1700000000000,
                },
                {
                    "seq": "1700000000001-0",
                    "event_type": "end",
                    "payload": {
                        "schema_version": 1,
                        "run_id": "run-1",
                        "thread_id": "thread-1",
                        "event": "end",
                        "payload": {"status": "completed"},
                        "created_at": "2026-05-27T00:00:01+00:00",
                    },
                    "ts": 1700000000001,
                },
            ]
        return []

    monkeypatch.setattr(agent_run_service.pg_manager, "get_async_session_context", fake_session_ctx)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", Repo)
    monkeypatch.setattr(agent_run_service, "list_run_stream_events", fake_list_events)
    monkeypatch.setattr(agent_run_service, "SSE_POLL_INTERVAL_SECONDS", 0)

    chunks = []
    async for chunk in agent_run_service.stream_agent_run_events(
        run_id="run-1",
        after_seq="0",
        current_uid="user-1",
    ):
        chunks.append(chunk)

    assert chunks[0].startswith("event: messages")
    assert "id: 1700000000000-0" in chunks[0]
    assert chunks[-1].startswith("event: end")
    assert "id: 1700000000001-0" in chunks[-1]


@pytest.mark.asyncio
async def test_create_agent_run_persists_input_before_enqueue(monkeypatch: pytest.MonkeyPatch):
    class FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(uid="user-1", role="user")

    class FakeDB:
        def __init__(self):
            self.order: list[str] = []
            self.committed = False
            self.added = []

        async def execute(self, stmt):
            del stmt
            return FakeResult()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            self.order.append("flush")
            for item in self.added:
                if getattr(item, "id", None) is None:
                    item.id = 10

        async def commit(self):
            self.order.append("commit")
            self.committed = True

        async def rollback(self):
            raise AssertionError("rollback should not be called")

    db = FakeDB()
    created_run = SimpleNamespace(
        id="",
        thread_id="thread-1",
        status="pending",
        request_id="req-1",
        uid="user-1",
    )

    class RunRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_run_by_request_id(self, request_id: str):
            del request_id
            return None

        async def create_run(self, **kwargs):
            assert kwargs["request_id"] == "req-1"
            assert kwargs["conversation_id"] == 1
            created_run.id = kwargs["run_id"]
            return created_run

        async def set_input_message(self, run_id: str, message_id: int):
            assert run_id == created_run.id
            assert message_id == 10
            return created_run

    class ConvRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_conversation_by_thread_id(self, thread_id: str):
            del thread_id
            return SimpleNamespace(id=1, uid="user-1", status="active", agent_id="default")

    class AgentRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_visible_by_slug(self, slug: str, user):
            del user
            return SimpleNamespace(slug=slug, backend_id="ChatbotAgent")

    class Queue:
        async def enqueue_job(self, job_name: str, run_id: str, _job_id: str):
            assert job_name == "process_agent_run"
            assert run_id == created_run.id
            assert _job_id == f"run:{created_run.id}"
            db.order.append("enqueue")
            assert db.committed is True

    async def fake_get_arq_pool():
        return Queue()

    monkeypatch.setattr(agent_run_service.agent_manager, "get_agent", lambda backend_id: object())
    monkeypatch.setattr(agent_run_service, "AgentRepository", AgentRepo)
    monkeypatch.setattr(agent_run_service, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", RunRepo)
    monkeypatch.setattr(agent_run_service, "get_arq_pool", fake_get_arq_pool)

    result = await agent_run_service.create_agent_run_view(
        query="hello",
        agent_id="default",
        thread_id="thread-1",
        meta={"request_id": "req-1"},
        image_content=None,
        current_uid="user-1",
        db=db,
    )

    assert db.order[-2:] == ["commit", "enqueue"]
    assert result["run_id"] == created_run.id
    assert result["request_id"] == "req-1"
    assert db.added[0].run_id == created_run.id
    assert db.added[0].request_id == "req-1"


@pytest.mark.asyncio
async def test_create_resume_run_marks_input_message_source(monkeypatch: pytest.MonkeyPatch):
    class FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(uid="user-1", role="user")

    class FakeDB:
        def __init__(self):
            self.order: list[str] = []
            self.committed = False
            self.added = []

        async def execute(self, stmt):
            del stmt
            return FakeResult()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            self.order.append("flush")
            for item in self.added:
                if getattr(item, "id", None) is None:
                    item.id = 11

        async def commit(self):
            self.order.append("commit")
            self.committed = True

        async def rollback(self):
            raise AssertionError("rollback should not be called")

    db = FakeDB()
    created_run = SimpleNamespace(
        id="",
        thread_id="thread-1",
        status="pending",
        request_id="resume-req",
        uid="user-1",
    )

    class RunRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_run_for_user(self, run_id: str, uid: str):
            assert run_id == "parent-run"
            assert uid == "user-1"
            return SimpleNamespace(id=run_id, thread_id="thread-1", status="interrupted")

        async def get_resume_run(self, parent_run_id: str, resume_request_id: str):
            assert parent_run_id == "parent-run"
            assert resume_request_id == "resume-req"
            return None

        async def get_run_by_request_id(self, request_id: str):
            assert request_id == "resume-req"
            return None

        async def create_run(self, **kwargs):
            assert kwargs["run_type"] == "resume"
            assert kwargs["parent_run_id"] == "parent-run"
            assert kwargs["resume_request_id"] == "resume-req"
            created_run.id = kwargs["run_id"]
            return created_run

        async def set_input_message(self, run_id: str, message_id: int):
            assert run_id == created_run.id
            assert message_id == 11
            return created_run

    class ConvRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_conversation_by_thread_id(self, thread_id: str):
            del thread_id
            return SimpleNamespace(id=1, uid="user-1", status="active", agent_id="default")

    class AgentRepo:
        def __init__(self, db_session):
            self.db = db_session

        async def get_visible_by_slug(self, slug: str, user):
            del user
            return SimpleNamespace(slug=slug, backend_id="ChatbotAgent")

    class Queue:
        async def enqueue_job(self, job_name: str, run_id: str, _job_id: str):
            assert job_name == "process_agent_run"
            assert run_id == created_run.id
            assert _job_id == f"run:{created_run.id}"
            assert db.committed is True

    async def fake_get_arq_pool():
        return Queue()

    monkeypatch.setattr(agent_run_service.agent_manager, "get_agent", lambda backend_id: object())
    monkeypatch.setattr(agent_run_service, "AgentRepository", AgentRepo)
    monkeypatch.setattr(agent_run_service, "ConversationRepository", ConvRepo)
    monkeypatch.setattr(agent_run_service, "AgentRunRepository", RunRepo)
    monkeypatch.setattr(agent_run_service, "get_arq_pool", fake_get_arq_pool)

    result = await agent_run_service.create_agent_run_view(
        query=None,
        agent_id="default",
        thread_id="thread-1",
        meta={"request_id": "resume-req"},
        image_content=None,
        current_uid="user-1",
        db=db,
        resume={"language": "python"},
        parent_run_id="parent-run",
        resume_request_id="resume-req",
    )

    assert result["run_id"] == created_run.id
    assert db.added[0].message_type == "resume"
    assert db.added[0].extra_metadata["source"] == "ask_user_question_resume"
