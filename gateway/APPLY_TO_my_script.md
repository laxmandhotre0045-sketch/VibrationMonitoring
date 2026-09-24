# Three edits to `my_script.py`

**These are already applied** in `gateway/my_script.py`. This file records what
changed and why, so the same edits can be made to your own copy on the gateway
machine. Nothing else in the script changed.

---

## 1. Replace the "Static settings" block

The one change that decides whether any data arrives at all.

**Remove:**

```python
SENSOR_ID   = "08:F9:E0:AD:FB:36"
BASE_URL    = "https://senvia.sensovibe.in/v1/vibreationDataAqUtility/sensor"
CONFIG_URL  = f"{BASE_URL}/{SENSOR_ID}"
PUSH_URL    = "https://senvia.sensovibe.in/v1/vibration-csv-trend/upload"

MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT   = 1883
MQTT_TOPIC  = "Vibration_Data"
```

**Replace with:**

```python
from uploader_settings import (
    SENSOR_ID, BASE_URL, CONFIG_URL, PUSH_URL,
    MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, MQTT_QOS,
    MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID, MQTT_KEEPALIVE,
    sample_metadata, report as report_settings,
)

report_settings(8)   # prints the resolved broker and unit; warns on anything missing
```

`MQTT_BROKER` becomes `127.0.0.1`, not `broker.hivemq.com`. The 50 kSPS PLC
project publishes to the gateway's local Mosquitto broker. Subscribed to
hivemq, the uploader connects fine, subscribes fine, and receives nothing,
indefinitely, with no error — which is the hardest kind of failure to notice.

If you would rather leave the PLC alone, the other half of the fix is to set
`sHostName` in `PrgMqttCom` back to `broker.hivemq.com`. One of the two has to
move; today they do not meet.

---

## 2. Authenticate in `start_mqtt()`

**Find:**

```python
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
```

**Replace with:**

```python
client = mqtt.Client(client_id=MQTT_CLIENT_ID)
client.on_connect = on_connect
client.on_message = on_message
if MQTT_USERNAME or MQTT_PASSWORD:
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.connect(MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE)
```

The broker does not enforce authentication today — its `mosquitto.conf` has no
`password_file` and no `acl_file`, so `allow_anonymous` applies. Sending the
credentials anyway costs nothing and means the uploader keeps working on the
day someone adds a password file, rather than going quiet.

The fixed `client_id` also matters: with the default, every reconnect gets a
new random id, and the broker cannot recognise a returning client.

---

## 3. Record what the numbers are, in `upload_file()`

**Find the `meta` dict and add one line after it:**

```python
meta = {
    "sensorId": SENSOR_ID,
    ...
}
meta.update(sample_metadata(8))   # <-- add this
```

That attaches `sampleUnit: "g"` and the per-channel `sensitivityMvPerG`.

This closes the gap that has blocked severity grading for the whole project.
The platform stores feature values under `scaled_eng` and nothing anywhere
recorded what that meant, so a velocity computed from them could be correct or
wrong by an order of magnitude, and no ISO zone could be honestly assigned to
any reading. The PLC applies

    counts × (5 V / 32768) ÷ sensitivity  →  g

so the values are acceleration in g. The uploader was the only component in the
chain that could have known this, and it was not passing it on.

Sensitivity is not uniform, and the cloud configuration gets it wrong: it
reports a single `sensitivity 100 mV/g`, while the gateway's GVL sets
**ch1 and ch2 to 0.5 V/g** and **ch3–ch8 to 0.1 V/g**. Anything derived from
channels 1 or 2 using the cloud's figure is off by a factor of five. The
per-channel list is sent so the value that reaches a report is the one that was
actually applied.

---

## Three things this patch does not fix

**Two uploader instances were running** (PIDs 2848 and 11908) when the
configuration reference was written. Neither is running now, so there is
nothing to stop on this machine — but check for duplicates on the gateway
before starting the patched script, because each one uploads and archives every
snapshot again.

**The Senvia config still says `ksps 25`** while the PLC samples at 50 kSPS. A
block sized from the config figure needs 13,888 rows, not 6,944 — so blocks are
currently half the intended duration. Fixing this is a cloud-side config
change, not a script change.

**Timestamps are per-message, not per-sample.** All 2,500 samples in a message
share one timestamp. At 50 kSPS they are 20 µs apart, so any analysis reading
the timestamp column as a real time base sees 2,500 simultaneous samples.
Deriving sample times from the message timestamp plus `index / 50000` would fix
it, but that changes the CSV contract with the platform and should be agreed
first.

Separately, `_derive_total_rows()` is an algebraic no-op: it computes
`msg_rows × (samples // msg_rows)`, which is just `samples`. Harmless, but it
is not doing what its name claims.
