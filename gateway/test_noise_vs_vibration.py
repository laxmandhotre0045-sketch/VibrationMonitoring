"""MOM item 11 — evaluate the system on noise data and on vibration data.

The MOM asks to "evaluate the system using vibration data only, and separately
evaluate it using noise data only, in order to understand how the system
performs for each type of data".

Two readings were possible and both were checked against the system:

  ACOUSTIC noise -- not possible here, and not a matter of effort. The platform
  accepts exactly four signal types, VIBRATION / TEMPERATURE / PRESSURE /
  TACHO; there is no acoustic type, no dB(A) anywhere in the services, and all
  eight channels are IEPE accelerometers. A microphone would need hardware, a
  new signal type, and a weighting curve before any of it could be tested.

  NOISE FLOOR -- the non-machine component: sensor bias drift, amplifier and
  ADC noise, and whatever the plant couples in electrically. This is what the
  idle captures contain, and it is what this module evaluates.

The interesting question is NOT "what does noise look like". It is **what does
the system claim when there is nothing to find**. A spectrum analyser handed
pure noise will always return a largest bin, and a shaft estimator will always
return some frequency. Whether those are presented as findings, or correctly
withheld, decides whether an engineer is sent chasing a fault that does not
exist. That is what the checks below actually test.

Run:
    python test_noise_vs_vibration.py                    # noise only
    python test_noise_vs_vibration.py --vibration archive_under_load
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from uploader_settings import SENSOR_ID, PLATFORM_API_URL
from test_10_samples import (
    Report, api, login, read_csv_channels, independent_stats,
)

HERE = Path(__file__).resolve().parent

#: Mains frequency in India. A line-frequency peak in an accelerometer channel
#: is electrical pickup, not motion, and must not be read as a machine order.
MAINS_HZ = 50.0

#: A Gaussian has excess kurtosis 0. Electronic noise that is close to Gaussian
#: reads near 0; impulsive interference pushes it up. The band is wide because
#: 13,888 samples give a sampling spread of roughly +/-0.04 on its own.
GAUSSIAN_KURTOSIS_BAND = 1.5


def spectrum_for(upload_id: str, channel: int, token: str) -> dict | None:
    st, an = api("/api/v1/measurements/uploads/" + str(upload_id)
                 + "/raw/analysis?channel=" + str(channel), token=token)
    if st != 200 or not isinstance(an, dict):
        return None
    return an


def describe_noise(cols: list[list[float]], rate: float) -> list[dict]:
    """Per-channel description of a capture that contains no machine signal."""
    out = []
    for ci, samples in enumerate(cols):
        x = np.asarray(samples, dtype=np.float64)
        ac = x - x.mean()
        n = ac.size
        win = np.hanning(n)
        # Amplitude-correct the window so peak heights stay comparable with the
        # platform's own spectrum, which applies the same correction.
        sp = np.abs(np.fft.rfft(ac * win)) / (win.sum() / 2.0)
        fr = np.fft.rfftfreq(n, d=1.0 / rate)

        band = (fr > 2.0)                      # ignore DC and drift
        amp = sp[band]
        frq = fr[band]
        imax = int(np.argmax(amp))

        # How far the largest line stands above the typical line. In pure noise
        # this ratio is small -- there is no peak, only the tallest blade of
        # grass. It is the honest way to ask "is there a tone here at all".
        med = float(np.median(amp)) or 1e-30
        prominence = float(amp[imax]) / med

        mains_idx = int(np.argmin(np.abs(frq - MAINS_HZ)))
        mains_ratio = float(amp[mains_idx]) / med

        s = independent_stats(samples)
        out.append({
            "ch": ci,
            "ac_rms": s["ac_rms"],
            "dc": s["mean"],
            "kurtosis": s["kurtosis_excess"],
            "crest": s["crest_factor"],
            "peak_hz": float(frq[imax]),
            "prominence": prominence,
            "mains_ratio": mains_ratio,
        })
    return out


def evaluate(folder: Path, label: str, rep: Report, token: str,
             items: list[dict], expect_signal: bool) -> list[dict]:
    files = sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        print("  (no captures in " + str(folder) + ")")
        return []
    print("\n" + "=" * 74)
    print(label.upper() + " DATASET  --  " + str(len(files)) + " captures from " + folder.name)
    print("=" * 74)

    rows: list[dict] = []
    rate = 50000.0
    for n, f in enumerate(files, 1):
        ts, cols = read_csv_channels(f)
        if len(ts) > 1:
            step_ms = statistics.median(b - a for a, b in zip(ts, ts[1:]))
            if step_ms > 0:
                rate = 1000.0 / step_ms
        rows.extend({**d, "file": f.name, "n": n} for d in describe_noise(cols, rate))

    # ---------------------------------------------------------------- stats --
    print("\n  " + "ch".rjust(3) + "  " + "AC rms (g)".rjust(11)
          + "  " + "kurtosis".rjust(9) + "  " + "crest".rjust(6)
          + "  " + "peak Hz".rjust(9) + "  " + "prominence".rjust(11)
          + "  " + "mains x".rjust(8))
    per_ch = {}
    findings: list[str] = []
    for ci in range(8):
        r = [x for x in rows if x["ch"] == ci]
        if not r:
            continue
        m = {k: statistics.fmean([x[k] for x in r])
             for k in ("ac_rms", "kurtosis", "crest", "prominence", "mains_ratio")}
        peaks = [x["peak_hz"] for x in r]
        per_ch[ci] = {**m, "peak_spread": max(peaks) - min(peaks),
                      "peaks": peaks, "n": len(r)}
        print("  " + str(ci).rjust(3) + "  " + ("%.5f" % m["ac_rms"]).rjust(11)
              + "  " + ("%+.3f" % m["kurtosis"]).rjust(9)
              + "  " + ("%.2f" % m["crest"]).rjust(6)
              + "  " + ("%.1f" % statistics.fmean(peaks)).rjust(9)
              + "  " + ("%.2f" % m["prominence"]).rjust(11)
              + "  " + ("%.2f" % m["mains_ratio"]).rjust(8))

    # ------------------------------------------------------------- checks --
    print()
    for ci, m in per_ch.items():
        if not expect_signal:
            # The first version of this asserted the idle set was featureless
            # noise. It is not, and the assertion was an assumption of mine
            # rather than a requirement of the system -- so the tonal content
            # is now REPORTED, and only genuine defects fail.
            if m["prominence"] >= 12.0:
                findings.append("ch%d: tone at ~%.0f Hz, %.0fx median%s"
                                % (ci, statistics.fmean(m["peaks"]),
                                   m["prominence"],
                                   " (drifts %.0f Hz)" % m["peak_spread"]
                                   if m["peak_spread"] > 5 else " (stable)"))

            # Mains pickup IS a defect. A 50 Hz line in an accelerometer
            # channel is electrical ingress: it is not motion, it will be
            # graded as vibration by every downstream feature, and on a 50 Hz
            # supply it sits exactly where a 3000 rpm shaft order would.
            rep.check(label + ": integrity",
                      "ch" + str(ci) + ": free of %g Hz mains pickup" % MAINS_HZ,
                      m["mains_ratio"] < 12.0,
                      "%.0fx median at %g Hz" % (m["mains_ratio"], MAINS_HZ))

            # Impulsive interference would show as high kurtosis; this is a
            # genuine data-quality check independent of any tone.
            rep.check(label + ": integrity",
                      "ch" + str(ci) + ": not impulsive (|excess kurtosis| < %.1f)"
                      % GAUSSIAN_KURTOSIS_BAND,
                      abs(m["kurtosis"]) < GAUSSIAN_KURTOSIS_BAND,
                      "excess kurtosis %+.3f" % m["kurtosis"])
        else:
            rep.check(label + ": character",
                      "ch" + str(ci) + ": a real tone is present (prominence > 12x)",
                      m["prominence"] > 12.0,
                      "prominence %.1fx" % m["prominence"])
            rep.check(label + ": character",
                      "ch" + str(ci) + ": dominant frequency is repeatable",
                      m["peak_spread"] < 20.0,
                      "spread %.1f Hz across %d captures"
                      % (m["peak_spread"], m["n"]))

    if findings:
        print()
        print("  TONAL CONTENT FOUND (reported, not failed):")
        for f_ in findings:
            print("    * " + f_)
    return rows


def evaluate_system_behaviour(folder: Path, rep: Report, token: str,
                              items: list[dict]) -> None:
    """The real question: what does the SYSTEM say when handed pure noise?"""
    files = sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime)[:5]
    print("\n" + "=" * 74)
    print("SYSTEM BEHAVIOUR ON NOISE  --  what does it report when nothing is there?")
    print("=" * 74 + "\n")

    reported: list[float] = []
    for f in files:
        upload_id = None
        for it in items:
            if isinstance(it, dict) and f.name == it.get("original_filename"):
                upload_id = it.get("upload_id")
                break
        if not upload_id:
            continue
        an = spectrum_for(upload_id, 0, token)
        if not an:
            continue
        sp = an.get("spectrum") or {}
        dom = float(sp.get("dominant_frequency_hz", 0.0))
        amp = float(sp.get("dominant_amplitude", 0.0))
        reported.append(dom)
        print("  " + f.name[9:15] + "  system reports dominant "
              + ("%.2f" % dom).rjust(9) + " Hz   amplitude "
              + ("%.6f" % amp))

    if len(reported) >= 3:
        spread = max(reported) - min(reported)
        centre = statistics.fmean(reported) or 1.0
        rel = spread / centre
        # RELATIVE, not absolute. An earlier version called a 47 Hz spread
        # "unstable" -- but at 5.5 kHz that is 0.9%, which is a stable tone,
        # not a wandering noise peak. The absolute threshold would have called
        # every high-frequency line unstable and hidden exactly this finding.
        stable = rel < 0.05
        print()
        print("  dominant frequency across captures: %.0f Hz +/- %.0f (%.1f%%)"
              % (centre, spread / 2, rel * 100))
        if stable:
            print("  -> STABLE. This is a real persistent tone, not a noise peak.")
            print("     The machine is idle, so its source is not shaft rotation.")
        else:
            print("  -> wanders; consistent with there being no tone to lock to.")

        # The check that matters: whatever the system reports, can a reader
        # tell how much to trust it? Search the response for any field that
        # expresses confidence, signal-to-noise or quality. This replaces an
        # earlier assertion hardcoded to True, which could never have failed.
        an = None
        for it in items:
            if isinstance(it, dict) and it.get("upload_id"):
                an = spectrum_for(it["upload_id"], 0, token)
                break
        keys = set()
        if an:
            keys |= set(an.keys())
            keys |= set((an.get("spectrum") or {}).keys())
            keys |= set((an.get("statistics") or {}).keys())
        quality = {k for k in keys if any(w in k.lower() for w in
                   ("confidence", "snr", "signal_to_noise", "quality",
                    "prominence", "significance"))}
        rep.check("noise: system behaviour",
                  "dominant frequency carries a confidence or SNR field",
                  bool(quality),
                  "found " + str(sorted(quality)) if quality else
                  "no confidence/SNR/quality field in the analysis response; "
                  "an idle machine and a faulty one report a dominant "
                  "frequency the same way")


def main() -> int:
    ap = argparse.ArgumentParser(description="MOM item 11 evaluation")
    ap.add_argument("--noise", default="archive",
                    help="folder of idle (noise-only) captures")
    ap.add_argument("--vibration", default=None,
                    help="folder of running-machine captures, when available")
    args = ap.parse_args()

    rep = Report()
    token = login()
    st, cfg = api("/api/v1/acquisition/config?device_id="
                  + urllib.parse.quote(SENSOR_ID))
    sensor_uuid = cfg.get("platformSensorId") if st == 200 else None
    st, snaps = api("/api/v1/measurements/raw/snapshots?sensor_id="
                    + str(sensor_uuid) + "&limit=200", token=token)
    items = (snaps.get("items") or []) if st == 200 and isinstance(snaps, dict) else []

    print("MOM ITEM 11 -- SEPARATE NOISE AND VIBRATION EVALUATION")
    print("platform : " + PLATFORM_API_URL)
    print("device   : " + SENSOR_ID)
    print("\nAcoustic noise is not evaluable on this system: the platform's")
    print("signal types are VIBRATION / TEMPERATURE / PRESSURE / TACHO, there is")
    print("no acoustic type, and all eight channels are IEPE accelerometers.")
    print("'Noise' below therefore means the measured noise floor.")

    noise_dir = HERE / args.noise
    evaluate(noise_dir, "noise", rep, token, items, expect_signal=False)
    evaluate_system_behaviour(noise_dir, rep, token, items)

    if args.vibration:
        vib_dir = HERE / args.vibration
        if any(vib_dir.glob("*.csv")):
            evaluate(vib_dir, "vibration", rep, token, items, expect_signal=True)
        else:
            print("\n" + "=" * 74)
            print("VIBRATION DATASET -- not yet available")
            print("=" * 74)
            print("  " + str(vib_dir) + " is empty.")
            print("  collect_under_load.py fills it when the machine starts.")
            rep.check("vibration: availability",
                      "running-machine captures present", False,
                      "none in " + vib_dir.name + "; start the pump")

    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
