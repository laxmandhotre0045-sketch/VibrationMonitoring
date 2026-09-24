# Vibration Condition Report

**Cooling Water Pump 1**
Pump Casing (Horizontal)
| | |
|---|---|
| Machine | Cooling Water Pump 1 &nbsp;·&nbsp; `CWP-001` |
| Type | Pump |
| Location | Pune / Utilities / Cooling Water |
| Measurement point | Pump Casing, Horizontal |
| Sensor | IEPE Accelerometer &nbsp;·&nbsp; `f21a66ba-df6d-41b1-af1d-a0b637a39f2f` |
| Reporting window | 2026-08-27 10:18 to 2026-09-04 10:49 |
| Captures analysed | 9 |
| Report generated | 2026-09-07 07:58 UTC |

---

## 1. Summary

**Action required.** Of 720 threshold assessments across 8 channels, **270 are critical** and 81 are at warning. 144 were not assessed because this sensor has no healthy baseline for those features — *not assessed is not the same as healthy*.
> ### ⚠ These captures are not a history
>
> All 9 captures in this window carry identical feature values. They appear to be the same source file ingested repeatedly rather than separate measurements, so no trend can be assessed and the readings below describe one measurement, not a history.
>
> Files seen: `sample_vibration_data (1).csv`, `sample_vibration_data.csv` .
>
> Everything below describes **one measurement**. Trend figures are shown as
> unavailable rather than flat, because a flat line here would be an artefact of
> repeated ingestion, not an observation about the machine.

---

## 2. Feature readings

Worst reading per feature across all channels, with the channel and capture it came from.

| Feature | Worst reading | Ch. | Status | Latest | Trend |
|---|---:|---:|---|---:|---|
| RMS | 0.42409 scaled_eng <sup>(M)</sup> | 3 | critical | 0.42409 scaled_eng | not assessable |
| Peak | 1.47921 scaled_eng <sup>(M)</sup> | 7 | critical | 1.47921 scaled_eng | not assessable |
| Crest Factor | 5.93089 dimensionless <sup>(M)</sup> | 4 | critical | 5.93089 dimensionless | not assessable |
| Kurtosis | 9.58423 dimensionless <sup>(M)</sup> | 4 | critical | 9.58423 dimensionless | not assessable |
| 1X Amplitude | 0.550564 scaled_eng <sup>(M)</sup> | 3 | critical | 0.550564 scaled_eng | not assessable |
| 2X Amplitude | 0.219616 scaled_eng <sup>(M)</sup> | 5 | critical | 0.219616 scaled_eng | not assessable |
| 3X Amplitude | 0.180283 scaled_eng <sup>(M)</sup> | 5 | critical | 0.180283 scaled_eng | not assessable |
| Envelope RMS | 0.599748 scaled_eng <sup>(M)</sup> | 3 | no_baseline | 0.599748 scaled_eng | not assessable |
| Noise Floor | -41.4162 dB <sup>(M)</sup> | 7 | critical | -41.4162 dB | not assessable |
| FFT Band Energy (0-500 Hz) | 0.539377 scaled_eng_sq <sup>(M)</sup> | 3 | no_baseline | 0.539377 scaled_eng_sq | not assessable |

**Features carrying a critical reading:**
- **RMS** — 0.42409 scaled_eng on channel 3 (8 of 8 channels critical)
- **Peak** — 1.47921 scaled_eng on channel 7 (6 of 8 channels critical)
- **Crest Factor** — 5.93089 dimensionless on channel 4 (2 of 8 channels critical)
- **Kurtosis** — 9.58423 dimensionless on channel 4 (1 of 8 channels critical)
- **1X Amplitude** — 0.550564 scaled_eng on channel 3 (6 of 8 channels critical)
- **2X Amplitude** — 0.219616 scaled_eng on channel 5 (4 of 8 channels critical)
- **3X Amplitude** — 0.180283 scaled_eng on channel 5 (1 of 8 channels critical)
- **Noise Floor** — -41.4162 dB on channel 7 (2 of 8 channels critical)

---

## 3. ISO 10816-3 reference limits

