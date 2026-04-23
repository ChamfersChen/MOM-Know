from __future__ import annotations

import base64
import hashlib
import os
import threading

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class SQLPasswordCrypto:
    """SQL 数据源密码加解密工具。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._private_key = None
        self._public_key_pem = ""
        self._storage_cipher = None

    @staticmethod
    def _build_storage_key() -> bytes:
        secret_seed = os.getenv("SQL_PASSWORD_ENCRYPTION_KEY") or os.getenv("JWT_SECRET_KEY") or "yuxi_know_secure_key"
        digest = hashlib.sha256(secret_seed.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)

    def _ensure_keypair(self) -> None:
        if self._private_key:
            return
        with self._lock:
            if self._private_key:
                return
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            public_key = private_key.public_key()
            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            self._private_key = private_key
            self._public_key_pem = public_pem.decode("utf-8")

    def _ensure_storage_cipher(self) -> None:
        if self._storage_cipher:
            return
        with self._lock:
            if self._storage_cipher:
                return
            self._storage_cipher = Fernet(self._build_storage_key())

    def get_public_key_pem(self) -> str:
        self._ensure_keypair()
        return self._public_key_pem

    def decrypt_password(self, encrypted_password: str) -> str:
        self._ensure_keypair()
        ciphertext = base64.b64decode(encrypted_password)
        plaintext = self._private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return plaintext.decode("utf-8")

    def encrypt_password_for_storage(self, password: str) -> str:
        self._ensure_storage_cipher()
        token = self._storage_cipher.encrypt(password.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt_password_from_storage(self, encrypted_password: str) -> str:
        self._ensure_storage_cipher()
        plaintext = self._storage_cipher.decrypt(encrypted_password.encode("utf-8"))
        return plaintext.decode("utf-8")

    def encrypt_connect_info_for_storage(self, connect_info: dict | None) -> dict:
        payload = dict(connect_info or {})
        password = payload.get("password")
        if password:
            payload["password_encrypted_storage"] = self.encrypt_password_for_storage(password)
            payload.pop("password", None)
        return payload

    def decrypt_connect_info_from_storage(self, connect_info: dict | None) -> dict:
        payload = dict(connect_info or {})
        if payload.get("password"):
            return payload

        encrypted_password = payload.pop("password_encrypted_storage", None)
        if encrypted_password:
            payload["password"] = self.decrypt_password_from_storage(encrypted_password)
        return payload

    @staticmethod
    def sanitize_connect_info_for_output(connect_info: dict | None) -> dict:
        payload = dict(connect_info or {})
        payload.pop("password", None)
        payload.pop("password_encrypted_storage", None)
        payload.pop("password_encrypted", None)
        return payload


sql_password_crypto = SQLPasswordCrypto()
