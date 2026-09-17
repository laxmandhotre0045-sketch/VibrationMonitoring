"""Settings for the gateway CSV uploader, read from the environment.

Drop this beside ``my_script.py`` and replace the module's "Static settings"
block with::

    from uploader_settings import (
        SENSOR_ID, BASE_URL, CONFIG_URL, PUSH_URL,
        MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, MQTT_QOS,
        MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID, MQTT_KEEPALIVE,
        SAMPLE_UNIT, SENSITIVITY_MV_PER_G, sample_metadata,
    )

Values come from a ``.env`` file beside this one, with the documented gateway
settings as fallbacks. Nothing here is a secret in itself -- the local broker
accepts anonymous connections -- but the credentials live outside the source
because this project has already published one credentials file to GitHub by
committing a file nobody had marked as sensitive.

Reference: SRPL/CFG/2026-27/001, Gateway Configuration Reference 50 kSPS.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file(path: Path) -> None:
    """Minimal .env reader, so the uploader needs no extra dependency."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Existing environment wins, so a service definition can override the
        # file without editing it.
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(_ENV_FILE)


def _get(name: str, default: str) -> str:
    value = os.environ.get(name, "")
    return value.strip() or default


# --------------------------------------------------------------------------
# Sensor and cloud endpoints
# --------------------------------------------------------------------------

#: The gateway MAC. Device identity rather than a secret, but it lives in .env
#: with everything else so that one file describes one gateway and this module
#: describes none.
SENSOR_ID = _get("SENSOR_ID", "")

#: Overridable so the uploader can be pointed at a local sink for testing.
#: Production is the default, so forgetting to set these cannot silently stop
#: real data reaching the cloud -- only deliberately setting them diverts it.
_API_ROOT = _get("SENVIA_API_ROOT", "https://senvia.sensovibe.in")

BASE_URL = f"{_API_ROOT}/v1/vibreationDataAqUtility/sensor"
CONFIG_URL = f"{BASE_URL}/{SENSOR_ID}"
PUSH_URL = f"{_API_ROOT}/v1/vibration-csv-trend/upload"

#: True when uploads are going somewhere other than the real platform. The
#: uploader says so at startup, because a test run that quietly looks like a
#: production run is how fabricated data ends up in a real trend database.
IS_TEST_TARGET = "senvia.sensovibe.in" not in _API_ROOT


# --------------------------------------------------------------------------
# MQTT source
# --------------------------------------------------------------------------
#
# THE CHANGE THAT MATTERS. The 50 kSPS PLC project publishes to the local
# Mosquitto broker on 127.0.0.1; the uploader was subscribing to
# broker.hivemq.com, which the 25 kSPS project used. After the 50 kSPS project
# is activated, those two do not meet: the uploader connects successfully,
# subscribes successfully, and receives nothing, forever, with no error.
#
# A silent no-op is the worst shape a misconfiguration can take, so the broker
# is named here explicitly rather than left as a default.

MQTT_BROKER = _get("MQTT_BROKER", "127.0.0.1")
MQTT_PORT = int(_get("MQTT_PORT", "1883"))
MQTT_TOPIC = _get("MQTT_TOPIC", "Vibration_Data")
MQTT_QOS = int(_get("MQTT_QOS", "1"))
MQTT_KEEPALIVE = int(_get("MQTT_KEEPALIVE", "60"))
MQTT_CLIENT_ID = _get(
    "MQTT_CLIENT_ID", f"senvia-uploader-{SENSOR_ID.replace(':', '')}"
)

#: No fallback on purpose. This file is tracked in git; the broker password is
#: not, and a default here would put it back into source, which is how the last
#: credentials leak in this project happened. Unset means "connect anonymously"
#: -- which the gateway's mosquitto.conf currently permits, since it has no
#: password_file and no acl_file.
#: The gateway publishes to two brokers: plain TCP to Mosquitto on the machine
#: itself, and WebSocket-over-TLS to the cloud. Same payload, same topic, two
#: transports -- so the transport is configuration, not a second code path.
MQTT_TRANSPORT = _get("MQTT_TRANSPORT", "tcp").lower()   # "tcp" or "websockets"
MQTT_WS_PATH = _get("MQTT_WS_PATH", "/mqtt")
MQTT_TLS = _get("MQTT_TLS", "").lower() in ("1", "true", "yes", "on")

MQTT_USERNAME = _get("MQTT_USERNAME", "")
MQTT_PASSWORD = _get("MQTT_PASSWORD", "")


# --------------------------------------------------------------------------
# What the stored numbers physically are
# --------------------------------------------------------------------------
#
# This is the gap that has blocked severity grading for the whole project. The
# platform stores feature values in "scaled_eng" and nothing records what that
# means, so a velocity derived from them could be right or ten times wrong, and
# no ISO zone can honestly be assigned.
#
# The gateway settles it. The PLC applies
#
#       counts x (5 V / 32768) / sensitivity  ->  g
#
# so the published values are ACCELERATION IN g. The uploader is the only place
# in the chain that knows this, and it was not passing it on.
#
# Sensitivity is not uniform, which the cloud configuration gets wrong: it
# reports a single "sensitivity 100 mV/g", while the gateway's GVL sets
# ch1 and ch2 to 0.5 V/g and ch3..ch8 to 0.1 V/g. Carried per channel here so
# the figure that reaches a report is the one that was actually applied.

