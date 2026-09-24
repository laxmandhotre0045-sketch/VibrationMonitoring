"""Push gateway snapshot CSVs into this platform's own ingest API.

The Beckhoff uploader (`my_script.py`) speaks the Senvia protocol:

    POST /v1/vibration-csv-trend/upload
    form: sensorId, channelCount, metadata (a JSON blob), file

This platform speaks a different one:

    POST /api/v1/ingest/raw
    header: X-API-Key
    form: device_id, file, sample_rate_hz, expected_channels, measured_at,
          sample_unit, sensitivity_mv_per_g

Same CSV, different envelope. Rather than teach one script two protocols --
which is how a push ends up going to the wrong place after a hurried edit --
this watches the folder the uploader already archives to and forwards each file
here. Senvia keeps receiving exactly what it received before; this is additive.

Run it beside the uploader:

    python platform_push.py --watch ./archive

or push files that already exist:

    python platform_push.py snapshot_1.csv snapshot_2.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from uploader_settings import SAMPLE_UNIT, SENSITIVITY_MV_PER_G, SENSOR_ID, _get

log = logging.getLogger("platform_push")

PLATFORM_URL = _get("PLATFORM_API_URL", "http://localhost:8000")
CONFIG_PATH = "/api/v1/acquisition/config"
INGEST_PATH = "/api/v1/ingest/raw"

#: The ingest API is key-authenticated, so the key is a real secret. It is read
#: from a file that .gitignore covers rather than from a literal here.
_KEY_FILE = Path(__file__).resolve().parent / ".ingest_key"


def api_key() -> str:
    key = _get("PLATFORM_API_KEY", "")
    if key:
        return key
    if _KEY_FILE.is_file():
        return _KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def fetch_config(device_id: str) -> dict:
    """Read the acquisition settings the dashboard is showing.

    The sample rate must come from here rather than from the gateway's own
    idea of it: the platform stores what it was told, and a file declared at a
    rate the platform does not expect produces a spectrum whose frequency axis
    is wrong by exactly that ratio, with nothing to show it.
    """
    url = f"{PLATFORM_URL}{CONFIG_PATH}?device_id={urllib.parse.quote(device_id)}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read())


def _multipart(fields: dict[str, str], filename: str, payload: bytes) -> tuple[bytes, str]:
    """Build a multipart body. Hand-rolled to keep this dependency-free."""
    boundary = f"----platformpush{uuid.uuid4().hex}"
    out = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        out += f"--{boundary}\r\n".encode()
        out += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        out += f"{value}\r\n".encode()
    out += f"--{boundary}\r\n".encode()
    out += (
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode()
    out += payload + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _measured_at(path: Path) -> str:
    """Capture time from the CSV's first timestamp, falling back to mtime.

    The filename carries a timestamp too, but the samples are the record of
    when the machine was actually turning.
    """
    try:
        with path.open(newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)                      # header
            first = next(reader, None)
        if first and first[0].isdigit():
            ts = int(first[0])
            return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


def push(path: Path, cfg: dict, device_id: str, key: str) -> bool:
    payload = path.read_bytes()
    if not payload.strip():
        log.warning("%s is empty; skipped", path.name)
        return False

    channels = int(cfg.get("totalChannelCount") or 8)
    fields = {
        "device_id": device_id,
        "sample_rate_hz": str(cfg.get("sampleRateHz") or ""),
        "expected_channels": str(channels),
        "measured_at": _measured_at(path),
    }

    # What the numbers in this CSV physically are, and what each channel's
    # transducer is. The PLC applies counts x (5 V / 32768) / sensitivity
    # before publishing, so the file is already acceleration in g.
    #
    # This leg used to send neither, while my_script.py sent both to Senvia.
    # The platform therefore recorded every capture as 'unconfirmed' and its
    # own safety rule withheld every severity -- correctly, on information it
    # was never given. Only what is actually configured is sent: an absent
    # setting stays absent rather than becoming a default, because a guessed
    # unit produces a plausible wrong severity rather than an obvious one.
    if SAMPLE_UNIT:
        fields["sample_unit"] = str(SAMPLE_UNIT)
    if SENSITIVITY_MV_PER_G and len(SENSITIVITY_MV_PER_G) == channels:
        fields["sensitivity_mv_per_g"] = ",".join(
            f"{v:g}" for v in SENSITIVITY_MV_PER_G
        )
    elif SENSITIVITY_MV_PER_G:
        log.warning(
            "%d sensitivities configured for %d channels; sending none rather "
            "than padding, since a figure on the wrong channel is wrong by the "
            "ratio between the two and looks ordinary.",
            len(SENSITIVITY_MV_PER_G), channels,
        )
    body, content_type = _multipart(fields, path.name, payload)
    req = urllib.request.Request(
        f"{PLATFORM_URL}{INGEST_PATH}",
        data=body,
        headers={"Content-Type": content_type, "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            ack = json.loads(resp.read() or b"{}")
        log.info(
            "%s -> HTTP %s  capture=%s samples=%s channels=%s",
            path.name, resp.status, ack.get("capture_id") or ack.get("id"),
            ack.get("sample_count"), ack.get("channel_count"),
        )
        return True
    except urllib.error.HTTPError as exc:
        # The body carries the reason -- a missing device, a channel-count
        # mismatch -- and dropping it would leave only a bare status code.
        log.error("%s -> HTTP %s  %s", path.name, exc.code, exc.read().decode()[:300])
    except Exception as exc:
        log.error("%s -> %s: %s", path.name, type(exc).__name__, exc)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path, help="CSV files to push")
    ap.add_argument("--watch", type=Path, metavar="DIR",
                    help="watch DIR and push each new CSV as it appears")
    ap.add_argument("--device-id", default=SENSOR_ID)
    ap.add_argument("--interval", type=float, default=10.0,
                    help="seconds between scans when watching (default 10)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    key = api_key()
    if not key:
        log.error("No API key. Put one in %s or set PLATFORM_API_KEY. "
                  "Create one under Settings -> Integrations -> API keys.", _KEY_FILE)
        return 2

    device_id = args.device_id
    if not device_id:
        log.error("No device id. Set SENSOR_ID in .env or pass --device-id.")
        return 2

    try:
        cfg = fetch_config(device_id)
    except urllib.error.HTTPError as exc:
        log.error("Config lookup failed (HTTP %s): %s", exc.code, exc.read().decode()[:300])
        log.error("The sensor needs its device_id set to %r under Equipment Master.", device_id)
        return 2

    log.info("Platform  : %s", PLATFORM_URL)
    log.info("Device    : %s", device_id)
    log.info("Config    : %s kSPS, %s ch, Fmax %s Hz, LOR %s",
             cfg.get("ksps"), cfg.get("totalChannelCount"),
             cfg.get("fmaxHz"), cfg.get("lor"))

    if not args.watch:
        ok = sum(push(p, cfg, device_id, key) for p in args.files if p.is_file())
        log.info("Pushed %d of %d file(s)", ok, len(args.files))
        return 0 if ok == len(args.files) else 1

    # Watch mode. Files already present when watching starts are pushed too,
    # so a restart does not silently skip whatever arrived while it was down.
    seen: set[Path] = set()
    log.info("Watching %s every %.0fs", args.watch.resolve(), args.interval)
    while True:
        for path in sorted(args.watch.glob("*.csv")):
            if path in seen:
                continue
            # Wait for the writer to finish: a file still being written pushes
            # a truncated window that looks like a real short capture.
            if time.time() - path.stat().st_mtime < 2:
                continue
            if push(path, cfg, device_id, key):
                seen.add(path)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
