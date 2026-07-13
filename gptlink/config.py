from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    image_dir: Path
    database_path: Path
    codex_home: Path
    hermes_home: Path
    host: str
    port: int
    public_base_url: str
    mcp_allowed_roots: tuple[Path, ...]
    webhook_secret: str | None = None
    webhook_allowed_hosts: tuple[str, ...] = ()
    webhook_allow_private: bool = False
    webhook_max_attempts: int = 6
    job_workers: int = 1

    @classmethod
    def load(cls) -> "Settings":
        root_dir = Path(__file__).resolve().parent.parent
        data_dir = Path(os.environ.get("GPTLINK_DATA_DIR", root_dir / "data")).resolve()
        codex_home = Path(
            os.environ.get("CODEX_HOME", Path.home() / ".codex")
        ).resolve()
        hermes_home = Path(
            os.environ.get("HERMES_HOME", Path.home() / ".hermes")
        ).resolve()
        host = os.environ.get("GPTLINK_HOST", "127.0.0.1")
        port = int(os.environ.get("GPTLINK_PORT", "8787"))
        configured_roots = os.environ.get("GPTLINK_MCP_ALLOWED_ROOTS", "")
        allowed_roots = tuple(
            Path(value).expanduser().resolve()
            for value in configured_roots.split(os.pathsep)
            if value.strip()
        )
        webhook_hosts = tuple(
            value.strip().lower()
            for value in os.environ.get("GPTLINK_WEBHOOK_ALLOWED_HOSTS", "").split(",")
            if value.strip()
        )
        webhook_allow_private = os.environ.get(
            "GPTLINK_WEBHOOK_ALLOW_PRIVATE", "false"
        ).lower() in {"1", "true", "yes"}
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            image_dir=data_dir / "images",
            database_path=data_dir / "gptlink.db",
            codex_home=codex_home,
            hermes_home=hermes_home,
            host=host,
            port=port,
            public_base_url=os.environ.get(
                "GPTLINK_PUBLIC_BASE_URL", f"http://{host}:{port}"
            ).rstrip("/"),
            mcp_allowed_roots=allowed_roots,
            webhook_secret=os.environ.get("GPTLINK_WEBHOOK_SECRET") or None,
            webhook_allowed_hosts=webhook_hosts,
            webhook_allow_private=webhook_allow_private,
            webhook_max_attempts=max(
                1, min(int(os.environ.get("GPTLINK_WEBHOOK_MAX_ATTEMPTS", "6")), 12)
            ),
            job_workers=max(1, min(int(os.environ.get("GPTLINK_JOB_WORKERS", "1")), 4)),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)


settings = Settings.load()
