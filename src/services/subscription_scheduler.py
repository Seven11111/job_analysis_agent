"""Lightweight in-process scheduler for local job subscriptions."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import sessionmaker

from src.db.session import get_session_factory
from src.services.subscription_service import JobSubscriptionService


logger = logging.getLogger(__name__)


class JobSubscriptionScheduler:
    def __init__(
        self,
        service: JobSubscriptionService,
        *,
        session_factory: sessionmaker | None = None,
        poll_interval_seconds: int | None = None,
    ):
        self.service = service
        self.session_factory = session_factory
        self.poll_interval_seconds = poll_interval_seconds

    def _session_factory(self):
        return self.session_factory or get_session_factory()

    def recover(self) -> int:
        session = self._session_factory()()
        try:
            recovered = self.service.recover_interrupted_runs(session)
            logger.info("Recovered %s interrupted job subscription runs", recovered)
            return recovered
        finally:
            session.close()

    def run_due_once(self) -> int:
        return self.service.run_due(self._session_factory())

    @staticmethod
    def seconds_until_next_minute(now: datetime) -> float:
        """Return the delay to the next minute boundary, as cron does its matching."""
        return max(0.01, 60 - now.second - now.microsecond / 1_000_000)

    async def run_forever(self) -> None:
        await asyncio.to_thread(self.recover)
        while True:
            try:
                await asyncio.to_thread(self.run_due_once)
            except Exception:
                logger.exception("Job subscription scheduler iteration failed")
            if self.poll_interval_seconds is not None:
                await asyncio.sleep(self.poll_interval_seconds)
            else:
                now = datetime.now(ZoneInfo(self.service.TIMEZONE))
                await asyncio.sleep(self.seconds_until_next_minute(now))
