from __future__ import annotations

import hashlib
import json
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
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    webhook_url TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    cancel_requested_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_status_created
                    ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS webhook_deliveries (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    last_status_code INTEGER,
                    last_error TEXT,
                    delivered_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_webhooks_due
                    ON webhook_deliveries(status, next_attempt_at);
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

    def create_job(
        self,
        *,
        job_id: str,
        operation: str,
        request: dict[str, object],
        webhook_url: str | None,
        metadata: dict[str, str],
    ) -> dict[str, object]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs
                    (id, operation, status, request_json, webhook_url,
                     metadata_json, created_at, updated_at)
                VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    operation,
                    json.dumps(request, separators=(",", ":")),
                    webhook_url,
                    json.dumps(metadata, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    @staticmethod
    def _decode_job(row: sqlite3.Row) -> dict[str, object]:
        job = dict(row)
        job["request"] = json.loads(str(job.pop("request_json")))
        raw_result = job.pop("result_json")
        job["result"] = json.loads(str(raw_result)) if raw_result else None
        job["metadata"] = json.loads(str(job.pop("metadata_json")))
        return job

    def get_job(self, job_id: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._decode_job(row) if row else None

    def list_jobs(self, limit: int = 30, status: str | None = None) -> list[dict[str, object]]:
        safe_limit = min(max(limit, 1), 100)
        with self.connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (safe_limit,)
                ).fetchall()
        return [self._decode_job(row) for row in rows]

    def recover_interrupted_jobs(self) -> int:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs SET status = 'queued', started_at = NULL, updated_at = ?
                WHERE status = 'running'
                """,
                (now,),
            )
        return cursor.rowcount

    def claim_next_job(self) -> dict[str, object] | None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """
                UPDATE jobs SET status = 'running', started_at = ?, updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, row["id"]),
            )
            if cursor.rowcount != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (row["id"],)
            ).fetchone()
        return self._decode_job(claimed)

    def finish_job(
        self, job_id: str, *, result: dict[str, object] | None = None, error: str | None = None
    ) -> dict[str, object] | None:
        now = utc_now()
        status = "failed" if error else "completed"
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status = ?, result_json = ?, error = ?,
                    completed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (
                    status,
                    json.dumps(result, separators=(",", ":")) if result is not None else None,
                    error,
                    now,
                    now,
                    job_id,
                ),
            )
        return self.get_job(job_id)

    def cancel_job(self, job_id: str) -> dict[str, object] | None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status = 'cancelled', cancel_requested_at = ?,
                    completed_at = ?, updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, now, job_id),
            )
        return self.get_job(job_id)

    def create_webhook_delivery(
        self,
        *,
        delivery_id: str,
        job_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO webhook_deliveries
                    (id, job_id, event_type, payload_json, status,
                     next_attempt_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    delivery_id,
                    job_id,
                    event_type,
                    json.dumps(payload, separators=(",", ":"), sort_keys=True),
                    now,
                    now,
                    now,
                ),
            )

    def claim_due_delivery(self) -> dict[str, object] | None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT d.*, j.webhook_url FROM webhook_deliveries d
                JOIN jobs j ON j.id = d.job_id
                WHERE d.status = 'pending' AND d.next_attempt_at <= ?
                ORDER BY d.next_attempt_at LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                """
                UPDATE webhook_deliveries SET status = 'delivering', updated_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, row["id"]),
            )
            if cursor.rowcount != 1:
                return None
        delivery = dict(row)
        delivery["payload"] = json.loads(str(delivery.pop("payload_json")))
        return delivery

    def recover_interrupted_deliveries(self) -> int:
        now = utc_now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE webhook_deliveries SET status = 'pending',
                    next_attempt_at = ?, updated_at = ?
                WHERE status = 'delivering'
                """,
                (now, now),
            )
        return cursor.rowcount

    def finish_delivery(
        self,
        delivery_id: str,
        *,
        delivered: bool,
        status_code: int | None,
        error: str | None,
        next_attempt_at: str | None,
    ) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE webhook_deliveries SET status = ?, attempts = attempts + 1,
                    next_attempt_at = COALESCE(?, next_attempt_at),
                    last_status_code = ?, last_error = ?, delivered_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    "delivered" if delivered else ("pending" if next_attempt_at else "exhausted"),
                    next_attempt_at,
                    status_code,
                    error,
                    now if delivered else None,
                    now,
                    delivery_id,
                ),
            )

    def delivery_for_job(self, job_id: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, event_type, status, attempts, next_attempt_at,
                    last_status_code, last_error, delivered_at, created_at
                FROM webhook_deliveries WHERE job_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return dict(row) if row else None
