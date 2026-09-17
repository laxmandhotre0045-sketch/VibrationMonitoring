import csv
import json
import logging
import os
import re
import shutil
import signal
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # script still runs in upload-only mode

# ----------------------------------------------------------------------------
# Static settings (edit these for your machine)
# ----------------------------------------------------------------------------
# Settings now come from uploader_settings.py, which reads gateway/.env, so
# that the broker password is not a literal in a tracked file.
#
# The value that changed: MQTT_BROKER is 127.0.0.1, not broker.hivemq.com. The
# 50 kSPS PLC project publishes to the gateway's local Mosquitto broker. Pointed
# at hivemq, this script connects, subscribes, and then receives nothing at all,
# indefinitely, with no error to say so.
from uploader_settings import (       # noqa: E402
    SENSOR_ID, BASE_URL, CONFIG_URL, PUSH_URL,
    MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, MQTT_QOS,
    MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID, MQTT_KEEPALIVE,
    MQTT_TRANSPORT, MQTT_WS_PATH, MQTT_TLS,
    sample_metadata,
    report as report_settings,
    PUSH_TARGET,
)

# --- Local folders / files --------------------------------------------------
WATCH_DIR = Path("./acquisition_data")   # snapshot CSVs land here
SENT_DIR = WATCH_DIR / "sent"            # uploaded files wait here briefly
FAILED_DIR = WATCH_DIR / "failed"
UNPARSED_LOG = WATCH_DIR / "unparsed_messages.log"

# --- Local archive (permanent copy of every CSV that reached the cloud) -----
# Each CSV is copied here right after its upload succeeds, so the folder holds
# exactly the same files the API stored in the cloud. Nothing is ever deleted
# from this folder by the script.
# Configurable, because D:\ exists on the gateway machine and not
# everywhere else. A missing archive folder is warned about, not fatal.
LOCAL_ARCHIVE_DIR = Path(os.environ.get("LOCAL_ARCHIVE_DIR", "./archive"))
# True  -> D:\Vibration Data\2026-09-15\<file>.csv  (one sub-folder per day)
# False -> D:\Vibration Data\<file>.csv             (flat folder)
LOCAL_ARCHIVE_BY_DATE = False

CSV_PATTERN = "*.csv"
CONFIG_POLL_SECONDS = 60       # how often to re-read the config API
MAIN_LOOP_SECONDS = 5          # scheduler tick
MIN_FILE_AGE_SECONDS = 10      # age check for externally-dropped files
UPLOAD_TIMEOUT_SECONDS = 120
MAX_UPLOAD_ATTEMPTS = 5
SENT_RETENTION_MINUTES = 30    # uploaded CSVs stay in sent/ this long
DEFAULT_PUSH_INTERVAL_MIN = 60
DEFAULT_LOR = 12800            # rows per snapshot until config says otherwise
DEFAULT_CHANNELS = 8
SAMPLE_DECIMALS = 4            # value formatting, matches the sample file
KSPS_TO_SPS = 1000             # config reports kilo-samples/s; unit conversion

