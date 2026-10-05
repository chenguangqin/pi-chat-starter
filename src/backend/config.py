from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    pi_model: str = field(
        default_factory=lambda: os.environ.get(
            "PI_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        )
    )
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("DATA_DIR", "./data"))
    )
    pi_idle_timeout_seconds: int = field(
        default_factory=lambda: int(os.environ.get("PI_IDLE_TIMEOUT_SECONDS", "900"))
    )
    max_pi_processes: int = field(
        default_factory=lambda: int(os.environ.get("MAX_PI_PROCESSES", "20"))
    )
    expected_pi_version: str = "1.0.2"

    @property
    def db_url(self) -> str:
        db_path = self.data_dir / "common_agent.db"
        return f"sqlite+aiosqlite:///{db_path}"
