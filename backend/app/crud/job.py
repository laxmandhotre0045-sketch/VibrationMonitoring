"""Queue operations for `processing_jobs`.

The interesting one is `claim_next_job`. Two workers polling the same table
must never take the same row, and a worker killed mid-job must not strand it
forever. Postgres gives both for free:

* ``FOR UPDATE SKIP LOCKED`` — a row another transaction has claimed is
  stepped over rather than waited on, so N workers scale without coordination.
* ``started_at`` on a running row — a job still "running" long past any
  plausible runtime belonged to a worker that died, and is claimable again.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.job import (
    ACTIVE_STATUSES,
    JOB_MEASUREMENT_PIPELINE,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    ProcessingJob,
)

DEFAULT_MAX_ATTEMPTS = 3


def get_job_for_upload(db: Session, upload_id: UUID) -> Optional[ProcessingJob]:
    return (
        db.query(ProcessingJob).filter(ProcessingJob.upload_id == upload_id).first()
    )


def has_active_job(db: Session, upload_id: UUID) -> bool:
    """Is work for this upload queued or already running?

    Read by the feature endpoints: while this is true they report the upload's
    recorded status instead of computing features in the request, which would
    race the worker doing the same thing.
    """
    return (
        db.query(ProcessingJob.id)
        .filter(
            ProcessingJob.upload_id == upload_id,
            ProcessingJob.status.in_(ACTIVE_STATUSES),
        )
        .first()
        is not None
    )


def enqueue_job(
    db: Session,
    upload_id: UUID,
    *,
    job_type: str = JOB_MEASUREMENT_PIPELINE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    now: datetime | None = None,
) -> ProcessingJob:
    """Queue work for an upload, replacing any job already recorded for it.

    An upsert, so re-uploading or reprocessing re-arms the one row for this
    upload rather than queuing the same work twice. `attempts` resets: a fresh
    request earns a fresh set of tries, including for a job that had run out.

    `created_at` is left alone on conflict, so the row keeps the time the
    upload first needed work.
    """
    moment = now or datetime.utcnow()
    values = {
        "upload_id": upload_id,
        "job_type": job_type,
        "status": STATUS_QUEUED,
        "attempts": 0,
        "max_attempts": max_attempts,
        "error": None,
        "available_at": moment,
        "started_at": None,
        "finished_at": None,
        "created_at": moment,
        "updated_at": moment,
    }

    insert_stmt = pg_insert(ProcessingJob).values(**values)
    db.execute(
        insert_stmt.on_conflict_do_update(
            index_elements=["upload_id"],
            set_={
                name: insert_stmt.excluded[name]
                for name in values
                if name not in ("upload_id", "created_at")
            },
        )
    )
    db.commit()

    job = get_job_for_upload(db, upload_id)
    if job is None:  # pragma: no cover - the upsert above just wrote it
        raise RuntimeError(f"Job for upload {upload_id} missing after enqueue")
    return job


def claim_next_job(
    db: Session,
    *,
    stale_running_after_s: int,
    now: datetime | None = None,
) -> Optional[ProcessingJob]:
    """Take the next runnable job, or None if the queue is empty.

    Claiming is the same transaction as selecting, so the row is marked running
    before any other worker can see it. Returns the job already counted as an
    attempt — a job that kills the worker every time still exhausts its
    attempts rather than looping forever.
    """
    moment = now or datetime.utcnow()
    stale_before = moment - timedelta(seconds=stale_running_after_s)

    job = (
        db.query(ProcessingJob)
        .filter(
            or_(
                and_(
                    ProcessingJob.status == STATUS_QUEUED,
                    ProcessingJob.available_at <= moment,
                ),
                # Abandoned by a worker that died holding it.
                and_(
                    ProcessingJob.status == STATUS_RUNNING,
                    ProcessingJob.started_at.isnot(None),
                    ProcessingJob.started_at < stale_before,
                ),
            )
        )
        .order_by(ProcessingJob.available_at.asc(), ProcessingJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None

    job.status = STATUS_RUNNING
    job.attempts = (job.attempts or 0) + 1
    job.started_at = moment
    job.finished_at = None
    job.updated_at = moment
    db.commit()
    db.refresh(job)
    return job


def mark_succeeded(
    db: Session, job_id: UUID, *, now: datetime | None = None
) -> Optional[ProcessingJob]:
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if job is None:
        return None
    moment = now or datetime.utcnow()
    job.status = STATUS_SUCCEEDED
    job.error = None
    job.finished_at = moment
    job.updated_at = moment
    db.commit()
    db.refresh(job)
    return job


def mark_failed(
    db: Session,
    job_id: UUID,
    error: str,
    *,
    retry_delay_s: int,
    now: datetime | None = None,
) -> Optional[ProcessingJob]:
    """Record a failure, and requeue it unless the attempts are spent.

    The attempt was already counted when the job was claimed, so this only has
    to decide between "try again later" and "stop".
    """
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if job is None:
        return None

    moment = now or datetime.utcnow()
    job.error = error
    job.updated_at = moment

    if job.attempts >= job.max_attempts:
        job.status = STATUS_FAILED
        job.finished_at = moment
    else:
        job.status = STATUS_QUEUED
        # Linear backoff on the attempt count: a database that is down stays
        # down for a while, and hammering it does not help.
        job.available_at = moment + timedelta(seconds=retry_delay_s * job.attempts)
        job.finished_at = None

    db.commit()
    db.refresh(job)
    return job


def count_by_status(db: Session) -> dict[str, int]:
    """Queue depth per status. For logging and an operator's eyeball."""
    from sqlalchemy import func

    rows = (
        db.query(ProcessingJob.status, func.count(ProcessingJob.id))
        .group_by(ProcessingJob.status)
        .all()
    )
    return {status: int(count) for status, count in rows}
