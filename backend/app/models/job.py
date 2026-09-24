"""Background work queued for the worker process.

One table, polled. No Redis, no broker: the database is already the thing every
process shares, it already gives us transactions, and `SELECT … FOR UPDATE SKIP
LOCKED` is exactly a work queue. A second piece of infrastructure to move a few
uploads a minute would cost more to operate than it saves.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base

#: Queued and waiting for a worker, or being retried after a failure.
STATUS_QUEUED = "queued"
#: Claimed by a worker. `started_at` says when, which is how a job abandoned by
#: a crashed worker is found again.
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
#: Out of attempts. Terminal — only a fresh enqueue revives it.
STATUS_FAILED = "failed"

ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

#: The only job kind today. Named rather than assumed, so a second kind is a
#: new constant instead of a new table.
JOB_MEASUREMENT_PIPELINE = "measurement_pipeline"


class ProcessingJob(Base):
    """One unit of deferred work for one upload.

    **One row per upload, not one per attempt.** `upload_id` is unique and
    enqueueing upserts, so re-uploading or reprocessing the same upload re-arms
    the existing row rather than growing a queue of duplicates for the same
    work. `attempts` carries the history that separate rows would have.
    """

    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    job_type = Column(String(40), nullable=False, default=JOB_MEASUREMENT_PIPELINE)
    status = Column(String(20), nullable=False, default=STATUS_QUEUED, index=True)

    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error = Column(Text, nullable=True)

    #: Not claimable before this. Set ahead on a retry, which is the backoff.
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
