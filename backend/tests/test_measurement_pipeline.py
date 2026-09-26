"""The measurement pipeline: what runs, in what order, and what a failure means.

No database. Every step's collaborator is replaced with a recorder, so these
assert the *orchestration* — which is the part that was duplicated by hand in
two routers and drifted (VIK-011).

The order here is not decoration. Features read the stored parse, alerts read
the feature rows, and the upload row is rebound as each step marks it so a
later step sees the current row rather than the caller's snapshot. Getting any
of that wrong produces empty results rather than an error.
"""
from __future__ import annotations

import dataclasses
import types

import pytest


class FakeUpload:
    """Only the attributes the pipeline reads."""

    def __init__(self, **overrides):
        self.id = "UP1"
        self.sensor_id = "SEN1"
        self.channel_count = 4
        self.parse_status = "pending"
        self.plots_status = "pending"
        self.features_status = "pending"
        self.parsed_data_path = None
        self.__dict__.update(overrides)

    def replace(self, **overrides):
        clone = FakeUpload(**self.__dict__)
        clone.__dict__.update(overrides)
        return clone


class FeatureRow:
    def __init__(self, status):
        self.status = status


PARSED = {"sample_count": 4096, "channels": {}, "timestamps": []}
CFG = {"sampling_rate_hz": 25600.0}


