from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid as uuid_mod

logger = logging.getLogger(__name__)


class PiProcess:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._state: str = "starting"
        self._is_streaming: bool = False
        self._reader_task: asyncio.Task | None = None
        self._event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._idle_since: float | None = None

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    @property
    def is_alive(self) -> bool:
        return self._state not in ("dead",)

    @property
    def state(self) -> str:
        return self._state

    @property
    def idle_since(self) -> float | None:
        return self._idle_since

    async def start(self, cmd: list[str], env: dict[str, str], cwd: str) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            cwd=cwd,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._state = "ready"

    async def _read_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        buf = b""
        try:
            while True:
                chunk = await self._process.stdout.read(8192)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        logger.warning("Failed to parse pi JSONL: %s", line[:200])
                        continue

                    if event.get("type") == "response":
                        cmd_id = event.get("id")
                        if cmd_id and cmd_id in self._pending_responses:
                            self._pending_responses[cmd_id].set_result(event)
                        continue

                    await self._event_queue.put(event)
        finally:
            self._state = "dead"
            self._is_streaming = False
            for fut in self._pending_responses.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("Pi process exited"))
            self._pending_responses.clear()
            await self._event_queue.put(None)

    async def _send_command(self, cmd: dict) -> dict:
        if self._state == "dead":
            raise RuntimeError("Pi process is dead")
        assert self._process is not None
        assert self._process.stdin is not None

        cmd_id = str(uuid_mod.uuid4())
        cmd["id"] = cmd_id
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_responses[cmd_id] = future

        data = json.dumps(cmd).encode() + b"\n"
        self._process.stdin.write(data)
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=30)
        finally:
            self._pending_responses.pop(cmd_id, None)

    async def send_get_state(self) -> dict:
        return await self._send_command({"type": "get_state"})

    async def send_prompt(self, message: str) -> dict:
        self._is_streaming = True
        self._state = "streaming"
        return await self._send_command({"type": "prompt", "message": message})

    async def iter_events(self):
        while True:
            event = await self._event_queue.get()
            if event is None:
                break
            yield event
            if event.get("type") == "agent_settled":
                self._state = "idle"
                self._is_streaming = False
                self._idle_since = time.monotonic()
                break

    async def abort(self) -> None:
        if self._state == "dead" or self._process is None or self._process.stdin is None:
            return
        data = json.dumps({"type": "abort"}).encode() + b"\n"
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def shutdown(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        self._state = "dead"
        self._is_streaming = False
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