# Optional auth: e.g. {"Authorization": "Bearer <token>"}
EXTRA_HEADERS: dict = {}

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("beckhoff_uploader.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("uploader")

session = requests.Session()
session.headers.update(EXTRA_HEADERS)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    log.info("Shutdown signal received, finishing current cycle...")
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ----------------------------------------------------------------------------
# Config handling
# ----------------------------------------------------------------------------
class AcqConfig:
    """Parsed view of the server-side acquisition configuration."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.push_interval_min = self._to_float(
            raw.get("miniutes"), DEFAULT_PUSH_INTERVAL_MIN)
        self.lor = int(self._to_float(raw.get("lor"), DEFAULT_LOR))
        self.fmax = self._to_float(raw.get("fmax"), None)
        formula = raw.get("acquisitionFormula") or {}
        self.ksps = self._to_float(raw.get("ksps"), None)
        if self.ksps is None:              # fall back to formula sample rate
            rate = self._to_float(formula.get("sampleRateHz"), None)
            if rate is not None:
                self.ksps = rate / KSPS_TO_SPS
        self.block_time_s = self._to_float(formula.get("blockTimeSeconds"), None)
        self.window_type = raw.get("windowType")
        self.channel_count = int(self._to_float(
            raw.get("totalChannelCount"), DEFAULT_CHANNELS))

    @staticmethod
    def _to_float(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def summary(self) -> str:
        return (f"push every {self.push_interval_min:g} min | "
                f"ksps={self.ksps} lor={self.lor} fmax={self.fmax} "
                f"blockTime={self.block_time_s}s window={self.window_type} "
                f"channels={self.channel_count}")


def fetch_config(previous):
    """GET the config API. Returns new config, or `previous` on failure."""
    try:
        resp = session.get(CONFIG_URL, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        if not raw.get("success", True):
            log.warning("Config API returned success=false: %s", raw)
            return previous
        cfg = AcqConfig(raw)
        if previous is None or cfg.raw != previous.raw:
            log.info("Config loaded/changed: %s", cfg.summary())
        return cfg
    except Exception as exc:
        log.warning("Could not fetch config (%s). Keeping previous settings.", exc)
        return previous


# ----------------------------------------------------------------------------
# Payload parsing helpers
# ----------------------------------------------------------------------------
_CH_KEY_RE = re.compile(r"(?i)^n?(?:ch|channel|sensor)[ _\-]?(\d+)$")
_TS_KEYS = ("system timestamp", "systemtimestamp", "timestamp_ms",
            "timestamp", "time", "ts", "sampletimestamp")

_EPOCH_1601_MS = 11644473600000  # ms between 1601-01-01 and 1970-01-01


def to_epoch_ms(value):
    """Best-effort conversion of a timestamp value to epoch milliseconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e16:                      # Windows FILETIME (100 ns since 1601)
            return int(v / 10000 - _EPOCH_1601_MS)
        if v > 1e14:                      # microseconds
            return int(v / 1000)
        if v > 1e11:                      # already milliseconds
            return int(v)
        if v > 1e8:                       # seconds
            return int(v * 1000)
        return None                       # too small to be an epoch time
    if isinstance(value, str):
        s = value.strip()
        try:
            return to_epoch_ms(float(s))
        except ValueError:
            pass
        try:                              # ISO date, e.g. 2026-07-27T16:26:38.672
            s2 = s.replace("Z", "+00:00")
            # device quirk: colon before milliseconds (16:52:11:210)
            s2 = re.sub(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}):(\d{1,6})$",
                        r"\1.\2", s2)
            dt = datetime.fromisoformat(s2)
            if dt.tzinfo is None:
                dt = dt.astimezone()      # assume local time
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None
    return None


