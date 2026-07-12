from __future__ import annotations

import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class CreatedApiKey:
    id: int
    name: str
    prefix: str
    secret: str
    created_at: str


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    prefix TEXT NOT NULL UNIQUE,
                    secret_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    model TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    size TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def hash_secret(secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def create_api_key(self, name: str) -> CreatedApiKey:
        key_id = secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:10]
        secret_material = secrets.token_urlsafe(32)
        secret = f"gptlink_{key_id}_{secret_material}"
        prefix = f"gptlink_{key_id}"
        created_at = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO api_keys (name, prefix, secret_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name.strip() or "Default", prefix, self.hash_secret(secret), created_at),
            )
            row_id = int(cursor.lastrowid)
        return CreatedApiKey(row_id, name.strip() or "Default", prefix, secret, created_at)

    def list_api_keys(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, prefix, created_at, last_used_at, revoked_at
                FROM api_keys ORDER BY id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def validate_api_key(self, secret: str) -> bool:
        if not secret.startswith("gptlink_"):
            return False
        parts = secret.split("_", 2)
        if len(parts) != 3:
            return False
        prefix = f"{parts[0]}_{parts[1]}"
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, secret_hash FROM api_keys
                WHERE prefix = ? AND revoked_at IS NULL
                """,
                (prefix,),
            ).fetchone()
            if row is None or not secrets.compare_digest(
                row["secret_hash"], self.hash_secret(secret)
            ):
                return False
            connection.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (utc_now(), row["id"]),
            )
        return True

    def revoke_api_key(self, key_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE api_keys SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (utc_now(), key_id),
            )
        return cursor.rowcount > 0

    def record_image(
        self,
        *,
        image_id: str,
        filename: str,
        prompt: str,
        model: str,
        quality: str,
        size: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO images
                    (id, filename, prompt, model, quality, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (image_id, filename, prompt, model, quality, size, utc_now()),
            )

    def list_images(self, limit: int = 24) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, filename, prompt, model, quality, size, created_at
                FROM images ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

