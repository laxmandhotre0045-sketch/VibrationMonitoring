# sql_agent

Backend-only access to sensor measurement data, shaped for other agents to consume.

Not a service. No HTTP routes, no UI, no chat. You import it, call it, and get a
predictable envelope back. The browser-facing view of this data lives in the
SensoVibe dashboard (**Sensor Data** in the sidebar); this package is what the
*next* agents build on.

---

## Quick start

```python
from sql_agent import SensorDataAgent

agent = SensorDataAgent()
result = agent.get_sensor_data("cooling water pump")

if result.ok:
    rows = result.data                    # list[dict], one row per capture x channel x feature
    csv_text = result.meta["csv"]
    caveats = result.meta["caveats"]      # units, no_baseline, ordering - read these
else:
    handle(result.error)                  # a sentence, safe to relay to a user
```

---

## The four entry points

| Method | Returns | Use when |
|---|---|---|
| `list_sensors(filter_text="")` | every sensor with its machine, plant, area, line | building a picker, or finding what exists |
| `resolve(sensor)` | exactly one sensor, or an error naming the alternatives | you have free text and need an id |
| `get_sensor_data(sensor, ...)` | the full history, flattened | trend analysis, export, feeding a model |
| `get_latest_reading(sensor)` | the most recent capture only | a health check — one request instead of N |

`get_sensor_data` takes `from_date`, `to_date`, `max_captures`, `include_csv`
and `write_csv`.

---

## The envelope

Every method returns an `AgentResult`:

```python
AgentResult(
    ok:    bool,
    kind:  str,                 # sensor_list | sensor_resolve | sensor_data | sensor_latest
    data:  list[dict],          # the rows
    meta:  dict,                # counts, columns, caveats, csv, provenance
    error: str | None,
)
```

with `to_dict()`, `to_json()` and `summary_text()` — the last being a few lines
suitable for dropping straight into a model's context.

**Failures are values, not exceptions.** An agent mid-plan should not die because
a sensor name matched three sensors. Check `ok`; `error` is a sentence you can
relay or act on. The only thing that raises is a genuine programming error.

---

## Row shape

One row per **capture x channel x feature** — long format, not a wide sheet.
It survives new feature codes without a schema change, and loads into pandas or
a database without reshaping. Machine identity repeats on every row so a row
detached from its result still says where it came from.

27 columns, in `CSV_COLUMNS`:

```
identity   sensor_id device_id machine_id machine_name machine_type
           plant_name area line mounting_location orientation sensor_type
capture    upload_id source original_filename observed_at measured_at
           created_at rotation_speed_rpm sample_count channel_count
reading    channel feature_code feature_name value unit status computed_at
```

---

## Read these before using the numbers

`meta["caveats"]` carries these on every result. They are here too because each
one is a wrong answer that looks reasonable:

1. **Values are `scaled_eng`**, not g or mm/s. The platform never applies sensor
   sensitivity — that happens on the device. Comparing raw magnitudes *across
   machines* is meaningless. Use `crest_factor`, `status`, or a ratio against the
   sensor's own baseline.
2. **`status="no_baseline"` means not assessed**, not healthy. Counting it as
   passing is the most likely silent error.
3. **Order by `observed_at`**, which is the device capture clock where one was
   supplied and server receipt otherwise. Devices buffer across dropped links, so
   `created_at` records when the network recovered, not when the machine was
   measured.
4. **`amplitude_1x/2x/3x` rest on an estimated shaft speed** unless the capture
   carries `rotation_speed_rpm`. Treat harmonic amplitudes as provisional when
   that field is empty.

---

## How it reads the data

Through the platform's REST API, as a login holding the read-only `user` role —
not by connecting to Postgres. Two consequences worth knowing:

- The client implements `GET` plus one login `POST`. There is no method here, and
  no permission behind the credential, that could modify anything. Two independent
  barriers, so a prompt-injected instruction to delete data has nothing to call.
- It inherits the platform's own permissions rather than reimplementing them.

Configure through the environment (or `vibrationbot/.env`):

```
PLATFORM_BASE_URL=http://localhost:8000
PLATFORM_EMAIL=user@vibration.com
PLATFORM_PASSWORD=...
PLATFORM_TIMEOUT_S=30
PLATFORM_MAX_UPLOADS=200
```

---

## Command line

Everything the agent can do is reachable from a terminal. Run from the
`vibrationbot/` directory:

```bash
python -m sql_agent check                       # verify connection + login
python -m sql_agent list                        # every sensor
python -m sql_agent list pump horizontal        # narrowed
python -m sql_agent resolve "cooling water"     # text -> one sensor id
python -m sql_agent latest "cooling water pump" # newest capture only
python -m sql_agent data "cooling water pump"   # full history
python -m sql_agent data "pump" --csv out.csv --from 2026-08-01 --rows 10
python -m sql_agent --json list                 # machine-readable envelope
```

`--json` prints the raw `AgentResult`, which is what a calling agent receives.
Errors go to stderr and set exit code 1, so shell pipelines and CI behave.

If the CLI and a calling agent ever disagree, the agent is wrong -- both go
through the same `SensorDataAgent` methods, so `python -m sql_agent check`
doubles as the deployment smoke test.

---

## Dependencies

Standard library plus `python-dotenv` (optional). It deliberately does **not**
import from `app/`, so depending on it will not pull in faiss, docling or
sentence-transformers. Verify with:

```python
import sys; from sql_agent import SensorDataAgent
assert not [m for m in sys.modules if m.startswith(("app.", "faiss", "torch"))]
```

---

## Tests

```
python -m pytest sql_agent/tests -q --noconftest
```

23 tests, fully offline against a stub platform. `--noconftest` skips the
chatbot's `conftest.py`, which imports the ingestion pipeline this package does
not need.

---

## Who uses it

- `app/chat/graph/tools_platform.py` — thin LangChain wrappers for the chatbot.
  All logic lives here; that file only adapts `AgentResult` to the tool contract.
- Future diagnosis, trending and reporting agents — call the methods above.

Fixes to resolution or flattening belong **in this package**, so every consumer
stays in step.