def _json_loads_tolerant(text: str):
    """json.loads with fallbacks for common device quirks."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    if not text[:1] in ("{", "["):
        return None          # not JSON-like; let the text parser handle it
    # multiple JSON objects concatenated in one payload -> list of them
    try:
        dec = json.JSONDecoder()
        objs, idx, n = [], 0, len(text)
        while idx < n:
            while idx < n and text[idx] in " \r\n\t\x00,":
                idx += 1
            if idx >= n:
                break
            obj, end = dec.raw_decode(text, idx)
            objs.append(obj)
            idx = end
        if objs:
            return objs if len(objs) > 1 else objs[0]
    except ValueError:
        pass
    # single-quoted pseudo-JSON, True/False/None literals
    try:
        import ast
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _numeric_list(v):
    """Return list of floats if v is a list of numbers, else None."""
    if not isinstance(v, list) or not v:
        return None
    out = []
    for x in v:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        out.append(float(x))
    return out


def parse_message(payload: bytes, channel_count: int):
    """
    Parse one MQTT payload into (timestamp_ms | None, rows).
    Each row is a list of floats, one value per channel.

    Handled shapes:
      A) {"System Timestamp": ..., "Ch1": [...], ..., "Ch8": [...]}
         channel-named arrays -> transpose to rows
      B) {"timestamp": ..., "data"/"values"/"samples": [[...], ...]}
         list of lists: per-channel arrays or ready rows (auto-detected)
      C) {"ch1": 0.1, "ch2": 0.2, ...}  scalar per channel -> one row
      D) [ {...}, {...} ] list of any of the above -> concatenated
      E) plain text lines of comma/space separated numbers -> rows
    """
    text = payload.decode("utf-8", errors="replace").strip().strip("\x00")
    data = _json_loads_tolerant(text)

    if data is None:                       # ---- plain text / CSV lines ----
        rows = []
        for line in text.splitlines():
            parts = re.split(r"[,;\s]+", line.strip())
            try:
                vals = [float(p) for p in parts if p != ""]
            except ValueError:
                continue                   # header or junk line
            if vals:
                rows.append(vals)
        return (None, rows) if rows else (None, None)

    if isinstance(data, list) and data and isinstance(data[0], dict):
        ts, rows = None, []                # ---- list of objects (D) -------
        for item in data:
            t, r = _parse_obj(item, channel_count)
            ts = ts or t
            if r:
                rows.extend(r)
        return ts, (rows or None)

    if isinstance(data, dict):
        return _parse_obj(data, channel_count)

    if isinstance(data, list):             # bare array
        rows = _rows_from_list_of_lists(data, channel_count)
        if rows is None:
            vals = _numeric_list(data)
            rows = [vals] if vals else None
        return None, rows

    return None, None


def _parse_obj(data: dict, channel_count: int):
    """Parse a single JSON object -> (timestamp_ms, rows)."""
    # --- timestamp ---------------------------------------------------------
    ts = None
    for k, v in data.items():
        if str(k).strip().lower() in _TS_KEYS:
            ts = to_epoch_ms(v)
            if ts:
                break

    # --- shape A: channel-named keys --------------------------------------
    chans = {}
    scalars = {}
    for k, v in data.items():
        m = _CH_KEY_RE.match(str(k).strip())
        if not m:
            continue
        idx = int(m.group(1))
        arr = _numeric_list(v)
        if arr is not None:
            chans[idx] = arr
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            scalars[idx] = float(v)

    if chans:
        order = sorted(chans)
        n = max(len(a) for a in chans.values())
        rows = [[chans[c][i] if i < len(chans[c]) else 0.0 for c in order]
                for i in range(n)]
        return ts, rows

    if scalars:                            # ---- shape C: one sample/message
        order = sorted(scalars)
        return ts, [[scalars[c] for c in order]]

    # --- shape B: a container key holding the samples ----------------------
    for key in ("data", "values", "samples", "payload", "channels", "sensordata"):
        for k, v in data.items():
            if str(k).strip().lower() != key:
                continue
            if isinstance(v, dict):        # nested object, e.g. "Values": {...}
                t2, rows = _parse_obj(v, channel_count)
                if rows:
                    return ts or t2, rows
                continue
            if isinstance(v, list):
                rows = _rows_from_list_of_lists(v, channel_count)
                if rows:
                    return ts, rows
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    all_rows = []
                    for item in v:
                        _, r = _parse_obj(item, channel_count)
                        if r:
                            all_rows.extend(r)
                    if all_rows:
                        return ts, all_rows
                vals = _numeric_list(v)
                if vals:
                    return ts, [vals]

    # --- last resort: any numeric-array values, sorted by key ---------------
    arrays = {k: _numeric_list(v) for k, v in data.items()}
    arrays = {k: a for k, a in arrays.items() if a is not None}
    if arrays:
        order = sorted(arrays)
        n = max(len(a) for a in arrays.values())
        rows = [[arrays[k][i] if i < len(arrays[k]) else 0.0 for k in order]
                for i in range(n)]
        return ts, rows

    return ts, None


def _rows_from_list_of_lists(v, channel_count: int):
    """[[...],[...]] -> rows. Detects per-channel vs per-row orientation."""
    if not (isinstance(v, list) and v and all(isinstance(x, list) for x in v)):
        return None
    mats = [_numeric_list(x) for x in v]
    if any(m is None for m in mats):
        return None
    if len(mats) == channel_count and len(mats[0]) != channel_count:
        n = max(len(m) for m in mats)      # per-channel arrays -> transpose
        return [[m[i] if i < len(m) else 0.0 for m in mats] for i in range(n)]
    return mats                            # already rows


# ----------------------------------------------------------------------------
# Snapshot writer: MQTT bins -> one CSV per acquisition window
# ----------------------------------------------------------------------------
class SnapshotWriter:
    """
    Accumulates (timestamp_ms, [ch0..chN]) sample rows and writes one snapshot
    CSV per acquisition window:

        timestamp_ms,ch0,...,ch{N-1}

    named YYYYMMDD_HHMMSS_<32-hex>_snapshot_<n>.csv  (matches server sample).

    The window is defined by the configuration API, not by a fixed message
    count:

        blockTimeSeconds    = lor / fmax          (served by the config API)
        samples_per_channel = int(blockTimeSeconds * ksps * 1000)

    e.g. lor=2500, fmax=9000, ksps=25 -> 0.2778 s -> 6944 samples/channel.

    A window is complete as soon as `samples_per_channel` rows have
    accumulated, regardless of how many samples each MQTT message carries.
    Samples beyond the cut (the fractional last bin, e.g. 6944/1249 = 5.55
    messages) carry over as the start of the next window.

    Only the LATEST complete window is kept (in memory). One CSV is written
    per push interval, when the scheduler calls `flush_latest()` — so exactly
    one file per `miniutes` from the config API is uploaded, the one closest
    to the trigger time. Older windows between pushes are discarded.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._rows: list = []              # [(ts_ms, [floats]), ...]
        self._counter = 0
        self._lor = DEFAULT_LOR
        self._channels = DEFAULT_CHANNELS
        self._unparsed = 0
        # last-seen config values that drive the snapshot geometry
        self._ksps = None
        self._block_time_s = None
        self._configured = False
        # dynamic acquisition values
        self._samples_per_channel = self._lor
        self._msg_rows = None              # samples/channel measured per MQTT msg
        self._bins_per_csv = None          # bins computed from msg length
        self._total_rows_per_csv = self._samples_per_channel
        self._msg_count = 0                # messages consumed this window
        self._latest_block = None          # newest complete window, push-pending
        self._windows_skipped = 0          # complete windows replaced unsent
        WATCH_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _derive_samples(lor: int, ksps, block_time_s):
        """Samples per channel for one acquisition window."""
        if block_time_s is None or ksps is None:
            samples = lor                  # config incomplete: lor rows per CSV
        else:
            # ksps is kilo-samples/second -> samples/second
            samples = int(block_time_s * ksps * KSPS_TO_SPS)
        return max(samples, 1)

    @staticmethod
    def _derive_total_rows(samples_per_channel: int, msg_rows: int | None):
        """Calculate total rows as samples * bins when message length is known."""
        if msg_rows and msg_rows > 0:
            bins = samples_per_channel / msg_rows
            return max(int(msg_rows * bins), 1)
        return max(samples_per_channel, 1)

    def apply_config(self, cfg: AcqConfig):
        with self._lock:
            # any of these changes the composition of a snapshot
            changed = (not self._configured or
                       cfg.lor != self._lor or
                       cfg.channel_count != self._channels or
                       cfg.ksps != self._ksps or
                       cfg.block_time_s != self._block_time_s)
            if not changed:
                return
            if self._configured:
                log.info("Snapshot geometry changed: lor %d->%d, channels %d->%d, "
                         "ksps %s->%s, blockTime %ss->%ss "
                         "(partial accumulation discarded)",
                         self._lor, cfg.lor, self._channels, cfg.channel_count,
                         self._ksps, cfg.ksps, self._block_time_s, cfg.block_time_s)
            self._lor = cfg.lor
            self._channels = cfg.channel_count
            self._ksps = cfg.ksps
            self._block_time_s = cfg.block_time_s
            self._samples_per_channel = self._derive_samples(
                self._lor, self._ksps, self._block_time_s)
            self._total_rows_per_csv = self._derive_total_rows(
                self._samples_per_channel, self._msg_rows)
            self._bins_per_csv = None
            # samples from the previous configuration must not mix into the new
            # window; msg length is re-measured from the next JSON message
            self._rows = []
            self._msg_count = 0
            self._msg_rows = None
            self._latest_block = None
            self._windows_skipped = 0
            self._configured = True
            log.info("Samples per channel per CSV = %d", self._samples_per_channel)

    # ---- ingestion ---------------------------------------------------------
    def add_message(self, topic: str, payload: bytes):
        """
        Append the message's samples; each time the accumulated rows reach
        `samples_per_channel` the completed window replaces `_latest_block`.
        Rows past the cut stay buffered as the start of the next window
        (fractional-bin carry-over). No CSV is written here — that happens
        once per push interval via `flush_latest()`.
        """
        with self._lock:
            channels = self._channels
        ts, rows = parse_message(payload, channels)
        if not rows:
            self._log_unparsed(payload)
            return
        if ts is None:
            ts = int(time.time() * 1000)       # fall back to arrival time

        blocks = []
        with self._lock:
            # msg length is measured from the JSON payload itself (length of
            # the per-channel arrays) on EVERY message, so it stays dynamic:
            # bins per CSV = samples_per_channel / measured msg length
            if self._msg_rows != len(rows):    # first message / length change
                self._msg_rows = len(rows)
                self._bins_per_csv = (
                    self._samples_per_channel / self._msg_rows
                    if self._msg_rows else 0.0)
                self._total_rows_per_csv = self._derive_total_rows(
                    self._samples_per_channel, self._msg_rows)
                log.info(
                    "MQTT msg length = %d samples/channel -> bins per CSV = %.2f, "
                    "total rows = %d",
                    self._msg_rows, self._bins_per_csv, self._total_rows_per_csv)
            for r in rows:
                r = (r + [0.0] * channels)[:channels]  # pad/trim to N channels
                self._rows.append((ts, r))
            self._msg_count += 1
            while len(self._rows) >= self._total_rows_per_csv:
                blocks.append(self._rows[:self._total_rows_per_csv])
                self._rows = self._rows[self._total_rows_per_csv:]
                self._msg_count = 0
            if blocks:
                # keep only the newest complete window for the next push
                if self._latest_block is not None:
                    self._windows_skipped += 1
                self._windows_skipped += len(blocks) - 1
                self._latest_block = blocks[-1]

    def _log_unparsed(self, payload: bytes):
        self._unparsed += 1
        if self._unparsed <= 5 or self._unparsed % 100 == 0:
            log.warning("Unparsed MQTT message #%d (logged to %s)",
                        self._unparsed, UNPARSED_LOG.name)
        try:
            with UNPARSED_LOG.open("ab") as fh:
                fh.write(payload + b"\n")
        except Exception:
            pass

    # ---- output ------------------------------------------------------------
    def _write_snapshot(self, block):
        with self._lock:
            self._counter += 1
            counter = self._counter
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_{uuid.uuid4().hex}_snapshot_{counter}.csv"
        tmp = WATCH_DIR / (name + ".part")
        target = WATCH_DIR / name
        header = ["timestamp_ms"] + [f"ch{i}" for i in range(len(block[0][1]))]
        fmt = f"%.{SAMPLE_DECIMALS}f"
        try:
            # Per-SAMPLE timestamps, derived from the sample rate.
            #
            # Every sample in one MQTT message used to carry that message's
            # single timestamp, so a 13,888-row window held about seven
            # distinct values and 2,000 samples claimed to be simultaneous.
            # This platform's ingest API rejects that outright -- "Timestamps
            # must increase monotonically" -- and any spectrum computed from
            # such a column has a meaningless frequency axis.
            #
            # The message timestamp is kept as the start of its own run of
            # samples, and the samples within it are spaced by 1/fs. That is
            # the true geometry: at 50 kSPS they are 20 us apart.
            rate = self._ksps * 1000.0 if self._ksps else None
            with tmp.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(header)
                if rate:
                    step_us = 1_000_000.0 / rate
                    run_start_ts = None      # ts of the current message
                    run_index = 0            # sample position within it
                    last_us = None
                    for ts, vals in block:
                        if ts != run_start_ts:
                            run_start_ts, run_index = ts, 0
                        micros = ts * 1000.0 + run_index * step_us
                        # A late message can carry a timestamp at or before the
                        # previous run's last sample. Nudging forward by one
                        # sample keeps the column strictly increasing without
                        # inventing a gap that was not measured.
                        if last_us is not None and micros <= last_us:
                            micros = last_us + step_us
                        last_us = micros
                        run_index += 1
                        writer.writerow([f"{micros / 1000.0:.3f}"]
                                        + [fmt % v for v in vals])
                else:
                    # No known rate: fall back to the message timestamp rather
                    # than fabricate a spacing. The file will be refused by a
                    # strict ingest, which is the honest outcome.
                    for ts, vals in block:
                        writer.writerow([ts] + [fmt % v for v in vals])
            tmp.rename(target)             # atomic: never uploaded half-done
            log.info("Snapshot ready: %s (%d rows x %d ch)",
                     name, len(block), len(block[0][1]))
            return target
        except Exception as exc:
            log.error("Could not write snapshot %s: %s", name, exc)
            return None

    def flush_latest(self):
        """
        Write the most recent complete window to a CSV and return its path,
        or None if no window completed since the last flush. Called once per
        push interval so exactly one file is uploaded per trigger.
        """
        with self._lock:
            block = self._latest_block
            skipped = self._windows_skipped
            self._latest_block = None
            self._windows_skipped = 0
        if block is None:
            return None
        if skipped:
            log.info("Discarded %d older window(s) this interval; "
                     "pushing only the latest", skipped)
        return self._write_snapshot(block)

    def pending_row_count(self):
        with self._lock:
            return len(self._rows)

    def progress(self):
        """(rows_so_far, samples_per_channel, msgs_in_window)."""
        with self._lock:
            return (len(self._rows), self._samples_per_channel,
                    self._msg_count)


