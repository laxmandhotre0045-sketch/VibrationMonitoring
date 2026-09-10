"""Command line access to the sensor agent.

    python -m sql_agent list
    python -m sql_agent data "cooling water pump" --csv out.csv

Everything the agent can do is reachable from here. If the CLI and a calling
agent disagree, the agent is wrong -- both go through the same
``SensorDataAgent`` methods, so this doubles as the smoke test for a deployment.

Output is deliberately ASCII. A Windows console defaults to cp1252 and raises
UnicodeEncodeError on an em dash, which would turn a working query into a
traceback for no reason.
"""

from __future__ import annotations

import argparse
import sys

from sql_agent.agent import AgentResult, SensorDataAgent
from sql_agent.config import PLATFORM_BASE_URL, PLATFORM_EMAIL, PLATFORM_MAX_UPLOADS


def _print_sensor_list(result: AgentResult) -> None:
    if not result.data:
        print("No sensors matched.")
        return
    print(f"{len(result.data)} sensor(s):\n")
    for e in result.data:
        active = "" if e.get("is_active", True) else "  [inactive]"
        print(f"  {e['machine_name']} / {e['mounting_location']} ({e['orientation']}){active}")
        print(f"    plant : {e['plant_name']} / {e['area']} / {e['line']}")
        print(f"    id    : {e['sensor_id']}")
        if e.get("device_id"):
            print(f"    device: {e['device_id']}")
        print()


def _print_data(result: AgentResult, *, rows_to_show: int) -> None:
    m = result.meta
    truncated = (
        f" (newest {m['captures_exported']} of {m['captures_available']})"
        if m.get("truncated")
        else ""
    )
    print(f"{m['machine_name']} / {m['mounting_location']} ({m['orientation']})")
    print(f"  sensor    : {m['sensor_id']}")
    print(f"  plant     : {m['plant_name']} / {m['area']} / {m['line']}")
    print(f"  rows      : {m['csv_rows']}")
    print(f"  captures  : {m['captures_exported']}{truncated}")
    print(f"  channels  : {m['channels']}")
    print(f"  features  : {len(m['feature_codes'])}")
    print(f"  window    : {m['first_observed_at']} -> {m['last_observed_at']}")
    print(f"  statuses  : {m['status_counts']}")
    if m.get("csv_path"):
        print(f"  saved to  : {m['csv_path']}")

    if not result.data or rows_to_show <= 0:
        return

    print(f"\n  first {min(rows_to_show, len(result.data))} reading(s):")
    print(f"    {'observed_at':<28} {'ch':>3} {'feature':<24} {'value':>14}  status")
    for r in result.data[:rows_to_show]:
        print(
            f"    {str(r['observed_at'])[:27]:<28} {str(r['channel']):>3} "
            f"{str(r['feature_code']):<24} {str(r['value']):>14}  {r['status']}"
        )

    print("\n  Caveats:")
    for c in m.get("caveats", []):
        print(f"    - {c}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sql_agent",
        description="Read sensor measurement data from the SensoVibe platform.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the raw result envelope as JSON."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List sensors")
    p_list.add_argument("filter", nargs="*", help="Optional words to narrow the list")

    p_resolve = sub.add_parser("resolve", help="Resolve text to one sensor")
    p_resolve.add_argument("sensor", help="UUID, device id, or descriptive text")

    p_data = sub.add_parser("data", help="Read a sensor's measurement history")
    p_data.add_argument("sensor", help="UUID, device id, or descriptive text")
    p_data.add_argument("--from", dest="from_date", help="Start date, YYYY-MM-DD")
    p_data.add_argument("--to", dest="to_date", help="End date, YYYY-MM-DD")
    p_data.add_argument(
        "--max-captures", type=int, default=PLATFORM_MAX_UPLOADS, help="Newest N captures"
    )
    p_data.add_argument("--csv", metavar="PATH", help="Write the CSV to this path")
    p_data.add_argument(
        "--rows", type=int, default=5, help="Readings to print (default 5, 0 for none)"
    )

    p_latest = sub.add_parser("latest", help="Read only the most recent capture")
    p_latest.add_argument("sensor", help="UUID, device id, or descriptive text")
    p_latest.add_argument(
        "--rows", type=int, default=5, help="Readings to print (default 5, 0 for none)"
    )

    p_check = sub.add_parser("check", help="Verify the platform connection and login")

    args = parser.parse_args(argv)
    agent = SensorDataAgent()

    if args.command == "check":
        print(f"platform : {PLATFORM_BASE_URL}")
        print(f"login as : {PLATFORM_EMAIL}")
        result = agent.list_sensors()
        if result.ok:
            print(f"status   : OK - {result.meta['count']} sensor(s) visible")
            return 0
        print(f"status   : FAILED - {result.error}")
        return 1

    if args.command == "list":
        result = agent.list_sensors(" ".join(args.filter))
    elif args.command == "resolve":
        result = agent.resolve(args.sensor)
    elif args.command == "latest":
        result = agent.get_latest_reading(args.sensor)
    else:
        result = agent.get_sensor_data(
            args.sensor,
            from_date=args.from_date,
            to_date=args.to_date,
            max_captures=args.max_captures,
            include_csv=bool(args.csv),
        )

    if args.json:
        print(result.to_json(indent=2))
        return 0 if result.ok else 1

    if not result.ok:
        # Errors to stderr so `... --json > file` keeps the file clean and a
        # shell pipeline can still see what went wrong.
        print(f"Error: {result.error}", file=sys.stderr)
        return 1

    if result.kind == "sensor_list":
        _print_sensor_list(result)
    elif result.kind == "sensor_resolve":
        e = result.data[0]
        print(f"{e['machine_name']} / {e['mounting_location']} ({e['orientation']})")
        print(f"  id: {e['sensor_id']}")
    else:
        if getattr(args, "csv", None):
            with open(args.csv, "w", encoding="utf-8", newline="") as fh:
                fh.write(result.meta["csv"])
            result.meta["csv_path"] = args.csv
        _print_data(result, rows_to_show=getattr(args, "rows", 5))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
