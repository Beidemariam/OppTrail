"""ADR 0004's in-process scheduler: the only thing here that knows the time.

Milestone 6.5. APScheduler inside the FastAPI process, started from the
`lifespan` and stopped with it — no broker, no worker container, no second
deploy unit, which is the whole of ADR 0004's argument for a 20-user
single-container app.

This module is deliberately thin, and that is the point: `jobs.py` holds what
runs and knows nothing about APScheduler, so every job is callable from a test
without a scheduler in the room (the ADR's own instruction). What is here is
the wiring and the three decisions that go with it.

- **Interval triggers, not cron.** Both jobs answer "how often", not "at what
  time": rules are checked every `automation_interval_minutes` and the
  snapshot taken every `backup_interval_hours`. An interval also means the
  first firing is one interval after boot rather than at startup, which is
  what keeps a restart loop from taking a backup per restart — and what keeps
  the e2e suite, which boots the real app, from running a tick during its
  three minutes.
- **`max_instances=1` and `coalesce=True`.** A tick that outlives its own
  interval must not have a second copy started beside it (both would walk the
  same rules and both would act), and a process that was asleep must not wake
  to a queue of missed ticks it then runs back to back. One at a time, and a
  missed tick is skipped rather than made up — sound because these jobs are
  idempotent by design (ADR 0004), not because missing one is free.
- **One instance is assumed.** ADR 0004 says so explicitly and names the
  consequence: two application instances would double-run every periodic job,
  because nothing here claims a lock. That is the same single-instance
  assumption ADR 0003's SSE makes, and the two are to be revisited together.

`settings.scheduler_enabled` turns it off, which the test suite does: a tick
firing under a test would evaluate a rule the test had just written, and the
failure would surface somewhere else entirely.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .jobs import run_job
from .logging_utils import logger
from .settings import settings

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler | None:
    """Start the scheduler, or answer `None` when it is switched off.

    Idempotent: called from `lifespan`, which runs once, but a second call
    returns the running scheduler rather than standing up a second one that
    would double every job.
    """
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(
        job_defaults={"max_instances": 1, "coalesce": True, "misfire_grace_time": 60}
    )
    scheduler.add_job(
        run_job,
        IntervalTrigger(minutes=settings.automation_interval_minutes),
        args=["automations"],
        id="automations",
        name="Evaluate time-driven automation rules",
    )
    scheduler.add_job(
        run_job,
        IntervalTrigger(hours=settings.backup_interval_hours),
        args=["backup"],
        id="backup",
        name="Snapshot the database",
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "scheduler_started",
        extra={
            "automation_interval_minutes": settings.automation_interval_minutes,
            "backup_interval_hours": settings.backup_interval_hours,
        },
    )
    return scheduler


def stop_scheduler() -> None:
    """Shut down without waiting for a running job.

    `wait=False` because the process is going away: a tick in flight has
    already written its `started` row, which is exactly how a reader learns
    that a job was interrupted rather than skipped. Blocking the shutdown on
    it would turn a container restart into a wait of up to a whole tick.
    """
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("scheduler_stopped")


def scheduled_jobs() -> list[str]:
    """The ids currently scheduled, for the test that asserts both are."""
    return [] if _scheduler is None else sorted(job.id for job in _scheduler.get_jobs())
