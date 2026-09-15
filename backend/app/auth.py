"""Password authentication, opaque sessions, RBAC, and audit persistence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Literal
from uuid import uuid4


Role = Literal["OPERATOR", "REVIEWER", "ADMIN"]
ROLES = {"OPERATOR", "REVIEWER", "ADMIN"}
PBKDF2_ITERATIONS = 310_000


@dataclass(frozen=True)
class AuthSettings:
    required: bool
    session_ttl_seconds: int
    bootstrap_username: str | None
    bootstrap_password_file: Path | None
    bootstrap_role: Role
    ingest_token_file: Path | None

    @classmethod
    def from_environment(cls, environment: str) -> "AuthSettings":
        default_required = "true" if environment == "production" else "false"
        required = os.getenv("CITYEYE_AUTH_REQUIRED", default_required).lower() == "true"
        ttl = int(os.getenv("CITYEYE_SESSION_TTL_SECONDS", "28800"))
        if ttl < 300 or ttl > 86400:
            raise ValueError("CITYEYE_SESSION_TTL_SECONDS must be between 300 and 86400")
        role = os.getenv("CITYEYE_BOOTSTRAP_ADMIN_ROLE", "ADMIN").upper()
        if role not in ROLES:
            raise ValueError("CITYEYE_BOOTSTRAP_ADMIN_ROLE is invalid")
        password_file = os.getenv("CITYEYE_BOOTSTRAP_ADMIN_PASSWORD_FILE")
        ingest_file = os.getenv("CITYEYE_INGEST_TOKEN_FILE")
        bootstrap_username = os.getenv("CITYEYE_BOOTSTRAP_ADMIN_USERNAME") or None
        if environment == "production" and bootstrap_username and "change-me" in bootstrap_username.lower():
            raise ValueError("Replace CHANGE-ME in CITYEYE_BOOTSTRAP_ADMIN_USERNAME")
        return cls(
            required=required,
            session_ttl_seconds=ttl,
            bootstrap_username=bootstrap_username,
            bootstrap_password_file=Path(password_file) if password_file else None,
            bootstrap_role=role,  # type: ignore[arg-type]
            ingest_token_file=Path(ingest_file) if ingest_file else None,
        )


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    username: str
    role: Role


def hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    selected_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), selected_salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${selected_salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def read_secret_file(path: Path | None, label: str) -> str | None:
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Cannot read {label} secret file") from exc
    if not value:
        raise ValueError(f"{label} secret file is empty")
    return value


class AuthRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('OPERATOR', 'REVIEWER', 'ADMIN')),
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry
                ON auth_sessions(expires_at);
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id TEXT PRIMARY KEY,
                    actor_user_id TEXT NOT NULL,
                    actor_username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    previous_value TEXT,
                    new_value TEXT,
                    request_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_audit_created_at
                ON audit_log(created_at DESC);
                """
            )

    def user_count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, username: str, password: str, role: Role) -> AuthenticatedUser:
        normalized = username.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("Username must contain 1 to 80 characters")
        if role not in ROLES:
            raise ValueError("Invalid role")
        user = AuthenticatedUser(str(uuid4()), normalized, role)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO users (user_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                    (user.user_id, user.username, hash_password(password), user.role),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Username already exists") from exc
        return user

    def list_users(self) -> list[AuthenticatedUser]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, username, role FROM users WHERE active = 1 ORDER BY username"
            ).fetchall()
        return [
            AuthenticatedUser(row["user_id"], row["username"], row["role"])
            for row in rows
        ]

    def authenticate(self, username: str, password: str) -> AuthenticatedUser | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, username, password_hash, role FROM users WHERE username = ? AND active = 1",
                (username.strip(),),
            ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            return None
        return AuthenticatedUser(row["user_id"], row["username"], row["role"])

    def create_session(self, user: AuthenticatedUser, ttl_seconds: int) -> tuple[str, float]:
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + ttl_seconds
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (time.time(),))
            connection.execute(
                "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user.user_id, expires_at),
            )
        return token, expires_at

    def resolve_session(self, token: str) -> AuthenticatedUser | None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT users.user_id, users.username, users.role
                   FROM auth_sessions JOIN users USING (user_id)
                   WHERE token_hash = ? AND expires_at > ? AND active = 1""",
                (token_hash, time.time()),
            ).fetchone()
        if row is None:
            return None
        return AuthenticatedUser(row["user_id"], row["username"], row["role"])

    def revoke_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))

    def record_audit(
        self,
        actor: AuthenticatedUser,
        action: str,
        target_type: str,
        target_id: str,
        previous_value: str | None,
        new_value: str | None,
        request_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO audit_log (
                    audit_id, actor_user_id, actor_username, action, target_type,
                    target_id, previous_value, new_value, request_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid4()), actor.user_id, actor.username, action, target_type,
                    target_id, previous_value, new_value, request_id,
                ),
            )

    def list_audit(self, limit: int = 100) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT audit_id, actor_user_id, actor_username, action,
                          target_type, target_id, previous_value, new_value,
                          request_id, created_at
                   FROM audit_log ORDER BY created_at DESC, audit_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