> **These limits are shown for reference and cannot be applied to the readings above.**
>
> ISO 10816-3 zone boundaries are expressed in **mm/s RMS**, broadband 10–1000 Hz,
> measured on non-rotating parts. The readings in section 2 are stored in
> `dB`, `dimensionless`, `scaled_eng`, `scaled_eng_sq` —
> the platform's own scaled engineering units. Comparing the two would produce a
> zone the data does not support, so **no zone has been assigned**.
>
> To obtain an ISO zone, convert the broadband velocity to mm/s RMS and use the
> unit-tested tool: `python scripts/vib_cli.py iso --vrms <value> --power-kw <kW> --type <machine> --foundation <rigid|flexible>`
ISO 10816-3 classifies pumps as Group 3 (separate driver) or Group 4 (integrated driver) regardless of rated power. The driver arrangement was not supplied, so both are shown. They differ by roughly 60%.

**Group 3 — Pumps with separate driver, rigid support** <sup>(C)</sup>
Pumps with multivane impeller and separate driver (centrifugal, mixed flow or axial flow), rated power above 15 kW.

| Boundary | Velocity |
|---|---:|
| Zone A/B | 2.3 mm/s RMS |
| Zone B/C | 4.5 mm/s RMS |
| Zone C/D | 7.1 mm/s RMS |
**Group 3 — Pumps with separate driver, flexible support** <sup>(C)</sup>
Pumps with multivane impeller and separate driver (centrifugal, mixed flow or axial flow), rated power above 15 kW.

| Boundary | Velocity |
|---|---:|
| Zone A/B | 3.5 mm/s RMS |
| Zone B/C | 7.1 mm/s RMS |
| Zone C/D | 11.0 mm/s RMS |
**Group 4 — Pumps with integrated driver, rigid support** <sup>(C)</sup>
Pumps with multivane impeller and integrated driver (centrifugal, mixed flow or axial flow), rated power above 15 kW.

| Boundary | Velocity |
|---|---:|
| Zone A/B | 1.4 mm/s RMS |
| Zone B/C | 2.8 mm/s RMS |
| Zone C/D | 4.5 mm/s RMS |
**Group 4 — Pumps with integrated driver, flexible support** <sup>(C)</sup>
Pumps with multivane impeller and integrated driver (centrifugal, mixed flow or axial flow), rated power above 15 kW.

| Boundary | Velocity |
|---|---:|
| Zone A/B | 2.3 mm/s RMS |
| Zone B/C | 4.5 mm/s RMS |
| Zone C/D | 7.1 mm/s RMS |

A value exactly on a boundary is assigned to the lower zone (e.g. 2.80 mm/s -> Zone B, 2.81 mm/s -> Zone C).
---

## 4. What was and was not established

Every section of this report completed.
**Not attempted in this report:**

- No fault diagnosis. Spectral peak matching requires a shaft speed, and
  `rotation_speed_rpm` is not recorded on these captures.
- No ISO severity zone, for the unit reason given in section 3.
- No trend analysis, because the captures are identical.

---

## 5. Provenance

Every figure in this report, with where it came from. **(M)** measured on the
machine, **(C)** computed by `app/domain` (unit-tested against published
references), **(R)** read from an indexed document.

