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
        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            image_dir=data_dir / "images",
            database_path=data_dir / "gptlink.db",
            codex_home=codex_home,
            hermes_home=hermes_home,
            host=os.environ.get("GPTLINK_HOST", "127.0.0.1"),
            port=int(os.environ.get("GPTLINK_PORT", "8787")),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)


settings = Settings.load()
