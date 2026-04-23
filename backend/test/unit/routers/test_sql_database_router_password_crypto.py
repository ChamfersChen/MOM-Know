from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routers.sql_database_router import _normalize_connect_info, sql_database_router
from server.utils.auth_middleware import get_admin_user
from yuxi.storage.postgres.models_business import User
from yuxi.utils.sql_password_crypto import sql_password_crypto


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(sql_database_router, prefix="/api")

    async def fake_admin_user():
        return User(
            username="admin",
            user_id="admin",
            password_hash="x",
            role="admin",
        )

    app.dependency_overrides[get_admin_user] = fake_admin_user
    return app


def _encrypt_password(plaintext: str) -> str:
    public_key_pem = sql_password_crypto.get_public_key_pem().encode("utf-8")
    public_key = serialization.load_pem_public_key(public_key_pem)
    ciphertext = public_key.encrypt(
        plaintext.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("utf-8")


def test_get_sql_password_public_key():
    client = TestClient(_build_app())
    response = client.get("/api/sql_database/password/public_key")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["algorithm"] == "RSA-OAEP-256"
    assert "BEGIN PUBLIC KEY" in payload["public_key"]


def test_normalize_connect_info_supports_encrypted_password():
    plaintext = "P@ssw0rd!"
    encrypted_password = _encrypt_password(plaintext)

    connect_info = {
        "host": "127.0.0.1",
        "port": 3306,
        "username": "root",
        "database": "mom",
        "password_encrypted": encrypted_password,
    }
    normalized = _normalize_connect_info(connect_info)

    assert normalized["password"] == plaintext
    assert "password_encrypted" not in normalized


def test_check_connection_decrypts_password(monkeypatch):
    captured: dict = {}

    async def fake_database_exists(connect_info):
        captured["checked_connect_info"] = connect_info
        return False

    def fake_test_connection(connect_info):
        captured["tested_connect_info"] = connect_info
        return True

    monkeypatch.setattr(
        "server.routers.sql_database_router.sql_database.database_ip_port_name_exists",
        fake_database_exists,
    )
    monkeypatch.setattr(
        "server.routers.sql_database_router.sql_database.test_connection",
        fake_test_connection,
    )

    plaintext = "P@ssw0rd!"
    payload = {
        "database_name": "mom",
        "db_type": "mysql",
        "connect_info": {
            "host": "127.0.0.1",
            "port": 3306,
            "username": "root",
            "database": "mom",
            "password_encrypted": _encrypt_password(plaintext),
        },
    }

    client = TestClient(_build_app())
    response = client.post("/api/sql_database/check_connection", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert captured["checked_connect_info"]["password"] == plaintext
    assert captured["tested_connect_info"]["password"] == plaintext


def test_storage_encrypt_and_decrypt_connect_info_roundtrip():
    connect_info = {
        "host": "127.0.0.1",
        "port": 3306,
        "username": "root",
        "database": "mom",
        "password": "P@ssw0rd!",
    }

    encrypted = sql_password_crypto.encrypt_connect_info_for_storage(connect_info)
    assert "password" not in encrypted
    assert "password_encrypted_storage" in encrypted

    decrypted = sql_password_crypto.decrypt_connect_info_from_storage(encrypted)
    assert decrypted["password"] == "P@ssw0rd!"


def test_sanitize_connect_info_for_output_removes_password_fields():
    connect_info = {
        "host": "127.0.0.1",
        "port": 3306,
        "username": "root",
        "database": "mom",
        "password": "plain",
        "password_encrypted": "network_cipher",
        "password_encrypted_storage": "storage_cipher",
    }

    sanitized = sql_password_crypto.sanitize_connect_info_for_output(connect_info)
    assert "password" not in sanitized
    assert "password_encrypted" not in sanitized
    assert "password_encrypted_storage" not in sanitized
