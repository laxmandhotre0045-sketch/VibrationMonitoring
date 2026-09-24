"""Recompute stored features for captures analysed by older code.

Two reasons a stored feature row is wrong or missing:

1. It was computed before the shaft speed came from the machine record. Every
   order-based number in those rows was divided by the tallest line in the
   spectrum, which on this pump is 2x or 4x the true speed on all eight
   channels. amplitude_1x/2x/3x were read at the wrong frequencies.

2. It was computed before the shape and burst features were measured on the
   centred signal, so a channel's standing bias counted as vibration and five
   of eight channels reported every sample as a four-sigma impact.

And one reason a capture has no features at all: `/api/v1/ingest/raw` stores
the samples and deliberately does not analyse them, because at 50 kSPS across
eight channels that work does not belong in a web request. The background
worker that was meant to pick them up is VIK-013 and does not exist yet, so
101 device captures are sitting unanalysed. Until it lands, this script is
how they get processed.

Idempotent: `persist_upload_features_and_trends` deletes a capture's existing
rows before writing new ones, so running this twice leaves one set.

    python scripts/recompute_features.py --dry-run
    python scripts/recompute_features.py --limit 5
    python scripts/recompute_features.py --with-trends
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text                                      # noqa: E402

from app.database import SessionLocal                            # noqa: E402
from app.models.measurement import SensorDataUpload              # noqa: E402
from app.services.feature_storage import (                       # noqa: E402
    machine_shaft_speed,
    persist_upload_features_and_trends,
)
from app.services.plot_generator import load_parsed_data         # noqa: E402

log = logging.getLogger("recompute")

#: A capture is up to date when it carries a feature only the current code
#: produces. Cheaper and more honest than a version column nobody maintains.
MARKER_FEATURE = "spectral_entropy"



def parsed_for(db, upload) -> tuple[dict | None, float, str]:
    """The capture's samples, from wherever they survive.

    The database copy comes first. Migration 018 stores every device capture
    as float8[] rows, and that is the durable one: the oldest uploads here
    have lost their .json files to retention or to a path that moved, while
    their samples are still in raw_vibration_channels. Reading the file first
    would skip 16 captures that are perfectly recoverable.
    """
    capture = db.execute(text("""
        SELECT id, sample_rate_hz, channel_count
          FROM raw_vibration_captures WHERE upload_id = :u
    """), {"u": str(upload.id)}).fetchone()

    if capture is not None:
        rows = db.execute(text("""
            SELECT channel_index, samples FROM raw_vibration_channels
             WHERE capture_id = :c ORDER BY channel_index
        """), {"c": str(capture.id)}).fetchall()
        if rows:
            channels = {f"ch{int(i)}": list(samples) for i, samples in rows}
            first = next(iter(channels.values()))
            rate = float(capture.sample_rate_hz or 25600.0)
            return ({
                "channels": channels,
                "channel_count": len(channels),
                "sample_count": len(first),
                "timestamps": [i / rate for i in range(len(first))],
            }, rate, "database")

    if upload.parsed_data_path and os.path.exists(upload.parsed_data_path):
        return load_parsed_data(upload.parsed_data_path), 0.0, "file"

    return None, 0.0, "missing"


def candidates(db, include_current: bool):
    where = "" if include_current else f"""
        AND NOT EXISTS (SELECT 1 FROM measurement_channel_features f
                         WHERE f.upload_id = u.id
                           AND f.feature_code = '{MARKER_FEATURE}')
    """
    rows = db.execute(text(f"""
        SELECT u.id FROM sensor_data_uploads u
         WHERE TRUE {where}
         ORDER BY u.created_at
    """)).fetchall()
    return [r[0] for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be done and stop")
    ap.add_argument("--limit", type=int, default=0, help="process at most N uploads")
    ap.add_argument("--with-trends", action="store_true",
                    help="also write the 32-segment trend rows (9,216 per capture; "
                         "about 3 MB each). Off by default: the features are what "
                         "baselines and grading read, and trends for historical "
                         "captures can be produced later from the same samples.")
    ap.add_argument("--all", action="store_true",
                    help="include captures that are already up to date")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db = SessionLocal()
    try:
        ids = candidates(db, include_current=args.all)
        if args.limit:
            ids = ids[:args.limit]
        log.info("%d upload(s) to process", len(ids))
        if args.dry_run:
            return 0

        done = skipped = failed = 0
        started = time.perf_counter()
        for i, upload_id in enumerate(ids, start=1):
            upload = db.get(SensorDataUpload, upload_id)
            if upload is None:
                skipped += 1
                continue
            try:
                parsed, rate, origin = parsed_for(db, upload)
            except Exception as exc:
                log.error("  [%3d/%d] %s: could not read samples: %s",
                          i, len(ids), upload_id, exc)
                failed += 1
                continue
            if parsed is None:
                # Nothing survives. Inventing rows for it would be worse than
                # leaving the capture unanalysed.
                log.info("  [%3d/%d] %s: no samples anywhere, skipped",
                         i, len(ids), upload_id)
                skipped += 1
                continue
            try:
                if not rate:
                    rate = float(
                        db.execute(text(
                            "SELECT sample_rate_hz FROM raw_vibration_captures "
                            "WHERE upload_id = :u"), {"u": str(upload_id)}).scalar()
                        or 25600.0
                    )
                machine = machine_shaft_speed(db, upload, parsed, rate)
                n_feat, n_trend = persist_upload_features_and_trends(
                    db, upload, parsed, rate, with_trends=args.with_trends)
                db.commit()
                log.info("  [%3d/%d] %s: %d features, %d trends, shaft %s (%s), "
                         "samples from %s",
                         i, len(ids), upload_id, n_feat, n_trend,
                         f"{machine.hz:.2f} Hz" if machine.hz else "unknown",
                         machine.source, origin)
                done += 1
            except Exception as exc:
                db.rollback()
                log.error("  [%3d/%d] %s: %s: %s",
                          i, len(ids), upload_id, type(exc).__name__, exc)
                failed += 1

        elapsed = time.perf_counter() - started
        log.info("done: %d recomputed, %d skipped, %d failed in %.1f s",
                 done, skipped, failed, elapsed)
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
