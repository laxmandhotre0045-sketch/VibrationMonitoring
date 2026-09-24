"""Command-line access to the vibration domain tools — no LLM, no server.

Every calculation the chatbot can do is reachable here, which makes it the
fastest way to sanity-check a number the bot produced. If the CLI and the bot
disagree, the bot is wrong.

    python scripts/vib_cli.py bearing --designation 6205 --rpm 1750
    python scripts/vib_cli.py iso --vrms 4.9 --group 3 --foundation rigid
    python scripts/vib_cli.py convert 1.0 --from g --to mm/s --freq 100
    python scripts/vib_cli.py machine save examples/P-101.json
    python scripts/vib_cli.py machine show P-101 --rpm 1478
    python scripts/vib_cli.py diagnose --rpm 1750 --peaks "1.0:0.9,2.0:0.2"
    python scripts/vib_cli.py diagnose --machine P-101 --rpm 1478 --peaks "3.5:0.9,1.0:0.2"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vibcore import bearing as bearing_mod  # noqa: E402
from vibcore import iso10816, units  # noqa: E402
from app.domain.machine import (  # noqa: E402
    MachineProfile,
    bearing_orders_for,
    derived_frequencies,
    machine_store,
    summarize_frequencies,
)
from vibcore.signatures import (  # noqa: E402
    MachineContext,
    SpectralPeak,
    cross_check_bearing_peaks,
    match_faults,
    summarize as summarize_faults,
)


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _parse_peaks(text: str, shaft_hz: float) -> list[SpectralPeak]:
    """Parse "order:amplitude,order:amplitude" into peaks.

    An order suffixed with "hz" is taken as an absolute frequency instead, so
    both "3.585:0.9" and "104.6hz:0.9" work.
    """
    peaks: list[SpectralPeak] = []
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise ValueError(f"expected 'order:amplitude', got {chunk!r}")
        left, right = chunk.split(":", 1)
        left = left.strip().lower()
        amplitude = float(right)
        if left.endswith("hz"):
            frequency = float(left[:-2])
            order = frequency / shaft_hz
        else:
            order = float(left)
            frequency = order * shaft_hz
        peaks.append(
            SpectralPeak(frequency_hz=frequency, amplitude=amplitude, order=order)
        )
    return peaks


# --------------------------------------------------------------------------


def cmd_bearing(args) -> int:
    geom = bearing_mod.geometry_from_inputs(
        designation=args.designation,
        n_balls=args.n_balls,
        ball_dia_mm=args.ball_dia,
        pitch_dia_mm=args.pitch_dia,
        contact_angle_deg=args.contact_angle,
    )
    if geom is None:
        return _fail(
            f"Could not resolve geometry for {args.designation!r}. "
            "Supply --n-balls, --ball-dia and --pitch-dia from the bearing datasheet."
        )

    freqs = bearing_mod.fault_frequencies(geom, args.rpm)
    if args.json:
        print(json.dumps(bearing_mod.build_record(freqs).as_dict(), indent=2))
    else:
        print(bearing_mod.summarize(freqs))
    return 0


def cmd_iso(args) -> int:
    group = args.group
    if group is None:
        group = iso10816.infer_machine_group(
            power_kw=args.power_kw,
            machine_type=args.type,
            integrated_driver=args.integrated_driver,
        )
        if group is None:
            return _fail(
                "Could not infer the machine group. Pass --group 1|2|3|4, or "
                "give --power-kw and --type."
            )
        print(f"(inferred machine group {group} from --power-kw/--type)\n")

    result = iso10816.severity_zone(args.vrms, group, args.foundation, args.standard)
    if args.json:
        print(json.dumps(iso10816.build_record(result).as_dict(), indent=2))
    else:
        print(iso10816.summarize(result))
    return 0


def cmd_convert(args) -> int:
    result = units.convert_amplitude(
        args.value,
        from_unit=getattr(args, "from"),
        to_unit=args.to,
        frequency_hz=args.freq,
        from_measure=args.from_measure,
        to_measure=args.to_measure,
    )
    if args.json:
        print(json.dumps(units.build_record(result, args.value).as_dict(), indent=2))
    else:
        print(units.summarize(result, args.value))
    return 0


def cmd_machine(args) -> int:
    if args.machine_action == "list":
        ids = machine_store.list_ids()
        print("\n".join(ids) if ids else "(no machines registered)")
        return 0

    if args.machine_action == "save":
        path = Path(args.path)
        if not path.exists():
            return _fail(f"{path} does not exist")
        profile = MachineProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
        saved = machine_store.save(profile)
        print(f"Saved {profile.machine_id} -> {saved}")
        print(f"ISO group: {profile.resolved_iso_group()}")
        return 0

    if args.machine_action == "show":
        profile = machine_store.load(args.machine_id)
        if profile is None:
            return _fail(f"machine {args.machine_id!r} not found")
        print(f"{profile.machine_id} — {profile.name or '(unnamed)'} [{profile.type or 'unknown type'}]")
        print(f"Foundation: {profile.foundation}   ISO group: {profile.resolved_iso_group()}")
        print()
        print(summarize_frequencies(derived_frequencies(profile, args.point, args.rpm)))
        return 0

    return _fail("unknown machine action")


def cmd_diagnose(args) -> int:
    profile = None
    if args.machine:
        profile = machine_store.load(args.machine)
        if profile is None:
            return _fail(f"machine {args.machine!r} not found")

    rpm = args.rpm or (profile.driver.rated_rpm if profile else None)
    if not rpm:
        return _fail("shaft speed unknown — pass --rpm, or use a machine with a rated speed")
    shaft_hz = rpm / 60.0

    try:
        peaks = _parse_peaks(args.peaks, shaft_hz)
    except ValueError as exc:
        return _fail(str(exc))
    if not peaks:
        return _fail("no peaks supplied")

    if profile is not None:
        ctx = MachineContext(
            shaft_rpm=rpm,
            bearing_orders=bearing_orders_for(profile, args.point, rpm),
            vane_pass_order=float(profile.driven.n_vanes) if profile.driven.n_vanes else None,
            line_freq_hz=profile.driver.line_freq_hz,
            has_journal_bearings=profile.has_journal_bearings(),
            has_rolling_bearings=profile.has_rolling_bearings(),
        )
    else:
        bearing_orders = {}
        if args.bearing:
            geom = bearing_mod.resolve_bearing(args.bearing)
            if geom is None:
                return _fail(f"could not resolve bearing {args.bearing!r}")
            freqs = bearing_mod.fault_frequencies(geom, rpm)
            bearing_orders = {
                "bpfo": freqs.bpfo_order,
                "bpfi": freqs.bpfi_order,
                "bsf": freqs.bsf_order,
                "bsf2x": freqs.bsf_2x_order,
                "ftf": freqs.ftf_order,
            }
        ctx = MachineContext(shaft_rpm=rpm, bearing_orders=bearing_orders)

    notes = cross_check_bearing_peaks(peaks, ctx.bearing_orders)
    hypotheses = match_faults(peaks, ctx, top_n=args.top_n)

    print(f"Shaft speed {rpm:.0f} rpm ({shaft_hz:.3f} Hz), {len(peaks)} peaks\n")
    print(summarize_faults(hypotheses, notes))

    if hypotheses:
        print("\nNext checks for the leading hypothesis:")
        for check in hypotheses[0].confirming_checks:
            print(f"  - {check}")
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vib_cli",
        description="Vibration analysis calculations (deterministic, no LLM).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json", action="store_true", help="emit the full computation record")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bearing", help="bearing fault frequencies (BPFO/BPFI/BSF/FTF)")
    p.add_argument("--designation", "-b", help="e.g. 6205, 'SKF 6205-2RS'")
    p.add_argument("--rpm", type=float, required=True)
    p.add_argument("--n-balls", type=int, dest="n_balls")
    p.add_argument("--ball-dia", type=float, dest="ball_dia", help="mm")
    p.add_argument("--pitch-dia", type=float, dest="pitch_dia", help="mm")
    p.add_argument("--contact-angle", type=float, dest="contact_angle", default=0.0, help="degrees")
    p.set_defaults(func=cmd_bearing)

    p = sub.add_parser("iso", help="ISO 10816-3 / 20816-3 severity zone")
    p.add_argument("--vrms", type=float, required=True, help="broadband velocity, mm/s RMS")
    p.add_argument("--group", type=int, choices=[1, 2, 3, 4])
    p.add_argument("--foundation", choices=["rigid", "flexible"], default="rigid")
    p.add_argument("--standard", choices=["10816-3", "20816-3"], default="10816-3")
    p.add_argument("--power-kw", type=float, dest="power_kw", help="used to infer --group")
    p.add_argument("--type", help="pump, motor, fan... used to infer --group")
    p.add_argument("--integrated-driver", action="store_true", dest="integrated_driver")
    p.set_defaults(func=cmd_iso)

    p = sub.add_parser("convert", help="convert amplitude between units/measures")
    p.add_argument("value", type=float)
    p.add_argument("--from", required=True, help="g, m/s2, mm/s, in/s, um, mil")
    p.add_argument("--to", required=True)
    p.add_argument("--freq", type=float, help="Hz — required when the quantity changes")
    p.add_argument("--from-measure", dest="from_measure", default="rms", choices=["rms", "peak", "pk-pk"])
    p.add_argument("--to-measure", dest="to_measure", default="rms", choices=["rms", "peak", "pk-pk"])
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("machine", help="machine profiles and their forcing frequencies")
    msub = p.add_subparsers(dest="machine_action", required=True)
    msub.add_parser("list", help="list registered machines")
    sp = msub.add_parser("save", help="register a machine from a JSON file")
    sp.add_argument("path")
    sp = msub.add_parser("show", help="show a machine's forcing-frequency table")
    sp.add_argument("machine_id")
    sp.add_argument("--rpm", type=float, help="measured speed; overrides the nameplate")
    sp.add_argument("--point", help="narrow bearing frequencies to one measurement point")
    p.set_defaults(func=cmd_machine)

    p = sub.add_parser("diagnose", help="rank fault hypotheses from spectral peaks")
    p.add_argument("--peaks", required=True, help='"1.0:0.9,2.0:0.2" or "104.6hz:0.9"')
    p.add_argument("--rpm", type=float)
    p.add_argument("--machine", help="registered machine_id for full context")
    p.add_argument("--point", help="measurement point on that machine")
    p.add_argument("--bearing", help="bearing designation, when no machine is registered")
    p.add_argument("--top-n", type=int, default=5, dest="top_n")
    p.set_defaults(func=cmd_diagnose)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, NotImplementedError) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
