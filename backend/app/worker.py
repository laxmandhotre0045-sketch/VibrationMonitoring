"""The background worker: poll `processing_jobs`, run what is queued.

Run it as its own process, beside the API:

    python -m app.worker

It shares the API's database, its settings and its uploads volume, and nothing
else — no HTTP, no broker. Polling a table is enough at this volume, and it
means one fewer piece of infrastructure to run, monitor and lose.

**Why a separate process rather than a FastAPI background task.** A background
task dies with the worker that spawned it: a deploy, a crash or an OOM kill
loses the work silently, with nothing left on disk saying it was ever owed.
A queue row survives all three, and is picked up by whichever worker is next
to poll.

Several of these can run at once. `claim_next_job` takes rows with
``FOR UPDATE SKIP LOCKED``, so two workers never take the same job and no
coordination is needed beyond the database.
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from types import FrameType

from app.config import settings
from app.crud import job as job_crud
from app.database import SessionLocal
from app.services.job_runner import UnknownJobType, run_job

logger = logging.getLogger("app.worker")


class Worker:
    """The polling loop. One job at a time, per process."""

    def __init__(
        self,
        *,
        poll_interval_s: float | None = None,
        idle_log_every_s: float = 300.0,
    ) -> None:
        self.poll_interval_s = (
            poll_interval_s
            if poll_interval_s is not None
            else settings.worker_poll_interval_s
        )
        self.idle_log_every_s = idle_log_every_s
        self._stop = threading.Event()
        self._last_idle_log = 0.0

    # -- lifecycle ---------------------------------------------------------

    def request_stop(self, *_: object) -> None:
        """Finish the job in hand, then exit. Safe to call from a signal."""
        if not self._stop.is_set():
            logger.info("Stop requested; finishing the current job then exiting")
        self._stop.set()

    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._on_signal)

    def _on_signal(self, signum: int, _frame: FrameType | None) -> None:
        logger.info("Received %s", signal.Signals(signum).name)
        self.request_stop()

    # -- the loop ----------------------------------------------------------

    def run_forever(self) -> None:
        logger.info(
            "Worker started; polling processing_jobs every %.1fs",
            self.poll_interval_s,
        )
        while not self._stop.is_set():
            try:
                did_work = self.run_once()
            except Exception:  # noqa: BLE001 — the loop must outlive any one failure
                # Already logged with context below; this catches the
                # unexpected, such as the database being unreachable.
                logger.exception("Worker iteration failed; backing off")
                did_work = False
                self._stop.wait(self.poll_interval_s)
                continue

            if not did_work:
                # Nothing queued. Sleep on the event, not on the clock, so a
                # stop signal is acted on immediately rather than after a
                # whole poll interval.
                self._stop.wait(self.poll_interval_s)

        logger.info("Worker stopped")

    def run_once(self) -> bool:
        """Claim and run at most one job. True if there was work to do."""
        db = SessionLocal()
        try:
            job = job_crud.claim_next_job(
                db, stale_running_after_s=settings.worker_stale_running_s
            )
            if job is None:
                self._log_idle(db)
                return False

            logger.info(
                "Claimed job %s for upload %s (attempt %d/%d)",
                job.id,
                job.upload_id,
                job.attempts,
                job.max_attempts,
            )
            started = time.perf_counter()

            try:
                run_job(db, job)
            except UnknownJobType as exc:
                # Retrying will not teach this build a handler it does not
                # have, so spend every attempt at once and stop.
                logger.error("Job %s: %s", job.id, exc)
                job.attempts = job.max_attempts
                db.commit()
                job_crud.mark_failed(db, job.id, str(exc), retry_delay_s=0)
                return True
            except Exception as exc:  # noqa: BLE001 — recorded, then retried
                db.rollback()
                logger.exception("Job %s failed for upload %s", job.id, job.upload_id)
                job_crud.mark_failed(
                    db,
                    job.id,
                    f"{type(exc).__name__}: {exc}",
                    retry_delay_s=settings.worker_retry_delay_s,
                )
                return True

            job_crud.mark_succeeded(db, job.id)
            logger.info(
                "Job %s done in %dms", job.id, int((time.perf_counter() - started) * 1000)
            )
            return True
        finally:
            db.close()

    def _log_idle(self, db) -> None:
        """Say the queue is empty now and then, so silence is legible."""
        now = time.monotonic()
        if now - self._last_idle_log < self.idle_log_every_s:
            return
        self._last_idle_log = now
        try:
            logger.info("Queue idle: %s", job_crud.count_by_status(db) or "empty")
        except Exception:  # noqa: BLE001 — a status log must never stop the loop
            logger.debug("Could not read queue depth", exc_info=True)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )
    worker = Worker()
    worker.install_signal_handlers()
    try:
        worker.run_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive use
        worker.request_stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
