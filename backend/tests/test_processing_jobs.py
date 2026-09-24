"""The upsert, the queue, and the worker loop.

No database. The SQL these build is compiled against the PostgreSQL dialect and
read, which is the part that matters: `ON CONFLICT … DO UPDATE` is what makes
storing an upload twice leave one row (VIK-012), and `FOR UPDATE SKIP LOCKED`
is what makes two workers never take the same job (VIK-013).
"""
from __future__ import annotations

import types
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Query


def _sql(statement) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


class RecordingSession:
    """Captures statements instead of executing them."""

    def __init__(self, row=None):
        self.executed = []
        self.commits = 0
        self.row = row
        self.captured_query = None

    def execute(self, statement, *args, **kwargs):
        self.executed.append(statement)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass

    def query(self, *entities):
        session = self

        class _Query:
            def filter(self, *a, **k):
                return self

            def order_by(self, *a, **k):
                return self

            def with_for_update(self, **k):
                return self

            def first(self):
                return session.row

        return _Query()


# ---------------------------------------------------------------------------
# VIK-012 — save_upload_data upserts
# ---------------------------------------------------------------------------


@pytest.fixture
def upload_data_sql() -> str:
    from app.crud import baseline as baseline_crud

    session = RecordingSession(row="STORED")
    baseline_crud.save_upload_data(
        session,
        upload_id=uuid4(),
        sensor_id=uuid4(),
        original_filename="dev.json",
        file_format="json",
        file_content=b"RAW",
        parsed_data={"sample_count": 10},
        channel_count=4,
        sample_count=10,
    )
    assert len(session.executed) == 1, "the upsert must be one statement, not read-then-write"
    return _sql(session.executed[0])


def test_storing_an_upload_twice_leaves_one_row(upload_data_sql):
    assert "INSERT INTO measurement_upload_data" in upload_data_sql
    assert "ON CONFLICT (upload_id) DO UPDATE" in upload_data_sql


def test_a_re_store_refreshes_the_payload(upload_data_sql):
    set_clause = upload_data_sql.split("DO UPDATE SET", 1)[1]
    for column in (
        "sensor_id", "original_filename", "file_format",
        "file_content", "parsed_data", "channel_count", "sample_count",
    ):
        assert f"{column} = excluded.{column}" in set_clause


def test_a_re_store_keeps_the_row_identity_and_first_stored_time(upload_data_sql):
    """`id` and `created_at` must survive.

    Anything already pointing at that id stays valid, and "created" keeps
    meaning when the upload was first stored rather than last touched.
    """
    set_clause = upload_data_sql.split("DO UPDATE SET", 1)[1]
    for column in ("id", "created_at", "upload_id"):
        assert f"{column} = excluded.{column}" not in set_clause


# ---------------------------------------------------------------------------
# VIK-013 — the queue
# ---------------------------------------------------------------------------


def test_claiming_a_job_locks_it_and_steps_over_locked_rows():
    """`FOR UPDATE SKIP LOCKED` is what lets workers scale without coordination."""
    from app.crud import job as job_crud

    session = RecordingSession(row=None)
    captured = {}

    class Recording(Query):
        def first(self):
            captured["statement"] = self.statement
            return None

    session.query = lambda *entities: Recording(entities)
    job_crud.claim_next_job(session, stale_running_after_s=600, now=datetime(2026, 1, 1))

    sql = _sql(captured["statement"])
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "available_at <=" in sql


def test_claiming_reclaims_a_job_abandoned_by_a_dead_worker():
    """A worker killed mid-job must not strand it forever."""
    from app.crud import job as job_crud

    session = RecordingSession(row=None)
    captured = {}

    class Recording(Query):
        def first(self):
            captured["statement"] = self.statement
            return None

    session.query = lambda *entities: Recording(entities)
    job_crud.claim_next_job(session, stale_running_after_s=600, now=datetime(2026, 1, 1))

    sql = _sql(captured["statement"])
    assert "started_at <" in sql, "a running job past its deadline must be claimable again"


def test_enqueueing_twice_re_arms_one_row():
    from app.crud import job as job_crud

    session = RecordingSession(row="JOB")
    job_crud.enqueue_job(session, uuid4())
    assert len(session.executed) == 1

    sql = _sql(session.executed[0])
    assert "ON CONFLICT (upload_id) DO UPDATE" in sql
    set_clause = sql.split("DO UPDATE SET", 1)[1]
    for column in ("status", "attempts", "error", "available_at"):
        assert f"{column} = excluded.{column}" in set_clause
    assert "created_at = excluded.created_at" not in set_clause


class JobRow:
    def __init__(self, attempts, max_attempts=3):
        self.id = uuid4()
        self.attempts = attempts
        self.max_attempts = max_attempts
        self.status = "running"
        self.error = None
        self.available_at = None
        self.finished_at = None
        self.updated_at = None


def test_a_failure_with_attempts_left_is_requeued_with_backoff():
    from app.crud import job as job_crud

    row = JobRow(attempts=2)
    now = datetime(2026, 1, 1, 12, 0, 0)
    job_crud.mark_failed(RecordingSession(row=row), row.id, "boom", retry_delay_s=30, now=now)

    assert row.status == "queued"
    assert row.error == "boom"
    # Linear in the attempt count: a database that is down stays down a while.
    assert row.available_at == now + timedelta(seconds=60)


