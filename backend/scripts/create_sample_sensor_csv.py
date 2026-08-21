"""
Generate a dummy 8-channel sensor measurement CSV for testing upload/plot/feature APIs.
Run: python scripts/create_sample_sensor_csv.py

Output format matches app/services/pdf_parser.py:
    timestamp_,ch0,ch1,...,ch7   (relative seconds + scaled engineering units, g)

Simulated asset: motor + pump train at 1500 RPM (25 Hz shaft), fs = 25.6 kHz, 8192 samples (0.32 s).
Each channel carries a different fault signature so every extracted feature has something to show:
    ch0 Motor DE Horizontal   healthy
    ch1 Motor DE Vertical     healthy
    ch2 Motor NDE Horizontal  unbalance      (dominant 1X)
    ch3 Motor NDE Axial       misalignment   (dominant 2X)
    ch4 Pump DE Horizontal    outer-race bearing defect (BPFO 3.57X, high crest/kurtosis)
    ch5 Pump DE Vertical      mechanical looseness (0.5X + harmonic family)
    ch6 Pump NDE Horizontal   early inner-race defect (BPFI 5.43X, 1X modulated)
    ch7 Pump NDE Axial        cavitation     (vane pass 5X + broadband noise)
"""
import math
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "sample_vibration_data.csv"

FS_HZ = 25600.0
N = 8192
SHAFT_HZ = 25.0
CHANNELS = 8
SEED = 20250820

_state = SEED


def rnd() -> float:
    """Deterministic 32-bit LCG so regenerated files are reproducible."""
    global _state
    _state = (1664525 * _state + 1013904223) % 4294967296
    return _state / 4294967296


def gauss() -> float:
    u1 = max(rnd(), 1e-12)
    u2 = rnd()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)


def sine(amp: float, freq: float, phase: float, t: float) -> float:
    return amp * math.sin(2 * math.pi * freq * t + phase)


def add_impulses(buf, defect_hz, amp, tau, resonance_hz, mod_depth):
    """Bearing defect: decaying resonance ring at each rolling-element impact."""
    period = 1.0 / defect_hz
    ring = int(6.0 * tau * FS_HZ)
    total = int((N / FS_HZ) / period) + 1
    for k in range(total):
        t0 = k * period * (1.0 + 0.02 * (rnd() - 0.5))
        mod = 1.0 + mod_depth * math.sin(2 * math.pi * SHAFT_HZ * t0)
        a = amp * mod * (1.0 + 0.10 * (rnd() - 0.5))
        start = int(t0 * FS_HZ)
        for i in range(start, min(start + ring, N)):
            dt = i / FS_HZ - t0
            if dt < 0:
                continue
            buf[i] += a * math.exp(-dt / tau) * math.sin(2 * math.pi * resonance_hz * dt)


def build_channels() -> list[list[float]]:
    ch = [[0.0] * N for _ in range(CHANNELS)]
    tt = [i / FS_HZ for i in range(N)]

    for i, t in enumerate(tt):  # ch0 — healthy
        ch[0][i] = (0.0015 + sine(0.045, SHAFT_HZ, 0.0, t) + sine(0.012, 2 * SHAFT_HZ, 0.7, t)
                    + sine(0.005, 3 * SHAFT_HZ, 1.9, t) + sine(0.008, 100.0, 0.3, t) + 0.010 * gauss())

    for i, t in enumerate(tt):  # ch1 — healthy
        ch[1][i] = (0.0010 + sine(0.030, SHAFT_HZ, 1.2, t) + sine(0.008, 2 * SHAFT_HZ, 2.4, t)
                    + sine(0.006, 100.0, 1.1, t) + 0.009 * gauss())

    for i, t in enumerate(tt):  # ch2 — unbalance
        ch[2][i] = (0.0020 + sine(0.420, SHAFT_HZ, 0.4, t) + sine(0.050, 2 * SHAFT_HZ, 1.5, t)
                    + sine(0.020, 3 * SHAFT_HZ, 2.8, t) + 0.012 * gauss())

    for i, t in enumerate(tt):  # ch3 — misalignment
        ch[3][i] = (0.0025 + sine(0.180, SHAFT_HZ, 2.1, t) + sine(0.550, 2 * SHAFT_HZ, 0.9, t)
                    + sine(0.150, 3 * SHAFT_HZ, 1.7, t) + sine(0.040, 4 * SHAFT_HZ, 0.2, t) + 0.015 * gauss())

    for i, t in enumerate(tt):  # ch4 — outer-race bearing defect
        ch[4][i] = (0.0010 + sine(0.060, SHAFT_HZ, 1.0, t) + sine(0.025, 2 * SHAFT_HZ, 2.2, t)
                    + 0.020 * gauss())
    add_impulses(ch[4], 3.57 * SHAFT_HZ, 1.200, 0.0012, 4200.0, 0.0)

    for i, t in enumerate(tt):  # ch5 — looseness
        ch[5][i] = (0.0018 + sine(0.120, 0.5 * SHAFT_HZ, 0.6, t) + sine(0.300, SHAFT_HZ, 1.4, t)
                    + sine(0.100, 1.5 * SHAFT_HZ, 2.6, t) + sine(0.220, 2 * SHAFT_HZ, 0.8, t)
                    + sine(0.080, 2.5 * SHAFT_HZ, 1.9, t) + sine(0.180, 3 * SHAFT_HZ, 0.1, t)
                    + sine(0.100, 4 * SHAFT_HZ, 2.0, t) + sine(0.070, 5 * SHAFT_HZ, 1.3, t) + 0.030 * gauss())

    for i, t in enumerate(tt):  # ch6 — early inner-race defect
        ch[6][i] = (0.0008 + sine(0.050, SHAFT_HZ, 2.5, t) + sine(0.020, 2 * SHAFT_HZ, 0.5, t)
                    + 0.018 * gauss())
    add_impulses(ch[6], 5.43 * SHAFT_HZ, 0.150, 0.0009, 3100.0, 0.6)

    for i, t in enumerate(tt):  # ch7 — cavitation
        ch[7][i] = (0.0012 + sine(0.040, SHAFT_HZ, 1.8, t) + sine(0.200, 5 * SHAFT_HZ, 0.3, t)
                    + sine(0.090, 10 * SHAFT_HZ, 2.7, t) + 0.350 * gauss())

    return ch


def main():
    ch = build_channels()
    lines = ["timestamp_," + ",".join(f"ch{c}" for c in range(CHANNELS))]
    for i in range(N):
        row = [f"{i / FS_HZ:.6f}"] + [f"{ch[c][i]:.6f}" for c in range(CHANNELS)]
        lines.append(",".join(row))

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created: {OUTPUT} ({N} rows x {CHANNELS} channels @ {FS_HZ:.0f} Hz)")


if __name__ == "__main__":
    main()
