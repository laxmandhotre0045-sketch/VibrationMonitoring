"""Show the measurement pipeline orchestrator making its routing decisions.

Run it to see what the orchestrator does when a step fails, and how a
reprocess run resumes from what the upload row already records:

    python scripts/demo_pipeline_orchestrator.py

Nothing here touches the database, the network, or the real services. The
step functions are replaced with fakes that either succeed or raise, so what
you are watching is purely the ordering and failure logic in
app/services/measurement_pipeline.py.

That this file exists at all is the argument for the refactor: the pipeline
can be exercised without a server, an API key or a device, because it no
longer lives inside a request handler.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import sys
from pathlib import Path

# app.config requires these to construct Settings. The orchestrator never
# opens a connection, so any syntactically valid value will do.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://demo:demo@localhost/demo")
os.environ.setdefault("SECRET_KEY", "demo-only-not-a-real-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import measurement_pipeline as mp  # noqa: E402

# Every failure below is deliberate, so the orchestrator's own warnings would
# only be noise interleaved with the output.
logging.getLogger(mp.__name__).setLevel(logging.CRITICAL)


class FakeUpload:
    """Just the columns the orchestrator reads."""

    def __init__(self, **overrides):
        self.id = "3f7a1c22-demo"
        self.sensor_id = "sensor-demo"
        self.channel_count = 8
        self.parsed_data_path = "/uploads/3f7a1c22.json"
        self.parse_status = "pending"
        self.plots_status = "pending"
        self.features_status = "pending"
        self.__dict__.update(overrides)


def fake_steps(failing: set[str]):
    """Same step table, real dependencies, fake bodies."""

    def body_for(name: str):
        def run(ctx):
            if name in failing:
                raise RuntimeError(f"simulated {name} failure")
            data = {"alerts_raised": 2, "critical": 1} if name == "alerts" else {}
            return f"{name} completed", data

        return run

    return tuple(
        dataclasses.replace(step, run=body_for(step.name), mark_ready=None, mark_failed=None)
        for step in mp.STEPS
    )


SYMBOL = {"ok": "[ok]     ", "failed": "[FAILED] ", "skipped": "[skipped]"}


def scenario(title: str, *, failing=frozenset(), only=None, upload=None) -> None:
    mp.STEPS = fake_steps(set(failing))
    result = mp.run_pipeline(
        db=None,
        upload=upload or FakeUpload(),
        parsed={"sample_count": 25600},
        cfg={"sampling_rate_hz": 25600.0},
        parsed_path="/uploads/3f7a1c22.json",
        raw_content=b"<device payload>",
        only=only,
    )

    print(f"\n  {title}")
    print("  " + "-" * 62)
    for name in mp.STEP_NAMES:
        outcome = result.outcomes[name]
        note = outcome.error or outcome.detail
        print(f"    {SYMBOL[outcome.status]} {name:<9} {note}")
    print(f"    => ok={result.ok}  ran={result.ran}  alerts_raised={result.alerts_raised}")


def main() -> None:
    print("\n" + "=" * 66)
    print("  MEASUREMENT PIPELINE ORCHESTRATOR")
    print("=" * 66)
    print("\n  Declared step table (app/services/measurement_pipeline.py):\n")
    for step in mp.STEPS:
        requires = ", ".join(step.requires) or "-"
        print(
            f"    {step.name:<9} requires={requires:<10} "
            f"column={str(step.status_field):<16} rerunnable={step.rerunnable}"
        )

    print("\n" + "=" * 66)
    print("  ROUTING BEHAVIOUR")
    print("=" * 66)

    scenario("1. Normal ingest - every step runs")

    scenario(
        "2. Plot generation fails - feature extraction must still run",
        failing={"plots"},
    )

    scenario(
        "3. Storage fails - everything downstream is skipped, not attempted",
        failing={"store"},
    )

    scenario(
        "4. Feature extraction fails - alerts skip, plots are unaffected",
        failing={"features"},
    )

    scenario(
        "5. Reprocess plots only, on an upload stored earlier",
        only={"plots"},
        upload=FakeUpload(
            parse_status="parsed", plots_status="failed", features_status="ready"
        ),
    )

    scenario(
        "6. Reprocess plots on an upload that was never stored - refused",
        only={"plots"},
    )

    print("\n  7. A misspelled step name is rejected before anything runs")
    print("  " + "-" * 62)
    try:
        mp.run_pipeline(
            db=None,
            upload=FakeUpload(),
            parsed={"sample_count": 0},
            cfg={"sampling_rate_hz": 25600.0},
            only={"plotz"},
        )
    except ValueError as exc:
        print(f"    ValueError: {exc}")

    print("\n" + "=" * 66)
    print("  Scenario 5 is the point: 'store' did not run, yet 'plots' proceeded,")
    print("  because upload.parse_status already said 'parsed'. The status columns")
    print("  you already write are what makes reprocessing possible.")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