writer = SnapshotWriter()


# ----------------------------------------------------------------------------
# MQTT client
# ----------------------------------------------------------------------------
def start_mqtt():
    """Connect to the broker in a background thread; auto-reconnects."""
    if mqtt is None:
        log.error("paho-mqtt is not installed (pip install paho-mqtt). "
                  "Running WITHOUT MQTT: only files dropped into %s "
                  "will be uploaded.", WATCH_DIR)
        return None

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("MQTT connected to %s:%d, subscribing to '%s'",
                     MQTT_BROKER, MQTT_PORT, MQTT_TOPIC)
            client.subscribe(MQTT_TOPIC, qos=MQTT_QOS)
        else:
            log.error("MQTT connect failed with code %s", rc)

    def on_disconnect(client, userdata, *args):
        log.warning("MQTT disconnected; auto-reconnect in progress...")

    def on_message(client, userdata, msg):
        try:
            writer.add_message(msg.topic, msg.payload)
        except Exception as exc:
            log.error("Failed to handle MQTT message: %s", exc)

    try:  # paho v2 API first, fall back to v1
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID,
            transport=MQTT_TRANSPORT)
    except (AttributeError, TypeError):
        client = mqtt.Client(client_id=MQTT_CLIENT_ID, transport=MQTT_TRANSPORT)

    if MQTT_TRANSPORT == "websockets":
        client.ws_set_options(path=MQTT_WS_PATH)
    if MQTT_TLS:
        import ssl
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    # Accepted but not currently enforced: the gateway's mosquitto.conf has no
    # password_file and no acl_file, so allow_anonymous applies. Sent anyway, so
    # that adding a password file later does not silently stop ingestion.
    if MQTT_USERNAME or MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
    client.loop_start()
    return client


