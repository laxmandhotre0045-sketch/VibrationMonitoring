"""Command line access to the report agent.

    python -m report_agent build "cooling water pump"
    python -m report_agent build "cooling water pump" --out report.md
    python -m report_agent build "pump" --power-kw 55 --foundation rigid --separate-driver

Phase 1: measured and computed data only. No language model is involved, so
this runs without an API key and costs nothing.

Output is forced to ASCII for the console, for the same reason as kb_agent: a
Windows console is cp1252 and machine names carry characters it cannot encode.
The file written by ``--out`` keeps full UTF-8.
"""

from __future__ import annotations

import argparse
import logging
import sys
import unicodedata
from pathlib import Path

from report_agent.pipeline import ReportContext, build_report
from report_agent.render import render, verify

_TRANSLIT = {
    "—": "-", "–": "-", "’": "'", "“": '"', "”": '"',
    "…": "...", "×": "x", "°": " deg", "µ": "u",
    "·": "-", "⚠": "!", "→": "->",
}


def _ascii(text: str) -> str:
    out = "".join(_TRANSLIT.get(ch, ch) for ch in text or "")
    return unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m report_agent",
        description="Build a vibration condition report from platform data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a report for one sensor")
    build.add_argument("sensor", help="Sensor UUID, device id, or descriptive text")
    build.add_argument("--from", dest="from_date", help="Start date, YYYY-MM-DD")
    build.add_argument("--to", dest="to_date", help="End date, YYYY-MM-DD")
    build.add_argument("--max-captures", type=int, default=200)
    build.add_argument("--power-kw", type=float, help="Rated power, for the ISO group")
    build.add_argument("--foundation", choices=["rigid", "flexible"])
    driver = build.add_mutually_exclusive_group()
    driver.add_argument("--integrated-driver", action="store_true",
                        help="Pump with an integrated driver (ISO Group 4)")
    driver.add_argument("--separate-driver", action="store_true",
                        help="Pump with a separate driver (ISO Group 3)")
    build.add_argument(
        "--acceleration-unit", choices=["g", "v"],
        help="What the stored acceleration values physically are: g, or volts "
             "from the accelerometer. Required before velocity can be derived.",
    )
    build.add_argument("--out", metavar="PATH", help="Write the report to a file")
    build.add_argument("--quiet", action="store_true", help="Only print problems")

    args = parser.parse_args(argv)
    logging.disable(logging.WARNING)

    integrated: bool | None = None
    if args.integrated_driver:
        integrated = True
    elif args.separate_driver:
        integrated = False

    ctx = ReportContext(
        sensor=args.sensor,
        from_date=args.from_date,
        to_date=args.to_date,
        max_captures=args.max_captures,
        power_kw=args.power_kw,
        foundation=args.foundation,
        integrated_driver=integrated,
        acceleration_unit=args.acceleration_unit,
    )

    result = build_report(ctx)
    if result.failed("collect"):
        error = result.outcomes["collect"].error
        print(f"Could not build the report: {error}", file=sys.stderr)
        return 1

    rendered = render(ctx.ledger, ctx.data)
    check = verify(ctx.ledger, rendered)
    text = rendered.text

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Report written to {args.out}  ({len(ctx.ledger)} facts)")
    elif not args.quiet:
        print(_ascii(text))

    print()
    print("-" * 78)
    steps = ", ".join(
        f"{name}={outcome.status}" for name, outcome in result.outcomes.items()
    )
    print(f"  steps    : {steps}")
    print(f"  facts    : {len(ctx.ledger)}")
    print(f"  verified : {'PASS - every figure traces to the ledger' if check.ok else 'FAILED'}")
    for problem in check.problems():
        print(f"      - {_ascii(problem)}")
    for note in check.notes:
        print(f"      note: {_ascii(note)}")
    print("-" * 78)

    return 0 if (result.ok and check.ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
