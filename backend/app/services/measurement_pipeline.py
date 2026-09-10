"""The measurement processing pipeline, and the orchestrator that runs it.

This module owns the answer to "what happens to an upload after the row
exists" — parse and store it, compute plots, extract features and trends,
report alerts. It knows nothing about HTTP: no request, no api_key, no status
codes. That is deliberate, and it is the whole point of the file.

Before this existed, the same sequence was written twice, in
routers/ingest.py (the device path) and routers/measurements.py (the manual
upload path), and the two copies had already drifted — only the device path
counted raised alerts. Both now call ``run_pipeline`` instead, so a fix lands
once.

Because it takes plain objects rather than a request, the same function is
callable from four places:

* the ingest endpoint, on a device POST
* the manual upload endpoint
* a reprocess endpoint, for an upload whose plots or features failed
* a backfill script or a test, with no server running at all

**How ordering works.** Nothing here calls anything else. Each step is a
function that takes the context and returns a short detail string; ``STEPS``
declares what each step needs, and ``run_pipeline`` reads that declaration to
decide what runs. Adding a step is a new entry in the list, not an edit to the
steps around it.

**How resumption works.** The upload row already records per-step state in
``parse_status`` / ``plots_status`` / ``features_status``. A step that is not
run this time counts as satisfied when the row says it succeeded earlier, so
``run_pipeline(..., only={"plots"})`` on a stored upload works without
re-storing anything.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud import baseline as baseline_crud
from app.crud import feature as feature_crud
from app.crud import measurement as measurement_crud
from app.models.measurement import SensorDataUpload
from app.services.feature_storage import persist_upload_features_and_trends
from app.services.plot_generator import save_parsed_data
from app.services.plot_storage import persist_all_plot_results

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Context — everything a step is allowed to read
# --------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """Inputs for one run. Steps read this and nothing else.

    ``upload`` is rebound as each step marks it, so a later step always sees
    the current row rather than the snapshot the caller passed in.
    """

    db: Session
    upload: SensorDataUpload
    parsed: dict[str, Any]
    cfg: dict[str, Any]

    # Needed by the store step only. A reprocess run leaves these unset,
    # which is safe because store is skipped on that path.
    raw_content: Optional[bytes] = None
    original_filename: Optional[str] = None
    file_format: Optional[str] = None
    parsed_path: Optional[str] = None

    @property
    def sampling_rate_hz(self) -> float:
        return float(self.cfg["sampling_rate_hz"])


# --------------------------------------------------------------------------
# Step declaration
# --------------------------------------------------------------------------


#: A step returns a short human-readable summary, and optionally a dict of
#: machine-readable values. Two channels rather than one, so a caller that
#: needs the alert count reads a number instead of parsing English out of a
#: log line.
StepReturn = "str | tuple[str, dict[str, Any]]"


@dataclass(frozen=True)
class Step:
    """One unit of work, plus how the upload row records its outcome.

    ``requires`` is what makes the ordering explicit. Before this file, the
    fact that features need parsed data was true only because one call sat
    below another; reordering the lines would have produced a confusing
    runtime error rather than a clear one.
    """

    name: str
    run: Callable[[PipelineContext], Any]
    requires: tuple[str, ...] = ()
    #: Column on SensorDataUpload holding this step's state, if it has one.
    status_field: Optional[str] = None
    #: Values of that column that mean "this step already succeeded".
    ready_values: frozenset[str] = frozenset({"ready"})
    mark_ready: Optional[Callable[[Session, UUID], Any]] = None
    mark_failed: Optional[Callable[[Session, UUID, str], Any]] = None
    #: False when running the step twice would corrupt data rather than
    #: refresh it. See the store step for the one case.
    rerunnable: bool = True


@dataclass
class StepOutcome:
    name: str
    #: "ok" | "failed" | "skipped"
    status: str
    detail: str = ""
    #: Structured values the step produced, for callers that need a number
    #: rather than a sentence.
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0


@dataclass
class PipelineResult:
    """What the caller gets back. Carries no HTTP meaning.

    The endpoint decides what a failure is worth: the device path treats a
    failed store as a 422 and a failed plot step as acceptable, because a
    sensor that keeps delivering is more valuable than one rejected over a
    derived artefact.
    """

    upload: SensorDataUpload
    outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    alerts_raised: int = 0

    def status_of(self, name: str) -> str:
        outcome = self.outcomes.get(name)
        return outcome.status if outcome else "skipped"

    def failed(self, name: str) -> bool:
        return self.status_of(name) == "failed"

    def error_for(self, name: str) -> str:
        outcome = self.outcomes.get(name)
        return outcome.error if outcome else ""

    @property
    def ok(self) -> bool:
        """No step failed.

        Not the same as "the work happened" — a run whose every step was
        skipped is also ``ok``. A reprocess caller wants ``ran`` as well,
        or it will report success for a request that did nothing.
        """
        return not any(o.status == "failed" for o in self.outcomes.values())

    @property
    def ran(self) -> list[str]:
        return [n for n, o in self.outcomes.items() if o.status == "ok"]

    @property
    def skipped(self) -> dict[str, str]:
        """Step name -> why it was skipped."""
        return {
            n: o.detail for n, o in self.outcomes.items() if o.status == "skipped"
        }


# --------------------------------------------------------------------------
# The steps
# --------------------------------------------------------------------------


def _store_step(ctx: PipelineContext):
    """Write the normalised parse to disk and to the database.

    Fatal by declaration rather than by exception: every other step lists
    "store" in ``requires``, so a failure here skips them automatically.
    """
    if not ctx.parsed_path:
        raise ValueError("parsed_path is required to store an upload")

    save_parsed_data(ctx.parsed_path, ctx.parsed)
    updated = measurement_crud.mark_upload_parsed(
        ctx.db, ctx.upload.id, ctx.parsed_path, ctx.parsed["sample_count"]
    )
    if updated is not None:
        ctx.upload = updated

    if ctx.raw_content is not None:
        baseline_crud.save_upload_data(
            ctx.db,
            upload_id=ctx.upload.id,
            sensor_id=ctx.upload.sensor_id,
            original_filename=ctx.original_filename or "",
            file_format=ctx.file_format or "json",
            file_content=ctx.raw_content,
            parsed_data=ctx.parsed,
            channel_count=ctx.upload.channel_count,
            sample_count=ctx.parsed["sample_count"],
        )
    samples = int(ctx.parsed["sample_count"])
    return f"{samples} samples", {"sample_count": samples}


def _plots_step(ctx: PipelineContext):
    path = ctx.parsed_path or ctx.upload.parsed_data_path
    if not path:
        raise ValueError("Upload has no parsed data path")
    count = persist_all_plot_results(ctx.db, ctx.upload, path, ctx.cfg)
    return f"{count} plot series", {"plot_rows": count}


def _features_step(ctx: PipelineContext):
    features, trends = persist_upload_features_and_trends(
        ctx.db, ctx.upload, ctx.parsed, ctx.sampling_rate_hz
    )
    return (
        f"{features} features, {trends} trend points",
        {"feature_rows": features, "trend_rows": trends},
    )


def _alerts_step(ctx: PipelineContext):
    """Count the feature rows that breached a threshold.

    Counting only, for now. Dispatch still happens inside
    feature_storage._notify_alert_webhooks, so this step reports what was
    already sent rather than sending it. Moving dispatch here is a behaviour
    change and belongs in its own commit; when it moves, this is where it
    lands and every caller picks it up for free.
    """
    rows = feature_crud.get_measurement_features(ctx.db, ctx.upload.id)
    breached = [r for r in rows if r.status in ("warning", "critical")]
    critical = sum(1 for r in breached if r.status == "critical")
    return (
        f"{len(breached)} alerts ({critical} critical)",
        {"alerts_raised": len(breached), "critical": critical},
    )


STEPS: tuple[Step, ...] = (
    Step(
        name="store",
        run=_store_step,
        status_field="parse_status",
        ready_values=frozenset({"parsed"}),
        mark_failed=measurement_crud.mark_upload_failed,
        # crud.baseline.save_upload_data is a plain INSERT, so a second run
        # leaves two rows for one upload. Until it upserts, this step is
        # excluded from any rerun.
        rerunnable=False,
    ),
    Step(
        name="plots",
        run=_plots_step,
        requires=("store",),
        status_field="plots_status",
        mark_ready=measurement_crud.mark_upload_plots_ready,
        mark_failed=measurement_crud.mark_upload_plots_failed,
    ),
    Step(
        name="features",
        run=_features_step,
        requires=("store",),
        status_field="features_status",
        mark_ready=feature_crud.mark_upload_features_ready,
        mark_failed=feature_crud.mark_upload_features_failed,
    ),
    Step(
        name="alerts",
        run=_alerts_step,
        requires=("features",),
        # No column of its own yet; its outcome lives only in the result.
        status_field=None,
    ),
)

STEP_NAMES: tuple[str, ...] = tuple(s.name for s in STEPS)


# --------------------------------------------------------------------------
# The orchestrator
# --------------------------------------------------------------------------


def run_pipeline(
    db: Session,
    upload: SensorDataUpload,
    parsed: dict[str, Any],
    cfg: dict[str, Any],
    *,
    raw_content: bytes | None = None,
    original_filename: str | None = None,
    file_format: str | None = None,
    parsed_path: str | None = None,
    only: Iterable[str] | None = None,
) -> PipelineResult:
    """Run the pipeline for one upload.

    ``only`` restricts the run to the named steps — that is the reprocess
    path. A step left out is treated as satisfied when the upload row says it
    already succeeded, so ``only={"plots"}`` reruns plots against data stored
    on an earlier run.

    A step that raises is recorded and the run continues; steps that required
    it are skipped. Nothing here raises on a step failure, because whether a
    given failure should reach the caller as an error is the caller's
    decision, not this module's.
    """
    requested = set(only) if only is not None else set(STEP_NAMES)
    unknown = requested - set(STEP_NAMES)
    if unknown:
        raise ValueError(f"Unknown pipeline steps: {', '.join(sorted(unknown))}")

    ctx = PipelineContext(
        db=db,
        upload=upload,
        parsed=parsed,
        cfg=cfg,
        raw_content=raw_content,
        original_filename=original_filename,
        file_format=file_format,
        parsed_path=parsed_path,
    )
    result = PipelineResult(upload=upload)

    for step in STEPS:
        outcome = _run_step(ctx, step, requested, result)
        result.outcomes[step.name] = outcome

    result.upload = ctx.upload
    result.alerts_raised = _alerts_count(result)
    return result


def _run_step(
    ctx: PipelineContext, step: Step, requested: set[str], result: PipelineResult
) -> StepOutcome:
    """Decide whether one step runs, then run it. The routing lives here."""
    if step.name not in requested:
        return StepOutcome(step.name, "skipped", detail="not requested")

    if step.name in requested and not step.rerunnable and _already_done(ctx, step):
        return StepOutcome(step.name, "skipped", detail="already done, not rerunnable")

    missing = [
        name for name in step.requires if not _satisfied(ctx, name, result)
    ]
    if missing:
        return StepOutcome(
            step.name, "skipped", detail=f"requires {', '.join(missing)}"
        )

    started = time.perf_counter()
    try:
        returned = step.run(ctx)
    except Exception as exc:  # noqa: BLE001 — one bad step must not kill the rest
        logger.warning("Pipeline step %s failed for upload %s: %s", step.name, ctx.upload.id, exc)
        if step.mark_failed is not None:
            updated = step.mark_failed(ctx.db, ctx.upload.id, str(exc))
            if updated is not None:
                ctx.upload = updated
        return StepOutcome(
            step.name,
            "failed",
            error=str(exc),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    if step.mark_ready is not None:
        updated = step.mark_ready(ctx.db, ctx.upload.id)
        if updated is not None:
            ctx.upload = updated

    detail, data = returned if isinstance(returned, tuple) else (returned, {})
    return StepOutcome(
        step.name,
        "ok",
        detail=detail,
        data=data,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _satisfied(ctx: PipelineContext, name: str, result: PipelineResult) -> bool:
    """Did a prerequisite succeed — this run, or on an earlier one?

    The second half is what makes reprocessing work. The upload row is
    already a record of which steps have succeeded; this reads it rather
    than assuming every run starts from nothing.
    """
    outcome = result.outcomes.get(name)
    if outcome is not None and outcome.status == "ok":
        return True
    step = _step_by_name(name)
    return step is not None and _already_done(ctx, step)


def _already_done(ctx: PipelineContext, step: Step) -> bool:
    if step.status_field is None:
        return False
    return getattr(ctx.upload, step.status_field, None) in step.ready_values


def _step_by_name(name: str) -> Step | None:
    return next((s for s in STEPS if s.name == name), None)


def _alerts_count(result: PipelineResult) -> int:
    outcome = result.outcomes.get("alerts")
    if outcome is None or outcome.status != "ok":
        return 0
    return int(outcome.data.get("alerts_raised", 0))


# --------------------------------------------------------------------------
# Config resolution — shared, because both entry points need it
# --------------------------------------------------------------------------


def resolve_config(
    db: Session,
    upload: SensorDataUpload,
    channel_count: int,
    sampling_rate_hz: float | None = None,
) -> dict[str, Any]:
    """The plot configuration for an upload.

    ``sampling_rate_hz`` overrides the stored value, which is what the device
    path needs: the rate the device reports describes the burst it actually
    captured, while the stored configuration is only a fallback for devices
    that do not report one.

    Moved here from routers/measurements.py, where it was private and the
    ingest router had to reimplement it.
    """
    config = measurement_crud.get_plot_config_by_sensor(db, upload.sensor_id)
    cfg = (
        measurement_crud.config_to_dict(config)
        if config
        else measurement_crud.default_config_dict(channel_count)
    )
    if sampling_rate_hz:
        cfg = {**cfg, "sampling_rate_hz": float(sampling_rate_hz)}
    return cfg
