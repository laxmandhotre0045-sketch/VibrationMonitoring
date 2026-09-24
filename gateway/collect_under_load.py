"""Watch the live capture stream and collect ten samples of a RUNNING machine.

MOM item 2 was tested against an idle machine: strip the DC offset and every
channel sat between 0.002 g and 0.023 g, which is sensor bias and electrical
noise. Items 3 (prediction) and 11 (vibration vs noise) need data with real
signal in it, and no amount of analysis turns an idle recording into one.

Nobody can predict when the pump will be switched on, so this watches instead
of asking. It reads each new archived capture as the uploader writes it, judges
whether the machine is turning, and copies the first ten running captures into
a separate folder so the acceptance harness can be pointed at them unchanged.

Judging "running" from the data, not from a switch:

  DC offset is removed first. An accelerometer at rest still reads a standing
  bias -- ch7 sits near -0.145 g -- and a threshold on the raw value would call
  a stationary machine active purely because of its bias. What matters is the
  AC content: the part that varies.

  A machine is called RUNNING when the loudest channel's AC RMS rises above
  THRESHOLD_G. The idle floor measured across seventeen captures was 0.0244 g at
  its very worst, so the default sits clear of it while staying far below
  anything a real pump produces.

Run it beside the uploader:

    python collect_under_load.py                 # wait, then collect 10
    python collect_under_load.py --threshold 0.04
    python collect_under_load.py --status        # judge what is already there
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "archive"
LOAD_DIR = HERE / "archive_under_load"

#: Above the measured idle floor (worst channel, worst capture: 0.0244 g) with
#: room to spare, and far below what a turning pump produces. Deliberately not
#: a "1.5x the floor" rule: the floor is noise, and scaling noise gives a
#: threshold that drifts with the noise rather than with the machine.
THRESHOLD_G = 0.035

#: Measured idle ceiling, kept here so the threshold's justification travels
#: with the number rather than living only in a report.
IDLE_CEILING_G = 0.0244


def channel_ac_rms(path: Path) -> list[float]:
    """AC RMS per channel: the standard deviation about each channel's mean.

    Reads with the standard library only, so this runs without numpy on a
    gateway machine that has nothing installed.
    """
    sums: list[float] = []
    sq: list[float] = []
    n = 0
    with path.open(newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header:
            return []
        width = len(header) - 1
        sums = [0.0] * width
        sq = [0.0] * width
        for row in reader:
            if len(row) != width + 1:
                continue
            n += 1
            for i in range(width):
                try:
                    v = float(row[i + 1])
                except ValueError:
                    continue
                sums[i] += v
                sq[i] += v * v
    if n < 2:
        return []
    out = []
    for i in range(len(sums)):
        mean = sums[i] / n
        var = max(sq[i] / n - mean * mean, 0.0)   # clamp: rounding can go < 0
        out.append(var ** 0.5)
    return out


def verdict(path: Path, threshold: float) -> tuple[bool, float, list[float]]:
    acs = channel_ac_rms(path)
    if not acs:
        return False, 0.0, []
    peak = max(acs)
    return peak > threshold, peak, acs


def report_existing(threshold: float) -> None:
    files = sorted(ARCHIVE.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        print(f"No captures in {ARCHIVE}")
        return
    print(f"{'capture':>10}  {'max AC rms':>11}  state")
    running = 0
    for f in files:
        ok, peak, _ = verdict(f, threshold)
        if ok:
            running += 1
        print(f"{f.name[9:15]:>10}  {peak:>11.5f}  {'RUNNING' if ok else 'idle'}")
    print(f"\n{running} of {len(files)} captures are above {threshold} g "
          f"(measured idle ceiling {IDLE_CEILING_G} g)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, default=THRESHOLD_G,
                    help=f"AC RMS in g above which the machine counts as running "
                         f"(default {THRESHOLD_G})")
    ap.add_argument("--count", type=int, default=10, help="samples to collect")
    ap.add_argument("--status", action="store_true",
                    help="judge the captures already archived and exit")
    ap.add_argument("--interval", type=float, default=15.0,
                    help="seconds between scans")
    args = ap.parse_args()

    if args.status:
        report_existing(args.threshold)
        return 0

    LOAD_DIR.mkdir(exist_ok=True)
    # Only files that appear from now on are candidates. Re-judging the backlog
    # would fill the set with captures taken before the machine was started.
    seen = {p.name for p in ARCHIVE.glob("*.csv")}
    collected = sorted(p.name for p in LOAD_DIR.glob("*.csv"))

    print(f"Watching {ARCHIVE}")
    print(f"Threshold {args.threshold} g AC rms  (idle ceiling measured at {IDLE_CEILING_G} g)")
    print(f"Need {args.count}, have {len(collected)}. Start the pump when ready.")
    print("-" * 66)

    idle_seen = 0
    while len(collected) < args.count:
        for path in sorted(ARCHIVE.glob("*.csv"), key=lambda p: p.stat().st_mtime):
            if path.name in seen:
                continue
            if time.time() - path.stat().st_mtime < 2:
                continue            # still being written
            seen.add(path.name)
            ok, peak, acs = verdict(path, args.threshold)
            stamp = path.name[9:15]
            if ok:
                shutil.copy2(path, LOAD_DIR / path.name)
                collected.append(path.name)
                loud = max(range(len(acs)), key=lambda i: acs[i])
                print(f"[{stamp}] RUNNING  max AC rms {peak:.5f} g on ch{loud}  "
                      f"-> collected {len(collected)}/{args.count}")
            else:
                idle_seen += 1
                if idle_seen % 4 == 1:
                    print(f"[{stamp}] idle     max AC rms {peak:.5f} g  (waiting)")
        if len(collected) < args.count:
            time.sleep(args.interval)

    print("-" * 66)
    print(f"Collected {len(collected)} running captures in {LOAD_DIR}")
    print("Now run the acceptance harness against them, unchanged:")
    print(f"  python test_10_samples.py --archive {LOAD_DIR.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