# ----------------------------------------------------------------------------
# Local archive: permanent copy of every uploaded CSV
# ----------------------------------------------------------------------------
def archive_target(path: Path) -> Path:
    """Where the permanent local copy of `path` lives (or would live)."""
    dest_dir = LOCAL_ARCHIVE_DIR
    if LOCAL_ARCHIVE_BY_DATE:
        # the snapshot name starts with YYYYMMDD_HHMMSS -> folder per day
        m = re.match(r"^(\d{4})(\d{2})(\d{2})_", path.name)
        day = (f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m
               else datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"))
        dest_dir = dest_dir / day
    return dest_dir / path.name


def is_archived(path: Path) -> bool:
    """True if a complete copy of `path` already exists in the archive."""
    try:
        dest = archive_target(path)
        return dest.is_file() and dest.stat().st_size == path.stat().st_size
    except OSError:
        return False


def archive_locally(path: Path) -> bool:
    """
    Copy an uploaded CSV into LOCAL_ARCHIVE_DIR. Returns True on success
    (or if an identical copy is already there). Never raises: the upload
    has already succeeded, so a local-disk problem must not stop the cycle.
    """
    try:
        if is_archived(path):
            return True
        dest = archive_target(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        shutil.copy2(str(path), str(tmp))  # keeps the original mtime
        tmp.replace(dest)                  # atomic: never a half-written file
        log.info("Archived %s -> %s", path.name, dest)
        return True
    except Exception as exc:
        log.error("Could not archive %s to %s: %s (will retry from sent/)",
                  path.name, LOCAL_ARCHIVE_DIR, exc)
        return False


# ----------------------------------------------------------------------------
# File collection & upload
# ----------------------------------------------------------------------------
_attempts: dict = {}


def pending_csv_files():
    now = time.time()
    files = []
    for p in sorted(WATCH_DIR.glob(CSV_PATTERN)):
        if not p.is_file():
            continue
        try:
            # our snapshots are complete by construction; age-check the rest
            if ("_snapshot_" not in p.name
                    and now - p.stat().st_mtime < MIN_FILE_AGE_SECONDS):
                continue
        except OSError:
            continue
        files.append(p)
    return files


def is_valid_csv(path: Path) -> bool:
    try:
        if path.stat().st_size == 0:
            return False
        with path.open("r", newline="", errors="replace") as fh:
            first = next(csv.reader(fh), None)
            return first is not None and len(first) > 0
    except Exception:
        return False


def upload_to_platform(path: Path, cfg: AcqConfig) -> bool:
    """Send one CSV to this VibrationMonitoring instance's ingest API.

    A different protocol from Senvia's -- key-authenticated, its own field
    names -- so it lives in platform_push rather than being spliced into the
    Senvia call, where one edit to a shared dict could send a file to the wrong
    place.
    """
    try:
        import platform_push
    except ImportError:
        log.error("platform_push.py is not beside this script; "
                  "cannot push to the platform")
        return False

    key = platform_push.api_key()
    if not key:
        log.error("No platform API key. Put one in gateway/.ingest_key or set "
                  "PLATFORM_API_KEY.")
        return False
    try:
        pcfg = platform_push.fetch_config(SENSOR_ID)
    except Exception as exc:
        log.error("Platform config lookup failed for %s: %s", SENSOR_ID, exc)
        return False
    return platform_push.push(path, pcfg, SENSOR_ID, key)


def upload_file(path: Path, cfg: AcqConfig) -> bool:
    """Send one CSV to whichever destination(s) PUSH_TARGET names."""
    if PUSH_TARGET in ("platform", "both"):
        ok_platform = upload_to_platform(path, cfg)
        if PUSH_TARGET == "platform":
            return ok_platform
        # "both": the Senvia leg still runs below, and the file only counts as
        # delivered if each configured destination accepted it. Treating a
        # half-success as success would quietly stop the retry that the failed
        # leg still needs.
        return upload_to_senvia(path, cfg) and ok_platform
    return upload_to_senvia(path, cfg)


def upload_to_senvia(path: Path, cfg: AcqConfig) -> bool:
    """POST one CSV as multipart/form-data. Returns True on success."""
    meta = {
        "sensorId": SENSOR_ID,
        "fileName": path.name,
        "acquiredAt": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
        "mqttTopic": MQTT_TOPIC,
        "ksps": cfg.ksps,
        "lor": cfg.lor,
        "fmax": cfg.fmax,
        "blockTimeSeconds": cfg.block_time_s,
        "windowType": cfg.window_type,
        "totalChannelCount": cfg.channel_count,
        "channelCount": cfg.channel_count,
    }
    # What the numbers in the CSV physically are. The PLC applies
    #     counts x (5 V / 32768) / sensitivity  ->  g
    # so the values are acceleration in g. Nothing downstream recorded this
    # before, which is why no severity zone could honestly be assigned to a
    # reading. Sensitivity is per channel because it is not uniform on this
    # hardware and the cloud config's single value is wrong for channels 1-2.
    meta.update(sample_metadata(cfg.channel_count))
    try:
        with path.open("rb") as fh:
            resp = session.post(
                PUSH_URL,
                files={"file": (path.name, fh, "text/csv")},
                data={"sensorId": SENSOR_ID,
                      "channelCount": cfg.channel_count,
                      "metadata": json.dumps(meta)},
                timeout=UPLOAD_TIMEOUT_SECONDS,
            )
        if resp.ok:
            log.info("Uploaded %s (%d bytes) -> HTTP %s",
                     path.name, path.stat().st_size, resp.status_code)
            return True
        log.error("Upload failed for %s: HTTP %s %s",
                  path.name, resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        log.error("Upload error for %s: %s", path.name, exc)
        return False


def push_cycle(cfg: AcqConfig):
    writer.flush_latest()      # materialize this interval's snapshot, if any
    files = pending_csv_files()
    if not files:
        rows, samples, msgs = writer.progress()
        log.info("Push cycle: nothing to upload (partial window: %d/%d "
                 "samples from %d message(s))", rows, samples, msgs)
        return
    log.info("Push cycle: %d file(s) pending", len(files))
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    for path in files:
        if _shutdown:
            return
        if not is_valid_csv(path):
            log.warning("Skipping invalid/empty CSV: %s", path.name)
            continue
        if upload_file(path, cfg):
            _attempts.pop(path.name, None)
            # the file is now in the cloud -> keep the same file locally
            archive_locally(path)
            try:
                shutil.move(str(path), str(SENT_DIR / path.name))
                log.info("Moved %s to sent/", path.name)
            except (OSError, shutil.Error) as exc:
                log.warning("Could not move %s to sent/: %s", path.name, exc)
        else:
            _attempts[path.name] = _attempts.get(path.name, 0) + 1
            if _attempts[path.name] >= MAX_UPLOAD_ATTEMPTS:
                log.error("Parking %s after %d failed attempts",
                          path.name, MAX_UPLOAD_ATTEMPTS)
                shutil.move(str(path), str(FAILED_DIR / path.name))
                _attempts.pop(path.name, None)


def cleanup_sent_files():
    """
    Delete files in SENT_DIR older than SENT_RETENTION_MINUTES, but only once
    their permanent copy exists in LOCAL_ARCHIVE_DIR. If the archive drive was
    unavailable at upload time the copy is retried here, so an uploaded file
    is never lost before it reaches D:\\Vibration Data.
    """
    if not SENT_DIR.is_dir():
        return
    cutoff = time.time() - SENT_RETENTION_MINUTES * 60
    for p in SENT_DIR.glob(CSV_PATTERN):
        try:
            if p.stat().st_mtime >= cutoff:
                continue
            if not archive_locally(p):
                continue                   # keep it; try again next tick
            p.unlink()
            log.info("Retention: deleted %s from sent/ (older than %d min, "
                     "archived copy kept)", p.name, SENT_RETENTION_MINUTES)
        except OSError as exc:
            log.warning("Could not delete %s: %s", p.name, exc)


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------
def main():
    log.info("Starting MQTT->Senvia snapshot uploader for sensor %s", SENSOR_ID)
    log.info("MQTT source : %s:%d topic '%s'", MQTT_BROKER, MQTT_PORT, MQTT_TOPIC)
    # Says out loud what was resolved, and warns about anything missing. Every
    # one of those warnings is a failure that is otherwise completely silent.
    report_settings(8)
    log.info("Push target : %s", PUSH_TARGET)
    log.info("Data folder : %s", WATCH_DIR.resolve())
    log.info("Local archive: %s%s", LOCAL_ARCHIVE_DIR,
             " (sub-folder per day)" if LOCAL_ARCHIVE_BY_DATE else "")
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    try:
        LOCAL_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Local archive folder %s is not available yet (%s); "
                    "uploaded files will wait in sent/ until it is.",
                    LOCAL_ARCHIVE_DIR, exc)

    cfg = fetch_config(None)
    if cfg is None:
        log.warning("Config unavailable at startup; using defaults "
                    "(%d min, lor %d).", DEFAULT_PUSH_INTERVAL_MIN, DEFAULT_LOR)
        cfg = AcqConfig({})
    writer.apply_config(cfg)

    client = start_mqtt()

    last_config_poll = time.time()
    last_push = time.time()  # first push happens one interval from startup

    while not _shutdown:
        now = time.time()

        if now - last_config_poll >= CONFIG_POLL_SECONDS:
            old_interval = cfg.push_interval_min
            cfg = fetch_config(cfg) or cfg
            last_config_poll = now
            writer.apply_config(cfg)       # live lor / channel-count changes
            if cfg.push_interval_min != old_interval:
                log.info("Push interval changed: %g -> %g min "
                         "(next push rescheduled)",
                         old_interval, cfg.push_interval_min)

        interval_s = max(cfg.push_interval_min, 0.1) * 60.0
        if now - last_push >= interval_s:
            try:
                push_cycle(cfg)
            except Exception as exc:
                log.exception("Unexpected error in push cycle: %s", exc)
            last_push = time.time()

        cleanup_sent_files()               # purge leftovers from older runs

        time.sleep(MAIN_LOOP_SECONDS)

    if client is not None:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass
    rows, samples, _ = writer.progress()
    log.info("Uploader stopped. Partial window of %d/%d sample(s) discarded.",
             rows, samples)


if __name__ == "__main__":
    main()