@pytest.fixture
def pipeline(monkeypatch):
    """The real module with every collaborator recorded instead of run.

    Returns the module plus the call log, so a test can assert on the sequence
    as well as the result.
    """
    from app.services import measurement_pipeline as mp

    calls: list[tuple[str, tuple, dict]] = []
    state = {"upload": None, "fail": set(), "features": []}

    def record(name, result=None):
        def fn(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name in state["fail"]:
                raise RuntimeError(f"boom in {name}")
            return result
        return fn

    def mark(name, **changes):
        def fn(db, upload_id, *rest):
            calls.append((name, (db, upload_id, *rest), {}))
            if name in state["fail"]:
                raise RuntimeError(f"boom in {name}")
            state["upload"] = state["upload"].replace(**changes)
            return state["upload"]
        return fn

    monkeypatch.setattr(mp, "save_parsed_data", record("save_parsed_data"))
    monkeypatch.setattr(mp, "persist_all_plot_results", record("persist_all_plot_results", 7))
    monkeypatch.setattr(
        mp, "persist_upload_features_and_trends", record("persist_upload_features_and_trends", (12, 3))
    )
    monkeypatch.setattr(mp, "baseline_crud", types.SimpleNamespace(
        save_upload_data=record("save_upload_data"),
    ))
    monkeypatch.setattr(mp, "measurement_crud", types.SimpleNamespace(
        mark_upload_parsed=mark("mark_upload_parsed", parse_status="parsed"),
        mark_upload_failed=record("mark_upload_failed"),
        mark_upload_plots_ready=mark("mark_upload_plots_ready", plots_status="ready"),
        mark_upload_plots_failed=record("mark_upload_plots_failed"),
        get_plot_config_by_sensor=record("get_plot_config_by_sensor"),
        config_to_dict=record("config_to_dict"),
        default_config_dict=record("default_config_dict", {"sampling_rate_hz": 2048.0}),
    ))
    monkeypatch.setattr(mp, "feature_crud", types.SimpleNamespace(
        mark_upload_features_ready=mark("mark_upload_features_ready", features_status="ready"),
        mark_upload_features_failed=record("mark_upload_features_failed"),
        get_measurement_features=record(
            "get_measurement_features",
            [FeatureRow("normal"), FeatureRow("warning"), FeatureRow("critical"), FeatureRow("warning")],
        ),
    ))

    # The step bodies look their collaborators up as module globals, so the
    # patches above reach them. `STEPS` does not: it binds `mark_ready` and
    # `mark_failed` into the table when the module is imported, so those have
    # to be swapped on the table itself.
    marks = {
        ("store", "mark_failed"): record("mark_upload_failed"),
        ("plots", "mark_ready"): mark("mark_upload_plots_ready", plots_status="ready"),
        ("plots", "mark_failed"): record("mark_upload_plots_failed"),
        ("features", "mark_ready"): mark("mark_upload_features_ready", features_status="ready"),
        ("features", "mark_failed"): record("mark_upload_features_failed"),
    }
    monkeypatch.setattr(mp, "STEPS", tuple(
        dataclasses.replace(
            step,
            **{
                field: marks[(step.name, field)]
                for field in ("mark_ready", "mark_failed")
                if getattr(step, field) is not None
            },
        )
        for step in mp.STEPS
    ))

    def run(upload=None, fail=(), **kwargs):
        state["upload"] = upload or FakeUpload()
        state["fail"] = set(fail)
        calls.clear()
        return mp.run_pipeline(
            "DB", state["upload"], PARSED, CFG,
            raw_content=b"RAW", original_filename="dev.json",
            file_format="json", parsed_path="/x/UP1.json", **kwargs
        )

    return types.SimpleNamespace(module=mp, run=run, calls=calls, names=lambda: [c[0] for c in calls])


# ---------------------------------------------------------------------------
# Order and arguments
# ---------------------------------------------------------------------------


def test_the_steps_run_in_the_declared_order(pipeline):
    pipeline.run()
    assert pipeline.names() == [
        "save_parsed_data",
        "mark_upload_parsed",
        "save_upload_data",
        "persist_all_plot_results",
        "mark_upload_plots_ready",
        "persist_upload_features_and_trends",
        "mark_upload_features_ready",
        "get_measurement_features",
    ]


def test_each_step_is_handed_what_it_needs(pipeline):
    pipeline.run()
    by_name = {name: (args, kwargs) for name, args, kwargs in pipeline.calls}

    assert by_name["save_parsed_data"][0] == ("/x/UP1.json", PARSED)
    assert by_name["mark_upload_parsed"][0] == ("DB", "UP1", "/x/UP1.json", 4096)

    stored = by_name["save_upload_data"][1]
    assert stored["file_content"] == b"RAW"
    assert stored["original_filename"] == "dev.json"
    assert stored["file_format"] == "json"
    assert stored["sample_count"] == 4096

    plots_args = by_name["persist_all_plot_results"][0]
    assert plots_args[2] == "/x/UP1.json"
    assert plots_args[3] is CFG

    feature_args = by_name["persist_upload_features_and_trends"][0]
    assert feature_args[2] is PARSED
    assert feature_args[3] == 25600.0, "features must use the resolved sampling rate"


def test_later_steps_see_the_row_earlier_steps_marked(pipeline):
    """The upload is rebound as it is marked.

    A step handed the caller's original snapshot would read `pending` for work
    that has already happened.
    """
    pipeline.run()
    by_name = {name: args for name, args, _ in pipeline.calls}
    assert by_name["persist_all_plot_results"][1].parse_status == "parsed"
    assert by_name["persist_upload_features_and_trends"][1].plots_status == "ready"


def test_the_alert_count_is_warnings_plus_criticals(pipeline):
    result = pipeline.run()
    assert result.alerts_raised == 3
    assert result.ok
    assert len(result.ran) == 4


# ---------------------------------------------------------------------------
# Failure grading — the caller decides what a failure is worth
# ---------------------------------------------------------------------------


def test_a_failed_store_skips_everything_downstream(pipeline):
    result = pipeline.run(fail={"save_parsed_data"})

    assert result.failed("store")
    assert "mark_upload_failed" in pipeline.names()
    assert "persist_all_plot_results" not in pipeline.names()
    assert "persist_upload_features_and_trends" not in pipeline.names()
    assert result.status_of("plots") == "skipped"
    assert result.status_of("features") == "skipped"
    assert result.error_for("store") == "boom in save_parsed_data"


def test_a_failed_plot_step_does_not_stop_features(pipeline):
    """Graded separately on purpose.

    A device that keeps delivering is worth more than one rejected because a
    derived artefact failed, and both statuses land on the upload for a later
    reprocess.
    """
    result = pipeline.run(fail={"persist_all_plot_results"})

    assert "mark_upload_plots_failed" in pipeline.names()
    assert "persist_upload_features_and_trends" in pipeline.names()
    assert "mark_upload_features_ready" in pipeline.names()
    assert not result.failed("store")
    assert not result.ok


def test_failed_features_leave_the_alert_count_at_zero_not_stale(pipeline):
    result = pipeline.run(fail={"persist_upload_features_and_trends"})

    assert "mark_upload_features_failed" in pipeline.names()
    assert result.status_of("alerts") == "skipped"
    assert result.alerts_raised == 0


# ---------------------------------------------------------------------------
# `only=` — reprocess, and the request/worker split
# ---------------------------------------------------------------------------


def test_only_plots_reruns_plots_against_already_stored_data(pipeline):
    stored = FakeUpload(parse_status="parsed", plots_status="failed", features_status="ready")
    result = pipeline.run(upload=stored, only={"plots"})

    assert "save_upload_data" not in pipeline.names(), "a reprocess must not re-store"
    assert "persist_all_plot_results" in pipeline.names()
    assert "persist_upload_features_and_trends" not in pipeline.names()
    assert result.status_of("plots") == "ok"


def test_store_reruns_now_that_it_upserts(pipeline):
    """VIK-012 removed `rerunnable=False`.

    While `save_upload_data` was a plain INSERT on a unique `upload_id`, a
    second store raised and the step had to be excluded from every rerun. It
    upserts now, so a full run over a stored upload refreshes it.
    """
    already_stored = FakeUpload(parse_status="parsed", plots_status="ready", features_status="ready")
    result = pipeline.run(upload=already_stored)

    assert result.status_of("store") == "ok"
    assert "save_upload_data" in pipeline.names()
    assert "not rerunnable" not in str(result.skipped)


def test_no_step_is_marked_unrerunnable(pipeline):
    assert [s.name for s in pipeline.module.STEPS if not s.rerunnable] == []


def test_an_unknown_step_name_is_rejected(pipeline):
    with pytest.raises(ValueError, match="nope"):
        pipeline.run(only={"nope"})


def test_the_request_and_the_worker_cover_the_pipeline_exactly_once():
    """VIK-013 split the pipeline across a request and a worker.

    A step in neither set would silently never run; a step in both would run
    twice. This is the arithmetic that stops either.
    """
    from app.services.job_runner import BACKGROUND_STEPS, REQUEST_STEPS
    from app.services.measurement_pipeline import STEP_NAMES

    assert set(REQUEST_STEPS) == {"store"}
    assert set(BACKGROUND_STEPS) == {"plots", "features", "alerts"}
    assert set(REQUEST_STEPS) | set(BACKGROUND_STEPS) == set(STEP_NAMES)
    assert not set(REQUEST_STEPS) & set(BACKGROUND_STEPS)


def test_the_pipeline_never_raises_on_a_step_failure(pipeline):
    """Whether a failure is fatal is the endpoint's call, not the pipeline's.

    The device path treats a failed store as 422 and a failed plot as
    acceptable; the pipeline stays out of that decision.
    """
    result = pipeline.run(fail={"save_parsed_data", "persist_all_plot_results"})
    assert result.failed("store")
    assert not result.ok
