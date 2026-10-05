from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import time

from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import Settings
from models import Conversation
from pi_process import PiProcess

logger = logging.getLogger(__name__)


class CapacityError(Exception):
    pass


class ProcessManager:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._processes: dict[str, PiProcess] = {}
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        version = await self._check_pi_version()
        if version != self._settings.expected_pi_version:
            raise RuntimeError(
                f"Expected pi {self._settings.expected_pi_version}, got {version}"
            )
        self._cleanup_task = asyncio.create_task(self._idle_cleanup_loop())

    async def _check_pi_version(self) -> str:
        proc = await asyncio.create_subprocess_exec(
            "pi", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip()

    async def get_or_create(self, conversation: Conversation) -> PiProcess:
        cid = conversation.id
        existing = self._processes.get(cid)
        if existing and existing.is_alive:
            return existing

        self._reap_expired()
        alive = sum(1 for p in self._processes.values() if p.is_alive)
        if alive >= self._settings.max_pi_processes:
            raise CapacityError("Too many active pi processes")

        session_dir = (
            self._settings.data_dir / "tenants" / conversation.tenant_id / "sessions"
        )
        session_dir.mkdir(parents=True, exist_ok=True)

        workdir = (
            self._settings.data_dir
            / "tenants"
            / conversation.tenant_id
            / "workdirs"
            / cid
        )
        workdir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "pi",
            "--mode", "rpc",
            "--no-tools",
            "--no-context-files",
            "--provider", "amazon-bedrock",
            "--model", self._settings.pi_model,
            "--session-dir", str(session_dir),
        ]
        if conversation.pi_session_path:
            cmd.extend(["--session", conversation.pi_session_path])

        env = {**os.environ, "AWS_PROFILE": "default"}

        proc = PiProcess()
        await proc.start(cmd, env, str(workdir))
        self._processes[cid] = proc

        if not conversation.pi_session_path:
            state_resp = await proc.send_get_state()
            session_file = state_resp.get("data", {}).get("sessionFile")
            if session_file:
                async with self._session_factory() as session:
                    await session.execute(
                        sa_update(Conversation)
                        .where(Conversation.id == cid)
                        .values(pi_session_path=session_file)
                    )
                    await session.commit()
                conversation.pi_session_path = session_file

        return proc

    def _reap_expired(self) -> None:
        now = time.monotonic()
        timeout = self._settings.pi_idle_timeout_seconds
        to_remove: list[str] = []
        for cid, proc in self._processes.items():
            if not proc.is_alive:
                to_remove.append(cid)
            elif proc.idle_since and (now - proc.idle_since) > timeout:
                asyncio.create_task(proc.shutdown())
                to_remove.append(cid)
        for cid in to_remove:
            del self._processes[cid]

    async def _idle_cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(60)
                self._reap_expired()
        except asyncio.CancelledError:
            pass

    def remove_process(self, conversation_id: str) -> None:
        proc = self._processes.pop(conversation_id, None)
        if proc and proc.is_alive:
            asyncio.create_task(proc.shutdown())

    def remove_workdir(self, tenant_id: str, conversation_id: str) -> None:
        workdir = (
            self._settings.data_dir
            / "tenants"
            / tenant_id
            / "workdirs"
            / conversation_id
        )
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)

    async def shutdown_all(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
        for proc in self._processes.values():
            await proc.shutdown()
        self._processes.clear()

    @property
    def active_count(self) -> int:
        return sum(1 for p in self._processes.values() if p.is_alive)
