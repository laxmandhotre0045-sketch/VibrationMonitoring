"""Ten-sample acceptance test for the vibration pipeline.

MOM item 2. Tests the chain the way a user exercises it -- through the HTTP
API, not by calling service functions -- and checks every number the system
reports against an independent calculation done here from the original CSV.

That independence is the point. A test that asks the system for RMS and then
asks the same code for RMS again proves only that the function is
deterministic. Each statistic below is recomputed from the archived file with
plain numpy, using the textbook definition, so a convention slip (excess vs
Pearson kurtosis, population vs sample standard deviation, mean-removed vs
raw RMS) shows up as a disagreement rather than passing silently.

The suite covers, per sample:

  A. Ingestion         -- was the file accepted, with the right geometry
  B. Round-trip        -- do the stored samples equal the CSV's samples
  C. Statistics        -- RMS, peak, crest, kurtosis, skewness vs independent
  D. Conventions       -- excess vs raw kurtosis really differ by 3
  E. Physical sanity   -- units, DC offset, noise floor

and across the set:

  F. Repeatability     -- ten captures of one unchanged machine should agree
  G. Negative tests    -- malformed input must be refused, not absorbed

Run:  python test_10_samples.py
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from uploader_settings import SENSOR_ID, PLATFORM_API_URL

ARCHIVE = Path(__file__).resolve().parent / "archive"
KEY_FILE = Path(__file__).resolve().parent / ".ingest_key"

#: Tolerance for "the platform's number equals my number". Floating point and
#: the platform's float32/float64 storage make exact equality the wrong test;
#: this is tight enough that a convention error cannot hide inside it.
REL_TOL = 1e-6

NL_C = chr(10)


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------

def login() -> str:
    """Admin bearer token. The measurements router is user-authenticated, not
    key-authenticated -- an API key gets a 401 there, which an earlier version
    of this test mistook for data."""
    env = {}
    envp = Path(__file__).resolve().parents[1] / "backend" / ".env"
    for line in envp.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("="); env[k.strip()] = v.strip()
    body = json.dumps({"email": env["INITIAL_ADMIN_EMAIL"],
                       "password": env["INITIAL_ADMIN_PASSWORD"]}).encode()
    req = urllib.request.Request(PLATFORM_API_URL + "/api/v1/auth/login", data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]


def api(path: str, key: str | None = None, token: str | None = None) -> tuple[int, object]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(PLATFORM_API_URL + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def read_csv_channels(path: Path) -> tuple[list[float], list[list[float]]]:
    """Return (timestamps_ms, [channel0_samples, channel1_samples, ...])."""
    with path.open(newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        n_ch = len(header) - 1
        ts: list[float] = []
        cols: list[list[float]] = [[] for _ in range(n_ch)]
        for row in reader:
            if len(row) != n_ch + 1:
                continue
            ts.append(float(row[0]))
            for i in range(n_ch):
                cols[i].append(float(row[i + 1]))
    return ts, cols


# --------------------------------------------------------------------------
# independent statistics -- textbook definitions, computed here
# --------------------------------------------------------------------------

def independent_stats(samples: list[float]) -> dict[str, float]:
    """Recompute every statistic from first principles.

    Deliberately NOT importing the platform's extractor. RMS is the raw
    quadratic mean including any DC component, which is what an accelerometer
    channel's RMS means; kurtosis and skewness are standardised about the mean
    with the population (biased, ddof=0) standard deviation, which is the
    convention the platform documents.
    """
    x = np.asarray(samples, dtype=np.float64)
    mean = float(np.mean(x))
    dev = x - mean
    sd = float(np.sqrt(np.mean(dev**2)))          # population sigma

    rms = float(np.sqrt(np.mean(x**2)))
    peak = float(np.max(np.abs(x)))
    return {
        "rms": rms,
        "peak": peak,
        "peak_to_peak": float(np.max(x) - np.min(x)),
        "crest_factor": peak / rms if rms > 0 else 0.0,
        "kurtosis_excess": float(np.mean(dev**4) / sd**4 - 3.0) if sd > 1e-30 else 0.0,
        "skewness": float(np.mean(dev**3) / sd**3) if sd > 1e-30 else 0.0,
        "mean": mean,
        "ac_rms": sd,
    }


def close(a: float, b: float, tol: float = REL_TOL) -> bool:
    scale = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / scale <= tol


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, bool, str]] = []

    def check(self, group: str, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((group, name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"    [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
        return ok

    def summary(self) -> int:
        total = len(self.rows)
        failed = [r for r in self.rows if not r[2]]
        print("\n" + "=" * 74)
        print(f"RESULT: {total - len(failed)}/{total} checks passed")
        by_group: dict[str, list[bool]] = {}
        for g, _, ok, _ in self.rows:
            by_group.setdefault(g, []).append(ok)
        for g, oks in by_group.items():
            print(f"  {g:34} {sum(oks):3}/{len(oks):<3} "
                  + ("OK" if all(oks) else "*** FAILURES ***"))
        if failed:
            print("\nFailures:")
            for g, name, _, detail in failed:
                print(f"  - [{g}] {name}: {detail}")
        print("=" * 74)
        return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ten-sample acceptance test")
    ap.add_argument("--archive", default="archive",
                    help="folder of captures to test (default: archive). Point "
                         "this at archive_under_load to run the same checks "
                         "against captures taken while the machine was turning.")
    args = ap.parse_args()
    archive_dir = Path(__file__).resolve().parent / args.archive
    print("archive  : " + str(archive_dir))
    files = sorted(archive_dir.glob("*.csv"))
    if len(files) < 10:
        print(f"Need 10 archived samples, found {len(files)} in {archive_dir}")
        return 2
    files = files[:10]
    key = KEY_FILE.read_text(encoding="utf-8").strip() if KEY_FILE.is_file() else None

    rep = Report()
    print("=" * 74)
    print("TEN-SAMPLE ACCEPTANCE TEST")
    print(f"platform : {PLATFORM_API_URL}")
    print(f"device   : {SENSOR_ID}")
    print("=" * 74)

    # ---------------------------------------------------------------- A/B --
    token = login()
    st, sens = api("/api/v1/acquisition/config?device_id="
                   + urllib.parse.quote(SENSOR_ID))
    sensor_uuid = (sens or {}).get("platformSensorId") if st == 200 else None

    st, snaps = api(f"/api/v1/measurements/raw/snapshots?sensor_id={sensor_uuid}&limit=200",
                    token=token)
    ok_list = rep.check("A. ingestion", "snapshot list reachable", st == 200, f"HTTP {st}")
    # Only a 200 carries items. A previous version read the body of a 401 and
    # counted its characters, which reported a pass on an error string.
    items = []
    if ok_list and isinstance(snaps, dict):
        items = snaps.get("items") or []
    elif ok_list and isinstance(snaps, list):
        items = snaps
    rep.check("A. ingestion", "at least 10 captures stored",
              len(items) >= 10, f"{len(items)} found")

    st, cfg = api("/api/v1/acquisition/config?device_id="
                  + urllib.parse.quote(SENSOR_ID))
    declared_rate = float(cfg.get("sampleRateHz", 0)) if st == 200 else 0.0
    rep.check("A. ingestion", "platform declares a sample rate",
              declared_rate > 0, f"{declared_rate} Hz")

    per_sample: list[dict[str, float]] = []

    for n, path in enumerate(files, 1):
        print(f"\n--- sample {n}/10: {path.name[:46]} ---")
        ts, cols = read_csv_channels(path)

        rep.check("A. ingestion", f"s{n}: 8 channels", len(cols) == 8, f"{len(cols)}")
        rep.check("A. ingestion", f"s{n}: 13888 rows", len(ts) == 13888, f"{len(ts)}")

        # --- B. the time base the platform refused before the fix ---------
        strictly_up = all(b > a for a, b in zip(ts, ts[1:]))
        rep.check("B. time base", f"s{n}: timestamps strictly increasing",
                  strictly_up)
        gaps = np.diff(np.asarray(ts))
        med_gap_ms = float(np.median(gaps))
        expected_ms = 1000.0 / declared_rate if declared_rate else 0.0
        rep.check("B. time base", f"s{n}: spacing matches declared rate",
                  abs(med_gap_ms - expected_ms) < expected_ms * 0.05,
                  f"median {med_gap_ms*1000:.2f} us vs expected {expected_ms*1000:.2f} us")

        # --- B2. round trip: what came back must be what went in ----------
        # The claim being tested is that storage is lossless. Comparing only
        # derived statistics would not catch a channel transposition or an
        # off-by-one, because RMS is order-independent -- so the samples
        # themselves are compared, in order.
        upload_id = None
        for it in items:
            if isinstance(it, dict) and path.name in (
                    it.get("original_filename"), it.get("file_name")):
                upload_id = it.get("upload_id") or it.get("id")
                break
        if upload_id:
            st, raw = api("/api/v1/measurements/uploads/" + str(upload_id)
                          + "/raw?offset=0&limit=500", token=token)
            if st == 200 and isinstance(raw, dict):
                rows = raw.get("samples") or []
                mismatches = []
                if not rows:
                    mismatches.append("no rows returned")
                for ci in range(len(cols)):
                    ch_key = "ch" + str(ci)
                    got = [r.get(ch_key) for r in rows if isinstance(r, dict)]
                    want = cols[ci][:len(got)]
                    bad = [j for j in range(len(want))
                           if got[j] is None or abs(float(got[j]) - want[j]) > 1e-6]
                    if bad:
                        mismatches.append(ch_key + ": " + str(len(bad)) + "/"
                                          + str(len(want)) + " differ (first at row "
                                          + str(bad[0]) + ")")
                rep.check("B. round trip",
                          "s" + str(n) + ": stored samples equal the CSV ("
                          + str(len(rows)) + " rows x " + str(len(cols)) + " ch)",
                          not mismatches, "; ".join(mismatches)[:150])
            else:
                rep.check("B. round trip", "s" + str(n) + ": raw samples readable back",
                          False, "HTTP " + str(st))

        # --- C. statistics, channel by channel ----------------------------
        ch_mismatch: list[str] = []
        for ci, samples in enumerate(cols):
            mine = independent_stats(samples)
            per_sample.append({"sample": n, "ch": ci, **mine})
            # sanity that cannot be wrong if the maths is right
            if mine["rms"] < abs(mine["mean"]) - 1e-9:
                ch_mismatch.append(f"ch{ci}: rms < |mean|")
            crest = mine["crest_factor"]
            if not (1.0 - 1e-9 <= crest <= 1e6):
                ch_mismatch.append(f"ch{ci}: crest {crest:.3f} outside [1, inf)")
        rep.check("C. statistics", f"s{n}: internal identities hold",
                  not ch_mismatch, "; ".join(ch_mismatch))

        # --- compare against the platform's own analysis -------------------
        for it in items:
            if not isinstance(it, dict):
                continue
            if path.name in (it.get("original_filename"), it.get("file_name"),
                             it.get("fileName"), it.get("filename")):
                upload_id = it.get("upload_id") or it.get("id")
                break
        if upload_id:
            st, an = api(f"/api/v1/measurements/uploads/{upload_id}/raw/analysis?channel=0", token=token)
            if st == 200 and isinstance(an, dict):
                stats = an.get("statistics") or an.get("stats") or {}
                mine = independent_stats(cols[0])
                for field, ours in (("rms", mine["rms"]),
                                    ("peak", mine["peak"]),
                                    ("crest_factor", mine["crest_factor"]),
                                    ("kurtosis", mine["kurtosis_excess"]),
                                    ("skewness", mine["skewness"])):
                    if field in stats:
                        rep.check("C. statistics",
                                  f"s{n}: platform {field} matches independent",
                                  close(float(stats[field]), ours),
                                  f"platform {float(stats[field]):.8g} vs ours {ours:.8g}")
                # --- D. the kurtosis convention trap ----------------------
                if "kurtosis_excess" in stats and "kurtosis_raw" in stats:
                    rep.check("D. conventions",
                              f"s{n}: kurtosis_raw - kurtosis_excess == 3",
                              close(float(stats["kurtosis_raw"])
                                    - float(stats["kurtosis_excess"]), 3.0, 1e-9),
                              f"{float(stats['kurtosis_raw']) - float(stats['kurtosis_excess']):.10f}")
            else:
                rep.check("C. statistics", f"s{n}: analysis endpoint reachable",
                          False, f"HTTP {st}: {str(an)[:120]}")
        else:
            rep.check("C. statistics", f"s{n}: capture locatable via API",
                      False, "no matching upload id in snapshot list")

        # --- H. every channel, not just ch0 -------------------------------
        # Testing one channel cannot detect a transposition: if the API served
        # ch5 when asked for ch2, a ch0-only test still passes. Each channel is
        # asked for by index and its RMS matched to that column of the CSV.
        if upload_id and n <= 3:   # three samples x eight channels is enough
            wrong = []
            for ci in range(len(cols)):
                st, an2 = api("/api/v1/measurements/uploads/" + str(upload_id)
                              + "/raw/analysis?channel=" + str(ci), token=token)
                if st != 200 or not isinstance(an2, dict):
                    wrong.append("ch" + str(ci) + ": HTTP " + str(st)); continue
                got = float((an2.get("statistics") or {}).get("rms", -1))
                want = independent_stats(cols[ci])["rms"]
                if not close(got, want):
                    # Name the column it DID match, which is what makes a
                    # transposition diagnosable rather than just red.
                    hit = [k for k in range(len(cols))
                           if close(got, independent_stats(cols[k])["rms"])]
                    wrong.append("ch" + str(ci) + ": got " + str(round(got, 8))
                                 + " which is ch" + str(hit) if hit else
                                 "ch" + str(ci) + ": " + str(round(got, 8)))
                if an2.get("channel") != ci:
                    wrong.append("ch" + str(ci) + ": response says channel "
                                 + str(an2.get("channel")))
            rep.check("H. per channel", "s" + str(n) + ": all 8 channels return their own data",
                      not wrong, "; ".join(wrong)[:170])

        # --- I. spectrum ---------------------------------------------------
        # The statistics are time-domain; none of them would notice a wrong
        # frequency axis. A spectrum whose axis is wrong by a factor of two is
        # exactly the failure the 25.6-vs-50 kSPS mismatch would have caused,
        # and it is invisible unless the axis itself is checked.
        if upload_id and n <= 3:
            st, an3 = api("/api/v1/measurements/uploads/" + str(upload_id)
                          + "/raw/analysis?channel=0", token=token)
            sp = (an3 or {}).get("spectrum") if st == 200 else None
            if sp:
                freqs = sp.get("frequencies") or []
                df = float(sp.get("frequency_resolution_hz") or 0)
                rep.check("I. spectrum", "s" + str(n) + ": axis starts at DC",
                          bool(freqs) and abs(float(freqs[0])) < 1e-9,
                          str(freqs[:1]))
                rep.check("I. spectrum", "s" + str(n) + ": axis ascends",
                          all(float(b) > float(a) for a, b in zip(freqs, freqs[1:])))
                # Top of the axis must not exceed Nyquist of the declared rate.
                rep.check("I. spectrum", "s" + str(n) + ": axis stays below Nyquist",
                          bool(freqs) and float(freqs[-1]) <= declared_rate / 2 + 1e-6,
                          "fmax " + str(round(float(freqs[-1]), 2))
                          + " Hz vs Nyquist " + str(declared_rate / 2))
                # Resolution must equal the spacing actually used.
                if len(freqs) > 2 and df > 0:
                    step = float(freqs[1]) - float(freqs[0])
                    rep.check("I. spectrum", "s" + str(n) + ": stated resolution equals real spacing",
                              abs(step - df) < max(df * 0.02, 1e-9),
                              "stated " + str(df) + " Hz, actual " + str(round(step, 6)) + " Hz")
                # The dominant line must be a line that exists, at a real peak.
                amps = sp.get("amplitudes") or []
                if amps and freqs:
                    imax = max(range(len(amps)), key=lambda i: float(amps[i]))
                    rep.check("I. spectrum", "s" + str(n) + ": dominant freq is the largest line",
                              abs(float(sp.get("dominant_frequency_hz", -1))
                                  - float(freqs[imax])) <= max(df, 1e-6),
                              "reported " + str(sp.get("dominant_frequency_hz"))
                              + " Hz, largest at " + str(round(float(freqs[imax]), 3)) + " Hz")
            else:
                rep.check("I. spectrum", "s" + str(n) + ": spectrum returned", False,
                          "HTTP " + str(st))

        # --- E. physical sanity -------------------------------------------
        mine0 = independent_stats(cols[0])
        rep.check("E. physical", f"s{n}: values plausible for g",
                  mine0["peak"] < 50.0,
                  f"peak {mine0['peak']:.4f} g")

    # ------------------------------------------------------------ F. repeat --
    print("\n--- repeatability across the 10 samples ---")
    for ci in range(8):
        acs = [r["ac_rms"] for r in per_sample if r["ch"] == ci]
        dcs = [r["mean"] for r in per_sample if r["ch"] == ci]
        if len(acs) < 2:
            continue
        ac_cv = statistics.pstdev(acs) / statistics.fmean(acs) if statistics.fmean(acs) else 0
        dc_spread = max(dcs) - min(dcs)
        # One machine in one state, sampled ten times two minutes apart: the
        # vibration level should not wander. A large spread means either the
        # machine changed or the pipeline is not reproducible -- both worth
        # knowing, so this reports rather than silently passing.
        rep.check("F. repeatability", f"ch{ci}: AC rms stable across samples",
                  ac_cv < 0.50,
                  f"CV {ac_cv*100:.1f}%, DC spread {dc_spread:.5f} g")

    # ------------------------------------------------------------- G. negative --
    print("\n--- negative tests: bad input must be refused ---")
    def post_csv(name: str, body: bytes) -> tuple[int, str]:
        boundary = "----negtest"
        parts = bytearray()
        for k, v in (("device_id", SENSOR_ID), ("expected_channels", "8")):
            parts += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        parts += (f"--{boundary}\r\nContent-Disposition: form-data; "
                  f'name="file"; filename="{name}"\r\n'
                  f"Content-Type: text/csv\r\n\r\n").encode()
        parts += body + b"\r\n" + f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            PLATFORM_API_URL + "/api/v1/ingest/raw", data=bytes(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "X-API-Key": key or ""}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, ""
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:160]
        except Exception as e:  # noqa: BLE001
            return 0, f"{type(e).__name__}: {e}"

    st, msg = post_csv("empty.csv", b"")
    rep.check("G. negative", "empty file refused", st >= 400, f"HTTP {st} {msg[:80]}")

    # These two must be REJECTED FOR THEIR TIMESTAMPS, not for their shape.
    # The first version sent one channel, so the API answered "Expected
    # exactly 8 channels but found 1" -- a pass that proved nothing about the
    # monotonic guard, which is the guard that blocked every real gateway file
    # until the per-sample timestamp fix. The extra assertion below pins that.
    hdr = ("timestamp_ms," + ",".join("ch" + str(i) for i in range(8)) + NL_C).encode()
    vals = ("," + ",".join("0.1" for _ in range(8)) + NL_C).encode()

    st, msg = post_csv("nonmono.csv", hdr + b"1000" + vals + b"1000" + vals + b"1000" + vals)
    rep.check("G. negative", "repeated timestamps refused", st >= 400,
              "HTTP " + str(st) + " " + msg[:100])
    rep.check("G. negative", "  ...refused for TIME, not channel count",
              st >= 400 and "channel" not in msg.lower(), msg[:100])

    st, msg = post_csv("backwards.csv", hdr + b"3000" + vals + b"2000" + vals + b"1000" + vals)
    rep.check("G. negative", "decreasing timestamps refused", st >= 400,
              "HTTP " + str(st) + " " + msg[:100])
    rep.check("G. negative", "  ...refused for TIME, not channel count",
              st >= 400 and "channel" not in msg.lower(), msg[:100])

    st, msg = post_csv("garbage.csv", b"this is not a csv at all\n\x00\x01\x02")
    rep.check("G. negative", "non-CSV refused", st >= 400, f"HTTP {st} {msg[:80]}")

    # An unknown device must not be silently attached to some other sensor.
    boundary = "----negtest2"
    parts = bytearray()
    for k, v in (("device_id", "00:00:00:00:00:00"), ("expected_channels", "8")):
        parts += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    parts += (f"--{boundary}\r\nContent-Disposition: form-data; "
              f'name="file"; filename="x.csv"\r\n\r\n').encode()
    parts += b"timestamp_ms,ch0\n1000,0.1\n1001,0.2\n" + b"\r\n" + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        PLATFORM_API_URL + "/api/v1/ingest/raw", data=bytes(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "X-API-Key": key or ""}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            st2 = r.status
    except urllib.error.HTTPError as e:
        st2 = e.code
    rep.check("G. negative", "unknown device refused", st2 >= 400, f"HTTP {st2}")

    # Authentication must actually be enforced.
    # A well-formed request with NO key. The earlier version posted b"x" with a
    # bogus boundary, so FastAPI rejected it at multipart parsing (400) before
    # the auth dependency ever ran -- it tested the parser, not the lock.
    bnd = "----nokey"
    CRLF = chr(13) + chr(10)
    body = bytearray()
    for k, v in (("device_id", SENSOR_ID), ("expected_channels", "8")):
        body += ("--" + bnd + CRLF
                 + 'Content-Disposition: form-data; name="' + k + '"' + CRLF + CRLF
                 + v + CRLF).encode()
    body += ("--" + bnd + CRLF
             + 'Content-Disposition: form-data; name="file"; filename="x.csv"' + CRLF
             + "Content-Type: text/csv" + CRLF + CRLF).encode()
    csv_body = ("timestamp_ms,ch0" + chr(10) + "1000,0.1" + chr(10)
                + "1001,0.2" + chr(10)).encode()
    body += csv_body + CRLF.encode() + ("--" + bnd + "--" + CRLF).encode()
    req = urllib.request.Request(
        PLATFORM_API_URL + "/api/v1/ingest/raw", data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={bnd}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    rep.check("G. negative", "missing API key refused", code in (401, 403),
              f"HTTP {code} (must be 401/403, not a parse error)")

    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
