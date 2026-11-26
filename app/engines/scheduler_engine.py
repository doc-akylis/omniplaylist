import asyncio
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any


class ScheduledJob:
    """Representation of an async background recurring task."""

    def __init__(
        self,
        name: str,
        interval_seconds: int,
        task_func: Callable[[], Coroutine[Any, Any, None]],
    ):
        self.name = name
        self.interval_seconds = interval_seconds
        self.task_func = task_func
        self.last_run: datetime | None = None
        self.is_running: bool = False


class SchedulerEngine:
    """Lightweight asynchronous background job runner for recurring playlist synchronizations."""

    def __init__(self):
        self.jobs: list[ScheduledJob] = []
        self._runner_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def add_job(
        self,
        name: str,
        interval_seconds: int,
        task_func: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """Register a new recurring background job."""
        self.jobs.append(ScheduledJob(name, interval_seconds, task_func))

    async def _loop(self) -> None:
        """Main evaluation loop executing jobs according to their intervals."""
        while not self._stop_event.is_set():
            now = datetime.utcnow()
            for job in self.jobs:
                if (
                    not job.last_run
                    or (now - job.last_run).total_seconds() >= job.interval_seconds
                ):
                    job.last_run = now
                    try:
                        await job.task_func()
                    except Exception as e:
                        print(f"[Scheduler] Error executing job '{job.name}': {e}")

            # Sleep short interval before next evaluation tick
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        """Start scheduler background task."""
        if self._runner_task is None or self._runner_task.done():
            self._stop_event.clear()
            self._runner_task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        """Signal stop event and terminate scheduler task."""
        self._stop_event.set()
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()
