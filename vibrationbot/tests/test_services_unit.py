"""Unit tests for session handling and vision enrichment. No OpenAI required."""

import json
import threading

import pytest

from app.ingestion import vision_enrichment
from app.chat.sessions import SessionService


# --------------------------------------------------------------------------
# SessionService
# --------------------------------------------------------------------------


def test_sessions_are_lru_bounded():
    svc = SessionService(max_sessions=3)
    for i in range(5):
        svc.get_or_create(f"s{i}")
    assert svc.get_history("s0") == []  # evicted
    assert svc.get_history("s4") == []  # present but empty
    assert len(svc._sessions) == 3


def test_active_session_survives_eviction():
    svc = SessionService(max_sessions=3)
    svc.get_or_create("keep")
    svc.add_turn("keep", "q", "a")
    for i in range(5):
        svc.get_or_create(f"filler{i}")
        svc.add_turn("keep", "q", "a")  # keeps it most-recently-used
    assert len(svc.get_history("keep")) == 6


def test_turn_history_is_capped():
    svc = SessionService()
    svc.get_or_create("s")
    for i in range(50):
        svc.add_turn("s", f"q{i}", f"a{i}")
    history = svc.get_history("s")
    assert len(history) <= 10
    assert history[-1].question == "q49"


def test_concurrent_add_turn_loses_nothing():
    """Regression: unlocked dict mutation dropped turns under the threadpool."""
    svc = SessionService()
    svc.get_or_create("shared")
    errors = []

    def worker(n):
        try:
            for i in range(50):
                svc.add_turn(f"sess{n}", f"q{i}", f"a{i}")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    for n in range(8):
        history = svc.get_history(f"sess{n}")
        assert len(history) == 10
        assert history[-1].question == "q49"


def test_get_or_create_generates_id_when_missing():
    svc = SessionService()
    sid = svc.get_or_create(None)
    assert sid and svc.get_history(sid) == []


# --------------------------------------------------------------------------
# Vision enrichment
# --------------------------------------------------------------------------


def _png_bytes(w=100, h=100):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _write_chunks(path, n_images=4, n_tables=0):
    chunks = [
        {"chunk_id": "c000", "chunk_type": "clause", "text": "intro text", "meta": {}}
    ]
    for i in range(n_images):
        chunks.append(
            {
                "chunk_id": f"i{i:03d}",
                "chunk_type": "image",
                "text": f"Figure {i}",
                "meta": {"asset_path": f"assets/fig{i}.png"},
            }
        )
    for i in range(n_tables):
        chunks.append(
            {
                "chunk_id": f"t{i:03d}",
                "chunk_type": "table",
                "text": f"col a | col b\n1 | {i}",
                "page_start": 1,
                "page_end": 1,
                "meta": {},
            }
        )
    chunks.append(
        {"chunk_id": "c999", "chunk_type": "clause", "text": "outro text", "meta": {}}
    )
    path.write_text("\n".join(json.dumps(c) for c in chunks) + "\n", encoding="utf-8")
    return chunks


def _make_doc(tmp_path, n_images=4, n_tables=0, with_pdf=False):
    if n_images:
        assets = tmp_path / "assets"
        assets.mkdir(exist_ok=True)
        for i in range(n_images):
            (assets / f"fig{i}.png").write_bytes(_png_bytes())
    if with_pdf:
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "A page with a table")
        doc.save(str(tmp_path / "source.pdf"))
        doc.close()
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(chunks_path, n_images, n_tables)
    return chunks_path