def test_a_failure_with_no_attempts_left_is_terminal():
    from app.crud import job as job_crud

    row = JobRow(attempts=3)
    now = datetime(2026, 1, 1, 12, 0, 0)
    job_crud.mark_failed(RecordingSession(row=row), row.id, "boom", retry_delay_s=30, now=now)

    assert row.status == "failed"
    assert row.finished_at == now


# ---------------------------------------------------------------------------
# The worker loop
# ---------------------------------------------------------------------------


@pytest.fixture
def worker(monkeypatch):
    from app import worker as worker_module
    from app.services.job_runner import UnknownJobType

    events: list[tuple] = []
    queue: list[types.SimpleNamespace] = []

    def claim(db, **kwargs):
        return queue.pop(0) if queue else None

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: types.SimpleNamespace(
        close=lambda: None, commit=lambda: None, rollback=lambda: None
    ))
    monkeypatch.setattr(worker_module, "job_crud", types.SimpleNamespace(
        claim_next_job=claim,
        mark_succeeded=lambda db, jid, **k: events.append(("succeeded", jid)),
        mark_failed=lambda db, jid, error, **k: events.append(
            ("failed", jid, error, k.get("retry_delay_s"))
        ),
        count_by_status=lambda db: {},
    ))

    def run_job(db, job):
        if job.behaviour == "raise":
            raise RuntimeError("pipeline exploded")
        if job.behaviour == "unknown":
            raise UnknownJobType("no handler for that job type")
        events.append(("ran", job.id))

    monkeypatch.setattr(worker_module, "run_job", run_job)

    def enqueue(behaviour="ok"):
        job = types.SimpleNamespace(
            id=uuid4(), upload_id=uuid4(), attempts=1, max_attempts=3, behaviour=behaviour
        )
        queue.append(job)
        return job

    return types.SimpleNamespace(
        instance=worker_module.Worker(poll_interval_s=0.01), events=events, enqueue=enqueue
    )


def test_an_empty_queue_is_not_work(worker):
    assert worker.instance.run_once() is False


def test_a_queued_job_is_claimed_run_and_marked(worker):
    job = worker.enqueue()
    assert worker.instance.run_once() is True
    assert ("ran", job.id) in worker.events
    assert ("succeeded", job.id) in worker.events


def test_a_raising_job_is_recorded_and_retried(worker):
    job = worker.enqueue("raise")
    worker.instance.run_once()

    failures = [e for e in worker.events if e[0] == "failed"]
    assert len(failures) == 1
    assert "pipeline exploded" in failures[0][2]
    assert failures[0][3] > 0, "a retryable failure must be scheduled, not dropped"


def test_an_unknown_job_type_stops_rather_than_looping(worker):
    """Retrying will not teach this build a handler it does not have."""
    job = worker.enqueue("unknown")
    worker.instance.run_once()
    assert job.attempts == job.max_attempts


def test_the_worker_stops_when_asked(worker):
    worker.instance.request_stop()
    worker.instance.run_forever()  # returns at once rather than polling
    assert worker.instance._stop.is_set()


# ---------------------------------------------------------------------------
# The gate that keeps the UI polling unchanged
# ---------------------------------------------------------------------------


class GateUpload:
    def __init__(self, **overrides):
        self.id = uuid4()
        self.sensor_id = uuid4()
        self.channel_count = 4
        self.parse_status = "parsed"
        self.features_status = "pending"
        self.parsed_data_path = "/x/u.json"
        self.__dict__.update(overrides)


def test_features_are_not_computed_in_the_request_while_a_job_is_queued(monkeypatch):
    """Two processes writing the same feature rows is the thing to avoid.

    The endpoint answers with the upload's recorded `pending` status, which is
    the signal the UI's 3-second poll is already waiting on.
    """
    from app.services import feature_storage

    computed = []
    monkeypatch.setattr(feature_storage, "job_crud", types.SimpleNamespace(
        has_active_job=lambda db, upload_id: True
    ))
    monkeypatch.setattr(
        feature_storage, "persist_upload_features_and_trends",
        lambda *a, **k: computed.append("computed")
    )

    upload = GateUpload()
    returned = feature_storage.ensure_upload_features_ready(None, upload, 2048.0)

    assert computed == []
    assert returned.features_status == "pending"


def test_features_are_still_computed_lazily_for_an_upload_with_no_job(monkeypatch):
    """Uploads made before the worker existed have nobody else to do it."""
    from app.services import feature_storage

    computed = []
    monkeypatch.setattr(feature_storage, "job_crud", types.SimpleNamespace(
        has_active_job=lambda db, upload_id: False
    ))
    monkeypatch.setattr(feature_storage, "_load_parsed_for_upload", lambda db, u: {"sample_count": 1})
    monkeypatch.setattr(
        feature_storage, "persist_upload_features_and_trends",
        lambda *a, **k: computed.append("computed")
    )
    monkeypatch.setattr(feature_storage, "feature_crud", types.SimpleNamespace(
        get_measurement_features=lambda *a, **k: [],
        mark_upload_features_ready=lambda db, uid: GateUpload(features_status="ready"),
    ))

    feature_storage.ensure_upload_features_ready(None, GateUpload(), 2048.0)
    assert computed == ["computed"]


def test_the_plot_read_also_defers_to_the_worker():
    """`persist_all_plot_results` deletes then re-inserts.

    Two of those running at once — a read and the worker — both delete an empty
    table and both insert, leaving one upload with two sets of plot rows.
    """
    import inspect

    from app.services import plot_storage

    source = inspect.getsource(plot_storage.get_or_load_all_plots)
    assert "has_active_job" in source
    assert source.index("has_active_job") < source.index("persist_all_plot_results(db")
