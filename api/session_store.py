"""
In-memory session storage for NyayaSetu API sessions.
"""

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import Any
import uuid

# Ensure src directory is in sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import logging_config  # noqa: F401 - ensure central logging format is configured
from orchestrator import CaseSession

logger = logging.getLogger(__name__)


class SessionStore:
    """This is single-process, in-memory storage - sessions are lost on restart and this does NOT work correctly if the API is ever run as multiple replicas behind a load balancer without sticky sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._cleanup_task: asyncio.Task | None = None

    def get(self, session_id: str) -> CaseSession | None:
        record = self._sessions.get(session_id)
        if record is None:
            return None
        return record.get("session")

    def create(self) -> tuple[str, CaseSession]:
        session_id = str(uuid.uuid4())
        session = CaseSession()
        now = datetime.now(timezone.utc)
        self._sessions[session_id] = {
            "session": session,
            "created_at": now,
            "last_active": now,
        }
        return session_id, session

    def touch(self, session_id: str) -> None:
        record = self._sessions.get(session_id)
        if record is not None:
            record["last_active"] = datetime.now(timezone.utc)

    def evict_expired(self, max_idle_seconds: int = 1800) -> int:
        now = datetime.now(timezone.utc)
        expired_ids = [
            sid
            for sid, item in list(self._sessions.items())
            if (now - item["last_active"]).total_seconds() > max_idle_seconds
        ]
        for sid in expired_ids:
            item = self._sessions.pop(sid, None)
            if item is not None:
                logger.info(
                    "Evicted expired session %s (last active at %s)",
                    sid,
                    item.get("last_active"),
                )
        return len(expired_ids)

    async def run_cleanup_loop(
        self, interval_seconds: int = 300, max_idle_seconds: int = 1800
    ) -> None:
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                self.evict_expired(max_idle_seconds=max_idle_seconds)
        except asyncio.CancelledError:
            pass

    def start_cleanup_task(
        self, interval_seconds: int = 300, max_idle_seconds: int = 1800
    ) -> asyncio.Task:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self.run_cleanup_loop(
                    interval_seconds=interval_seconds,
                    max_idle_seconds=max_idle_seconds,
                )
            )
        return self._cleanup_task

    async def stop_cleanup_task(self) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
