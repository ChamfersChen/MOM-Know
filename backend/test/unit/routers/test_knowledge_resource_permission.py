from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from server.routers import knowledge_router
from yuxi.permissions import ResourcePermission


def _request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "path_params": {"kb_id": "kb-1"},
        }
    )


def test_knowledge_route_permission_classification_keeps_query_params_manage_only():
    assert (
        knowledge_router._knowledge_route_required_permission(_request("POST", "/api/knowledge/databases/kb-1/query"))
        == ResourcePermission.READ
    )


def test_redact_database_secrets_removes_credentials_from_metadata_and_params():
    database = {
        "additional_params": {"dify_token": "secret", "chunk_size": 100},
        "metadata": {"notion_token": "secret", "chunk_size": 100},
    }

    knowledge_router.redact_database_secrets(database)

    assert database == {
        "additional_params": {"chunk_size": 100},
        "metadata": {"chunk_size": 100},
    }
    assert (
        knowledge_router._knowledge_route_required_permission(
            _request("PUT", "/api/knowledge/databases/kb-1/query-params")
        )
        == ResourcePermission.MANAGE
    )


@pytest.mark.asyncio
async def test_readonly_admin_can_read_but_cannot_update_knowledge_base(monkeypatch):
    database = {
        "created_by": "owner",
        "share_config": {
            "version": 2,
            "read_scope": {"access_level": "global"},
            "manage_scope": None,
        },
    }

    async def fake_get_database_info(_kb_id):
        return database

    monkeypatch.setattr(knowledge_router.knowledge_base, "get_database_info", fake_get_database_info)
    admin = SimpleNamespace(uid="admin-1", role="admin", department_id=2)

    assert (
        await knowledge_router.get_admin_user(
            _request("GET", "/api/knowledge/databases/kb-1"),
            admin,
        )
        is admin
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge_router.get_admin_user(
            _request("PUT", "/api/knowledge/databases/kb-1"),
            admin,
        )
    assert exc_info.value.status_code == 403