def _read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def vision_env(monkeypatch):
    monkeypatch.setattr(vision_enrichment, "ENABLE_VISION_ENRICHMENT", True)
    monkeypatch.setattr(vision_enrichment, "VISION_ENRICH_FIGURES", True)
    monkeypatch.setattr(vision_enrichment, "VISION_ENRICH_TABLES", True)
    monkeypatch.setattr(vision_enrichment, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(vision_enrichment, "OpenAI", lambda **kw: object())


def test_figures_enriched_and_order_preserved(tmp_path, vision_env, monkeypatch):
    monkeypatch.setattr(
        vision_enrichment, "_vision_call", lambda client, prompt, data_url: "FIGDESC"
    )
    chunks_path = _make_doc(tmp_path, n_images=4)
    n = vision_enrichment.enrich_chunks(chunks_path, tmp_path)

    assert n == 4
    out = _read(chunks_path)
    assert [c["chunk_id"] for c in out] == ["c000", "i000", "i001", "i002", "i003", "c999"]
    assert out[0]["text"] == "intro text"  # clause untouched
    assert out[-1]["text"] == "outro text"
    for i in range(4):
        chunk = out[i + 1]
        assert chunk["text"].startswith("FIGDESC")
        assert f"Figure {i}" in chunk["text"]  # original placeholder retained
        assert chunk["meta"]["vision_caption"] == "FIGDESC"


def test_vision_runs_concurrently(tmp_path, vision_env, monkeypatch):
    """Regression: vision calls were serial and dominated ingest wall-clock."""
    active = peak = 0
    lock = threading.Lock()
    barrier = threading.Barrier(4, timeout=10)

    def slow(client, prompt, data_url):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()  # deadlocks unless >=4 run at once
        with lock:
            active -= 1
        return "DESC"

    monkeypatch.setattr(vision_enrichment, "_vision_call", slow)
    monkeypatch.setattr(vision_enrichment, "VISION_CAPTION_WORKERS", 8)

    chunks_path = _make_doc(tmp_path, n_images=4)
    assert vision_enrichment.enrich_chunks(chunks_path, tmp_path) == 4
    assert peak >= 4, f"expected concurrency, peak parallelism was {peak}"


def test_quota_error_short_circuits_remaining(tmp_path, vision_env, monkeypatch):
    import httpx
    import openai

    calls = []

    def failing(client, prompt, data_url):
        calls.append(1)
        response = httpx.Response(
            401, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        )
        raise openai.AuthenticationError(
            "no quota", response=response, body={"code": "insufficient_quota"}
        )

    monkeypatch.setattr(vision_enrichment, "_vision_call", failing)
    monkeypatch.setattr(vision_enrichment, "VISION_CAPTION_WORKERS", 1)

    chunks_path = _make_doc(tmp_path, n_images=6)
    n = vision_enrichment.enrich_chunks(chunks_path, tmp_path)

    assert n == 0
    assert len(calls) == 1, f"quota flag should stop after first failure, got {calls}"
    assert len(_read(chunks_path)) == 8  # chunks still written intact


def test_missing_assets_are_skipped(tmp_path, vision_env, monkeypatch):
    monkeypatch.setattr(vision_enrichment, "_vision_call", lambda *a: "x")
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(chunks_path, n_images=3)  # no assets/ dir created
    assert vision_enrichment.enrich_chunks(chunks_path, tmp_path) == 0
    assert len(_read(chunks_path)) == 5


def test_tables_transcribed_via_page_image(tmp_path, vision_env, monkeypatch):
    """Table chunks are sent to vision as a rendered page image."""
    seen = {}

    def capture(client, prompt, data_url):
        seen["has_image"] = data_url is not None
        seen["prompt"] = prompt
        return "| a | b |\n| --- | --- |\n| 1 | 2 |\n\nA summary of the table."

    monkeypatch.setattr(vision_enrichment, "_vision_call", capture)
    chunks_path = _make_doc(tmp_path, n_images=0, n_tables=1, with_pdf=True)
    n = vision_enrichment.enrich_chunks(chunks_path, tmp_path)

    assert n == 1
    assert seen["has_image"] is True, "table should be sent as a rendered page image"
    assert "col a" in seen["prompt"]  # local extraction passed as an anchor
    out = _read(chunks_path)
    table = next(c for c in out if c["chunk_type"] == "table")
    assert "summary of the table" in table["text"]
    assert table["meta"]["local_table_text"].startswith("col a")  # original kept
    assert table["meta"]["vision_table"]


def test_tables_fall_back_to_text_only_without_pdf(tmp_path, vision_env, monkeypatch):
    """DOCX / missing source PDF: table goes to vision as text, no image."""
    seen = {}

    def capture(client, prompt, data_url):
        seen["has_image"] = data_url is not None
        return "clean markdown + summary"

    monkeypatch.setattr(vision_enrichment, "_vision_call", capture)
    chunks_path = _make_doc(tmp_path, n_images=0, n_tables=1, with_pdf=False)
    n = vision_enrichment.enrich_chunks(chunks_path, tmp_path)

    assert n == 1
    assert seen["has_image"] is False
    table = next(c for c in _read(chunks_path) if c["chunk_type"] == "table")
    assert table["text"] == "clean markdown + summary"


def test_tables_disabled_leaves_them_untouched(tmp_path, vision_env, monkeypatch):
    monkeypatch.setattr(vision_enrichment, "VISION_ENRICH_TABLES", False)
    monkeypatch.setattr(vision_enrichment, "_vision_call", lambda *a: "SHOULD NOT RUN")
    chunks_path = _make_doc(tmp_path, n_images=0, n_tables=2, with_pdf=True)
    assert vision_enrichment.enrich_chunks(chunks_path, tmp_path) == 0
    for c in _read(chunks_path):
        if c["chunk_type"] == "table":
            assert "SHOULD NOT RUN" not in c["text"]


def test_element_cap_prioritizes_tables_over_figures(tmp_path, vision_env, monkeypatch):
    """A large catalog must not blow the token budget; tables win the cap."""
    monkeypatch.setattr(vision_enrichment, "VISION_MAX_ELEMENTS", 3)
    calls = {"figure": 0, "table": 0}
    lock = threading.Lock()

    def fake(client, prompt, data_url):
        with lock:
            kind = "figure" if prompt.startswith("Describe this figure") else "table"
            calls[kind] += 1
        return "RESULT"

    monkeypatch.setattr(vision_enrichment, "_vision_call", fake)
    # 2 tables + 10 figures, cap 3 -> both tables + 1 figure = 3 calls total.
    chunks_path = _make_doc(tmp_path, n_images=10, n_tables=2, with_pdf=True)
    n = vision_enrichment.enrich_chunks(chunks_path, tmp_path)

    assert n == 3
    assert calls["table"] == 2, "both tables should survive the cap"
    assert calls["figure"] == 1, "only the remaining slot goes to a figure"


def test_element_cap_unlimited_when_zero(tmp_path, vision_env, monkeypatch):
    monkeypatch.setattr(vision_enrichment, "VISION_MAX_ELEMENTS", 0)
    monkeypatch.setattr(vision_enrichment, "_vision_call", lambda *a: "R")
    chunks_path = _make_doc(tmp_path, n_images=5, n_tables=0)
    assert vision_enrichment.enrich_chunks(chunks_path, tmp_path) == 5


def test_retry_after_parsed_from_message():
    err = Exception("Rate limit reached. Please try again in 274ms. Visit ...")
    assert abs(vision_enrichment._retry_after_seconds(err) - 0.274) < 1e-6
    err2 = Exception("slow down, try again in 2s please")
    assert vision_enrichment._retry_after_seconds(err2) == 2.0
    assert vision_enrichment._retry_after_seconds(Exception("no hint here")) is None


def test_retry_after_parsed_from_header():
    class Resp:
        headers = {"retry-after-ms": "500"}

    err = Exception("429")
    err.response = Resp()
    assert vision_enrichment._retry_after_seconds(err) == 0.5


def test_ingest_lock_blocks_second_ingest(tmp_path, monkeypatch):
    """A second ingest must fail fast while one holds the lock."""
    from app.ingestion import ingest_service

    monkeypatch.setattr(ingest_service, "_LOCK_PATH", tmp_path / ".ingest.lock")

    with ingest_service._ingest_lock():
        with pytest.raises(ingest_service.IngestBusyError):
            with ingest_service._ingest_lock():
                pass  # should never get here

    # Lock is released after the outer context — re-acquirable now.
    with ingest_service._ingest_lock():
        pass


def test_ingest_lock_reclaims_stale_lock(tmp_path, monkeypatch):
    """A lock owned by a dead PID is reclaimed, not honored forever."""
    from app.ingestion import ingest_service

    lock_path = tmp_path / ".ingest.lock"
    monkeypatch.setattr(ingest_service, "_LOCK_PATH", lock_path)
    # Write a lock owned by a PID that cannot be alive.
    lock_path.write_text("999999999 0.0")
    monkeypatch.setattr(ingest_service, "_pid_alive", lambda pid: False)

    # Should reclaim and acquire without raising.
    with ingest_service._ingest_lock():
        pass


def test_token_bucket_paces_to_budget(monkeypatch):
    """Starts empty and paces: each call waits for the bucket to refill."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(vision_enrichment.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(
        vision_enrichment.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s)
    )
    # 6000 tokens/min = 100 tokens/sec, starting EMPTY (no initial burst).
    bucket = vision_enrichment._TokenBucket(6000)

    t0 = clock["t"]
    bucket.acquire(100)  # empty -> must wait ~1s to refill 100 tokens
    assert clock["t"] - t0 >= 1.0 - 1e-6

    t1 = clock["t"]
    bucket.acquire(100)  # again ~1s
    assert clock["t"] - t1 >= 1.0 - 1e-6


def test_token_bucket_disabled_when_limit_zero(monkeypatch):
    monkeypatch.setattr(vision_enrichment, "VISION_TPM_LIMIT", 0)
    assert vision_enrichment._make_token_bucket() is None


def test_pacing_applied_during_enrichment(tmp_path, vision_env, monkeypatch):
    """Enrichment acquires from the bucket before each call."""
    acquired = []
    real_bucket = vision_enrichment._TokenBucket(10_000_000)  # huge → never blocks

    def make_bucket():
        orig = real_bucket.acquire
        real_bucket.acquire = lambda cost: (acquired.append(cost), orig(cost))[1]
        return real_bucket

    monkeypatch.setattr(vision_enrichment, "_make_token_bucket", make_bucket)
    monkeypatch.setattr(vision_enrichment, "_vision_call", lambda *a: "R")
    chunks_path = _make_doc(tmp_path, n_images=3)
    assert vision_enrichment.enrich_chunks(chunks_path, tmp_path) == 3
    assert len(acquired) == 3
    assert all(c > 0 for c in acquired)


def test_transient_error_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(vision_enrichment, "VISION_MAX_RETRIES", 4)
    # Avoid real sleeping.
    monkeypatch.setattr(vision_enrichment.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("try again in 100ms")
        return "OK"

    flag = threading.Event()
    result = vision_enrichment._call_with_retry(flaky, "x", flag)
    assert result == "OK"
    assert calls["n"] == 3
