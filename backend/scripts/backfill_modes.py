"""Decide the operating mode for captures stored before the detector existed.

The 161 captures on this platform predate VIK-039, so they carry no mode and
a mode-scoped baseline would have nothing to build from. Re-running the
detector over them is cheap -- it needs the shaft speed and one level per
capture, not a spectrum per channel.

Idempotent: persist_mode replaces a capture's verdict rather than adding to
it.

    python scripts/backfill_modes.py --dry-run
    python scripts/backfill_modes.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                                      # noqa: E402

from app.database import SessionLocal                            # noqa: E402
from app.models.measurement import SensorDataUpload              # noqa: E402
from app.services.feature_storage import machine_shaft_speed     # noqa: E402
from app.services.mode_storage import (                          # noqa: E402
    equipment_for_sensor,
    persist_mode,
)
from app.services.quality_storage import latest_for_upload       # noqa: E402

from recompute_features import parsed_for                        # noqa: E402

log = logging.getLogger("backfill-modes")


def quality_summary_for(db, upload_id):
    """The stored quality verdict, shaped the way the detector expects.

    Read back rather than recomputed: the mode must be decided against the
    verdict this capture actually carries, not a fresh one that might
    disagree with what is on record beside it.
    """
    stored = latest_for_upload(db, upload_id)
    channels = {}
    for channel, row in stored.items():
        if channel is None:
            continue
        channels[channel] = {"checks": row.get("checks") or []}
    return {"channels": channels} if channels else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    db = SessionLocal()
    try:
        ids = [r[0] for r in db.execute(text("""
            SELECT DISTINCT u.id FROM sensor_data_uploads u
              JOIN raw_vibration_captures c ON c.upload_id = u.id
             ORDER BY u.id
        """)).fetchall()]
        if args.limit:
            ids = ids[:args.limit]
        print(f"{len(ids)} capture(s) to classify")
        if args.dry_run:
            return 0

        labels = Counter()
        reasons = Counter()
        done = failed = 0
        for upload_id in ids:
            upload = db.get(SensorDataUpload, upload_id)
            if upload is None:
                continue
            try:
                parsed, rate, _ = parsed_for(db, upload)
                if parsed is None:
                    continue
                if not rate:
                    rate = float(db.execute(text(
                        "SELECT sample_rate_hz FROM raw_vibration_captures "
                        "WHERE upload_id = :u"), {"u": str(upload_id)}).scalar()
                        or 25600.0)
                machine = machine_shaft_speed(db, upload, parsed, rate)
                verdict = persist_mode(
                    db,
                    upload_id=upload.id,
                    sensor_id=upload.sensor_id,
                    equipment_id=equipment_for_sensor(db, upload.sensor_id),
                    channels=(parsed.get("channels") or {}),
                    shaft_hz=machine.hz,
                    shaft_usable=machine.usable,
                    shaft_source=machine.source,
                    quality_summary=quality_summary_for(db, upload.id),
                )
                db.commit()
                labels[verdict.label] += 1
                if verdict.is_unknown:
                    reasons[verdict.reason[:80]] += 1
                done += 1
            except Exception as exc:
                db.rollback()
                log.error("  %s: %s: %s", upload_id, type(exc).__name__, exc)
                failed += 1

        print(f"\nclassified {done}, failed {failed}")
        for label, count in labels.most_common():
            print(f"   {label:<18}{count}")
        if reasons:
            print("\nwhy the unknown ones are unknown:")
            for reason, count in reasons.most_common(3):
                print(f"   {count:>4}x {reason}...")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
