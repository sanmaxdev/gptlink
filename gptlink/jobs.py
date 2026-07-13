from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from gptlink.agent_service import AgentImageService
from gptlink.config import Settings, settings
from gptlink.database import Database
from gptlink.webhooks import deliver_webhook, validate_webhook_url

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class JobManager:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self.database = Database(app_settings.database_path)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if any(thread.is_alive() for thread in self._threads):
                return
            self.settings.ensure_directories()
            self.database.initialize()
            self.database.recover_interrupted_jobs()
            self.database.recover_interrupted_deliveries()
            self._stop.clear()
            self._threads = []
            for index in range(self.settings.job_workers):
                thread = threading.Thread(
                    target=self._run,
                    name=f"gptlink-job-{index + 1}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads = []

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        self.settings.ensure_directories()
        self.database.initialize()
        payload = dict(request)
        webhook_url = payload.pop("webhook_url", None)
        metadata = payload.pop("metadata", {}) or {}
        if webhook_url:
            if not self.settings.webhook_secret or len(self.settings.webhook_secret) < 32:
                raise ValueError(
                    "Webhooks require GPTLINK_WEBHOOK_SECRET with at least 32 characters"
                )
            webhook_url = validate_webhook_url(str(webhook_url), self.settings)
        operation = str(payload.pop("operation", "generate"))
        job = self.database.create_job(
            job_id=f"job_{uuid.uuid4().hex}",
            operation=operation,
            request=payload,
            webhook_url=webhook_url,
            metadata={str(key): str(value) for key, value in dict(metadata).items()},
        )
        self.start()
        return self.public_job(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.database.get_job(job_id)
        return self.public_job(job) if job else None

    def list_jobs(self, *, limit: int = 30, status: str | None = None) -> list[dict[str, Any]]:
        return [self.public_job(job) for job in self.database.list_jobs(limit, status)]

    def cancel_job(self, job_id: str) -> dict[str, Any] | None:
        job = self.database.cancel_job(job_id)
        return self.public_job(job) if job else None

    def public_job(self, job: dict[str, Any]) -> dict[str, Any]:
        request = dict(job.get("request") or {})
        reference_count = len(request.pop("reference_images", []) or [])
        request.pop("mask_image", None)
        public = {
            "id": job["id"],
            "object": "image_job",
            "operation": job["operation"],
            "status": job["status"],
            "request": {**request, "reference_image_count": reference_count},
            "metadata": job.get("metadata") or {},
            "result": job.get("result"),
            "error": job.get("error"),
            "webhook": (
                {
                    "configured": True,
                    "host": urlparse(str(job["webhook_url"])).hostname,
                }
                if job.get("webhook_url")
                else {"configured": False, "host": None}
            ),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
        }
        delivery = self.database.delivery_for_job(str(job["id"]))
        public["webhook_delivery"] = delivery
        return public

    def _run(self) -> None:
        while not self._stop.is_set():
            worked = self._process_job() or self._process_delivery()
            if not worked:
                self._stop.wait(0.5)

    def _process_job(self) -> bool:
        job = self.database.claim_next_job()
        if not job:
            return False
        job_id = str(job["id"])
        try:
            request = dict(job["request"])
            operation = str(job["operation"])
            service = AgentImageService(self.settings)
            result = asyncio.run(
                service.generate(
                    **request,
                    action="edit" if operation in {"edit", "variation"} else None,
                )
            )
            finished = self.database.finish_job(job_id, result=result)
        except Exception as exc:
            logger.warning("Image job %s failed: %s", job_id, type(exc).__name__)
            finished = self.database.finish_job(job_id, error=str(exc)[:2000])
        if finished and finished.get("webhook_url"):
            public = self.public_job(finished)
            event_type = f"image_job.{finished['status']}"
            payload = {
                "id": f"evt_{uuid.uuid4().hex}",
                "object": "event",
                "type": event_type,
                "created_at": datetime.now(UTC).isoformat(),
                "data": {"job": public},
            }
            self.database.create_webhook_delivery(
                delivery_id=f"whd_{uuid.uuid4().hex}",
                job_id=job_id,
                event_type=event_type,
                payload=payload,
            )
        return True

    def _process_delivery(self) -> bool:
        delivery = self.database.claim_due_delivery()
        if not delivery:
            return False
        attempt = int(delivery["attempts"]) + 1
        try:
            status_code = deliver_webhook(
                url=str(delivery["webhook_url"]),
                delivery_id=str(delivery["id"]),
                event_type=str(delivery["event_type"]),
                payload=dict(delivery["payload"]),
                settings=self.settings,
            )
            self.database.finish_delivery(
                str(delivery["id"]),
                delivered=True,
                status_code=status_code,
                error=None,
                next_attempt_at=None,
            )
        except Exception as exc:
            exhausted = attempt >= self.settings.webhook_max_attempts
            delay = min(5 * (3 ** (attempt - 1)), 3600)
            retry_at = None
            if not exhausted:
                retry_at = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
            logger.warning(
                "Webhook delivery %s attempt %s failed: %s",
                delivery["id"],
                attempt,
                type(exc).__name__,
            )
            self.database.finish_delivery(
                str(delivery["id"]),
                delivered=False,
                status_code=getattr(exc, "status_code", None),
                error=str(exc)[:1000],
                next_attempt_at=retry_at,
            )
        return True


_manager = JobManager()


def get_job_manager() -> JobManager:
    return _manager
