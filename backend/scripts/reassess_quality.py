"""Re-run the data-quality engine over captures already stored — VIK-022.

The engine's thresholds are calibrated against this gateway, so they move.
When they do, every assessment made before the move was made by different
rules, and the captures have to be graded again or the two cannot be
compared.

The move that prompted this script: the engine took the converter's
quantisation step from the sensitivity on the sensor record, and that record
is wrong. `gateway/.env` declares 500 mV/g on channels 0 and 1; the stored
samples are quantised in 0.0015 g steps on all eight, which is 100 mV/g.
Judged against a step five times finer than the converter can produce, every
one of those channels looked coarsely quantised: 245 of 248 assessments on
channels 0 and 1 failed the noise-floor check, for a fault that was in the
configuration rather than the signal. The engine now measures the step from
the samples, and these captures need grading by that rule.

Only `data_quality_assessments` is touched. Features and trends are left
exactly as they are -- re-running the whole feature pipeline to correct a
quality grade would rewrite three million rows to change a few hundred.

Idempotent: persist_quality replaces a capture's assessment rather than
adding to it, because re-running the engine is a corrected opinion and not a
second one.

    python scripts/reassess_quality.py --dry-run
    python scripts/reassess_quality.py --limit 5
    python scripts/reassess_quality.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                                      # noqa: E402

from app import crud                                             # noqa: E402
from app.database import SessionLocal                            # noqa: E402
from app.models.measurement import SensorDataUpload              # noqa: E402
from app.services.feature_storage import machine_shaft_speed     # noqa: E402
from app.services.quality_storage import persist_quality         # noqa: E402

from recompute_features import parsed_for                        # noqa: E402

log = logging.getLogger("reassess")


def candidates(db) -> list:
    """Every upload whose samples are still in the database.

    A capture with no samples cannot be re-graded, and its old assessment is
    left alone rather than deleted: a judgement made by superseded rules is
    still the judgement that was made, and the engine version stored beside
    it says which rules those were.
    """
    return [r[0] for r in db.execute(text("""
        SELECT DISTINCT u.id FROM sensor_data_uploads u
          JOIN raw_vibration_captures c ON c.upload_id = u.id
         ORDER BY u.id
    """)).fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        ids = candidates(db)
        if args.limit:
            ids = ids[:args.limit]
        log.info("%d capture(s) to re-assess", len(ids))
        if args.dry_run:
            return 0

        done = skipped = failed = 0
        warned = 0
        levels: dict[str, int] = {}
        started = time.perf_counter()
        for i, upload_id in enumerate(ids, start=1):
            upload = db.get(SensorDataUpload, upload_id)
            if upload is None:
                skipped += 1
                continue
            try:
                parsed, rate, origin = parsed_for(db, upload)
                if parsed is None:
                    skipped += 1
                    continue
                if not rate:
                    rate = float(db.execute(text(
                        "SELECT sample_rate_hz FROM raw_vibration_captures "
                        "WHERE upload_id = :u"), {"u": str(upload_id)}).scalar()
                        or 25600.0)
                sensor = crud.get_sensor_by_id(db, upload.sensor_id)
                machine = machine_shaft_speed(db, upload, parsed, rate)
                summary = persist_quality(
                    db,
                    upload_id=upload.id,
                    sensor_id=upload.sensor_id,
                    channels=(parsed.get("channels") or {}),
                    sampling_rate_hz=rate,
                    expected_samples=parsed.get("sample_count"),
                    sensitivity_mv_per_g=(float(sensor.sensitivity)
                                          if sensor is not None and sensor.sensitivity
                                          else None),
                    shaft_hz=machine.hz if machine.usable else None,
                )
                db.commit()
                levels[summary["level"]] = levels.get(summary["level"], 0) + 1
                if summary.get("warnings"):
                    warned += 1
                    if warned == 1:
                        log.info("  %s", summary["warnings"][0])
                done += 1
                if i % 25 == 0 or i == len(ids):
                    log.info("  [%3d/%d] %s -> %s", i, len(ids), upload_id,
                             summary["level"])
            except Exception as exc:
                db.rollback()
                log.error("  [%3d/%d] %s: %s: %s", i, len(ids), upload_id,
                          type(exc).__name__, exc)
                failed += 1

        log.info("done: %d re-assessed, %d skipped, %d failed in %.1f s",
                 done, skipped, failed, time.perf_counter() - started)
        log.info("capture levels: %s",
                 ", ".join(f"{k}={v}" for k, v in sorted(levels.items())))
        if warned:
            log.warning("%d capture(s) carry a sensitivity mismatch warning -- "
                        "the device applied a different sensitivity from the "
                        "one on the sensor record", warned)
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