| Id | Quantity | Value | | Source |
|---|---|---:|---|---|
| `F1` | captures in the reporting window | 9 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F2` | measurement rows analysed | 720 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F3` | channels recorded | 8 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F4` | reporting window | 2026-08-27 10:18 to 2026-09-04 10:49 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F5` | readings assessed critical | 270 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F6` | readings assessed warning | 81 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F7` | readings assessed normal | 225 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F8` | readings assessed no_baseline | 144 | M | platform, sensor f21a66ba-df6d-41b1-af1d-a0b637a39f2f |
| `F9` | worst RMS | 0.42409 scaled_eng | M | channel 3, capture f88e67ab, 2026-08-27 10:18 |
| `F10` | latest RMS on channel 3 | 0.42409 scaled_eng | M | channel 3, 2026-09-04 10:49 |
| `F11` | worst Peak | 1.47921 scaled_eng | M | channel 7, capture f88e67ab, 2026-08-27 10:18 |
| `F12` | latest Peak on channel 7 | 1.47921 scaled_eng | M | channel 7, 2026-09-04 10:49 |
| `F13` | worst Crest Factor | 5.93089 dimensionless | M | channel 4, capture f88e67ab, 2026-08-27 10:18 |
| `F14` | latest Crest Factor on channel 4 | 5.93089 dimensionless | M | channel 4, 2026-09-04 10:49 |
| `F15` | worst Kurtosis | 9.58423 dimensionless | M | channel 4, capture f88e67ab, 2026-08-27 10:18 |
| `F16` | latest Kurtosis on channel 4 | 9.58423 dimensionless | M | channel 4, 2026-09-04 10:49 |
| `F17` | worst 1X Amplitude | 0.550564 scaled_eng | M | channel 3, capture f88e67ab, 2026-08-27 10:18 |
| `F18` | latest 1X Amplitude on channel 3 | 0.550564 scaled_eng | M | channel 3, 2026-09-04 10:49 |
| `F19` | worst 2X Amplitude | 0.219616 scaled_eng | M | channel 5, capture f88e67ab, 2026-08-27 10:18 |
| `F20` | latest 2X Amplitude on channel 5 | 0.219616 scaled_eng | M | channel 5, 2026-09-04 10:49 |
| `F21` | worst 3X Amplitude | 0.180283 scaled_eng | M | channel 5, capture f88e67ab, 2026-08-27 10:18 |
| `F22` | latest 3X Amplitude on channel 5 | 0.180283 scaled_eng | M | channel 5, 2026-09-04 10:49 |
| `F23` | worst Envelope RMS | 0.599748 scaled_eng | M | channel 3, capture f88e67ab, 2026-08-27 10:18 |
| `F24` | latest Envelope RMS on channel 3 | 0.599748 scaled_eng | M | channel 3, 2026-09-04 10:49 |
| `F25` | worst Noise Floor | -41.4162 dB | M | channel 7, capture f88e67ab, 2026-08-27 10:18 |
| `F26` | latest Noise Floor on channel 7 | -41.4162 dB | M | channel 7, 2026-09-04 10:49 |
| `F27` | worst FFT Band Energy (0-500 Hz) | 0.539377 scaled_eng_sq | M | channel 3, capture f88e67ab, 2026-08-27 10:18 |
| `F28` | latest FFT Band Energy (0-500 Hz) on channel 3 | 0.539377 scaled_eng_sq | M | channel 3, 2026-09-04 10:49 |
| `F29` | ISO 10816-3 Group 3 rigid A/B boundary | 2.3 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F30` | ISO 10816-3 Group 3 rigid B/C boundary | 4.5 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F31` | ISO 10816-3 Group 3 rigid C/D boundary | 7.1 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F32` | ISO 10816-3 Group 3 flexible A/B boundary | 3.5 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F33` | ISO 10816-3 Group 3 flexible B/C boundary | 7.1 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F34` | ISO 10816-3 Group 3 flexible C/D boundary | 11 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F35` | ISO 10816-3 Group 4 rigid A/B boundary | 1.4 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F36` | ISO 10816-3 Group 4 rigid B/C boundary | 2.8 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F37` | ISO 10816-3 Group 4 rigid C/D boundary | 4.5 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F38` | ISO 10816-3 Group 4 flexible A/B boundary | 2.3 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F39` | ISO 10816-3 Group 4 flexible B/C boundary | 4.5 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |
| `F40` | ISO 10816-3 Group 4 flexible C/D boundary | 7.1 mm/s RMS | C | app/domain/iso10816 (unit-tested reference tables) |

### Caveats carried by this data

- Values are the platform's stored feature values in scaled engineering units (unit='scaled_eng'), not converted to g, mm/s or micrometres. Comparing raw magnitudes across different machines is not meaningful; use crest_factor, status, or a ratio against the sensor's own baseline instead.- status='no_baseline' means the feature was not assessed because no healthy reference exists for this sensor. It does not mean the machine is healthy.- Rows are ordered by observed_at, which is the device's capture clock where one was supplied and server receipt otherwise. Only observed_at orders a trend correctly.- Shaft speed behind amplitude_1x/2x/3x is estimated from the spectrum unless the capture carries rotation_speed_rpm. Treat harmonic amplitudes as provisional when rotation_speed_rpm is empty.
---

<sub>Generated by report_agent · 2026-09-07 07:58 UTC · 40 facts ·
no value in this report was written by a language model.</sub>
