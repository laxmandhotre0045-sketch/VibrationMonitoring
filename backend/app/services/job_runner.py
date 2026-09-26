"""What a queued job actually does.

Kept apart from `worker.py` so the work and the polling loop can be reasoned
about — and tested — separately. This module knows nothing about polling,
signals or sleeping; the worker knows nothing about pipelines.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.crud import measurement as measurement_crud
from app.models.job import JOB_MEASUREMENT_PIPELINE, ProcessingJob
from app.services.feature_storage import _load_parsed_for_upload
from app.services.measurement_pipeline import PipelineResult, resolve_config, run_pipeline

logger = logging.getLogger(__name__)

#: What the request already did before queuing: parsed the file and stored it.
#:
#: Store stays in the request on purpose. `parse_status` has to read "parsed"
#: the moment upload returns, because the feature endpoints the UI polls answer
#: 422 for an upload that is not parsed — and the UI would show an error
#: instead of "still working".
REQUEST_STEPS = frozenset({"store"})

#: What the worker does. The expensive half, and the half Phase 1 grows.
BACKGROUND_STEPS = frozenset({"plots", "features", "alerts"})


class UnknownJobType(Exception):
    """A job row this build has no handler for."""


def run_job(db: Session, job: ProcessingJob) -> PipelineResult:
    """Run one claimed job to completion.

    Raises on anything that stopped the pipeline from running at all — the
    upload row gone, parsed data unreadable, the database unavailable. Those
    are worth retrying, and the worker turns them into a retry.

    A *step* that fails is not one of those. `run_pipeline` already records
    step failures on the upload row, which is exactly where the UI reads them
    from; retrying against the pipeline's own recorded verdict would fight it,
    and would flip a status the UI has already stopped polling on. So a run
    that completes with a failed step is a job that succeeded at its job.
    """
    if job.job_type != JOB_MEASUREMENT_PIPELINE:
        raise UnknownJobType(f"No handler for job_type {job.job_type!r}")

    upload = measurement_crud.get_upload_by_id(db, job.upload_id)
    if upload is None:
        raise ValueError(f"Upload {job.upload_id} no longer exists")

    cfg: dict[str, Any] = resolve_config(db, upload.sensor_id, upload.channel_count)
    parsed = _load_parsed_for_upload(db, upload)

    result = run_pipeline(db, upload, parsed, cfg, only=BACKGROUND_STEPS)

    failed = [name for name in BACKGROUND_STEPS if result.failed(name)]
    if failed:
        # Recorded on the upload, surfaced to the UI through its status fields.
        # Logged here too, because a worker's log is where someone looks when a
        # user says "the numbers never arrived".
        logger.warning(
            "Job %s finished with failed steps for upload %s: %s",
            job.id,
            job.upload_id,
            "; ".join(f"{name}: {result.error_for(name)}" for name in failed),
        )
    else:
        logger.info(
            "Job %s completed upload %s (%s)",
            job.id,
            job.upload_id,
            ", ".join(f"{n}: {result.outcomes[n].detail}" for n in result.ran) or "nothing to do",
        )

    return result