# --------------------------------------------------------------------------
# Where snapshots are sent
# --------------------------------------------------------------------------
#
# "senvia"   - the Senvia cloud, the original behaviour and still the default
# "platform" - this VibrationMonitoring instance's own ingest API
# "both"     - send to each; a failure on either is reported separately
#
# Two destinations rather than one because they answer different questions.
# The gateway machine already uploads to Senvia; a second uploader doing the
# same only duplicates rows. Feeding this platform is what puts the readings on
# the dashboard, and that is a different job from keeping the cloud trend fed.
PUSH_TARGET = _get("PUSH_TARGET", "senvia").lower()

PLATFORM_API_URL = _get("PLATFORM_API_URL", "http://localhost:8000")


SAMPLE_UNIT = _get("SAMPLE_UNIT", "g")

#: Empty, not a guess. A wrong sensitivity does not fail loudly -- it produces a
#: plausible number that is wrong by a factor of five on channels 1 and 2, and
#: an ISO zone assigned from it would read as authoritative.
_DEFAULT_SENSITIVITY = ""


def _sensitivity_list() -> list[float]:
    raw = _get("SENSITIVITY_MV_PER_G", _DEFAULT_SENSITIVITY)
    out: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(float(part))
        except ValueError:
            # A malformed entry must not be read as a real sensitivity: a wrong
            # one is a silently wrong severity assessment later.
            return []
    return out


SENSITIVITY_MV_PER_G = _sensitivity_list()


def sample_metadata(channel_count: int) -> dict:
    """The unit facts to attach to every upload.

    Returned as a dict to merge into the uploader's existing ``meta``. Only
    what is actually known is included: if the per-channel sensitivities do not
    match the channel count, the list is omitted rather than padded, because a
    guessed sensitivity produces a plausible wrong answer downstream, which is
    worse than a missing one.
    """
    meta: dict = {"sampleUnit": SAMPLE_UNIT}
    if SENSITIVITY_MV_PER_G and len(SENSITIVITY_MV_PER_G) == channel_count:
        meta["sensitivityMvPerG"] = SENSITIVITY_MV_PER_G
        distinct = sorted(set(SENSITIVITY_MV_PER_G))
        if len(distinct) == 1:
            meta["sensitivityUniform"] = True
        else:
            # Flagged, because the cloud configuration reports one value for
            # all channels and that is not what the gateway applies.
            meta["sensitivityUniform"] = False
            meta["sensitivityNote"] = (
                "Sensitivity differs by channel on this gateway "
                f"({', '.join(f'{v:g}' for v in SENSITIVITY_MV_PER_G)} mV/g). "
                "The cloud configuration's single value does not describe "
                "channels 1 and 2."
            )
    elif SENSITIVITY_MV_PER_G:
        meta["sensitivityNote"] = (
            f"{len(SENSITIVITY_MV_PER_G)} sensitivities configured for "
            f"{channel_count} channels; omitted rather than guessed."
        )
    return meta


def check(channel_count: int = 8) -> list[str]:
    """Return the problems worth printing at startup, worst first.

    Every item here is a failure that is otherwise silent. The uploader has no
    way to notice any of them at runtime: an empty topic still subscribes, a
    missing sensitivity still uploads, a wrong broker still connects. They only
    surface days later as a gap in the trend or a severity that was never
    right, so they are said out loud once, at the start, where someone is
    watching.
    """
    problems: list[str] = []

    if not SENSOR_ID:
        problems.append(
            "SENSOR_ID is not set. The uploader cannot fetch its configuration "
            f"or attribute readings to a machine. Set it in {_ENV_FILE}."
        )
    if not MQTT_USERNAME and not MQTT_PASSWORD:
        problems.append(
            "No MQTT credentials set; connecting anonymously. The gateway's "
            "broker permits this today. If a password file is ever added, the "
            "uploader will stop receiving data with no visible error."
        )
    if not SENSITIVITY_MV_PER_G:
        problems.append(
            "SENSITIVITY_MV_PER_G is not set, so uploads carry no sensitivity. "
            "Values are still in g and still usable as a trend, but no "
            "severity zone can be assigned from them."
        )
    elif len(SENSITIVITY_MV_PER_G) != channel_count:
        problems.append(
            f"SENSITIVITY_MV_PER_G lists {len(SENSITIVITY_MV_PER_G)} channels "
            f"but {channel_count} are being uploaded; it will be omitted "
            "rather than guessed."
        )
    return problems


def report(channel_count: int = 8) -> None:
    """Print the resolved source and any problems. Never raises, never exits:
    a degraded upload is better than none, provided the degradation is stated.
    """
    print(
        f"[settings] MQTT {MQTT_BROKER}:{MQTT_PORT} topic={MQTT_TOPIC!r} "
        f"qos={MQTT_QOS} auth={'yes' if MQTT_USERNAME else 'anonymous'}"
    )
    print(
        f"[settings] samples are {SAMPLE_UNIT}, sensitivity "
        + (
            f"{', '.join(f'{v:g}' for v in SENSITIVITY_MV_PER_G)} mV/g"
            if SENSITIVITY_MV_PER_G
            else "UNKNOWN"
        )
    )
    if IS_TEST_TARGET:
        print(f"[settings] *** TEST TARGET: uploads go to {_API_ROOT}, "
              f"NOT the Senvia platform ***")
    for problem in check(channel_count):
        print(f"[settings] WARNING: {problem}")


if __name__ == "__main__":
    report()
