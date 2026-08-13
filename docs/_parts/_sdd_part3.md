---

# 4.0 Backend Documentation

## 4.1 Folder Structure and Layering

```
backend/app/
├── config.py        ← settings (env-bound)
├── database.py      ← engine / session / Base / get_db
├── main.py          ← application assembly
├── dependencies/    ← FastAPI Depends providers (auth)
├── models/          ← SQLAlchemy ORM (persistence shape)
├── schemas/         ← Pydantic (wire shape)
├── crud/            ← data access (no HTTP, no business rules)
├── routers/         ← HTTP endpoints (no SQL, no DSP)
└── services/        ← business logic and algorithms
```

Dependency direction is strictly downward: `routers → services → crud → models`. `schemas` is imported by routers and services; `crud` never imports `routers`; `services` never raise `HTTPException` (they raise `ValueError`, which routers translate).

## 4.2 Application Startup — `app/main.py`

| Element | Detail |
|---------|--------|
| `lifespan` | Async context manager. Opens a `SessionLocal`, calls `seed_super_admin(db)` then `seed_role_users(db)`, closes the session in `finally`, then `yield`s. No shutdown logic. |
| `FastAPI(...)` | `title="AI Vibration Intelligence Platform"`, `version="1.1.0"`, and a Markdown `description` containing Swagger login instructions and a table of the three dev accounts |
| `CORSMiddleware` | 6 allowed origins, all methods, all headers, credentials enabled |
| `include_router` | `auth`, `baselines`, `equipment`, `lookups`, `measurements` |
| Directory creation | `os.makedirs(settings.upload_dir)` and `os.makedirs(settings.measurement_upload_dir)` at import time |
| `custom_openapi()` | Post-processes the generated schema |
| `GET /health` | Returns `{"status": "ok", "service": "AI Vibration Intelligence Platform"}`; unauthenticated |

### 4.2.1 `custom_openapi()` in detail

```mermaid
flowchart TD
    A[custom_openapi called] --> B{app.openapi_schema cached?}
    B -->|yes| C[return cache]
    B -->|no| D[get_openapi title/version/description/routes]
    D --> E["Add securitySchemes.BearerAuth<br/>type=http, scheme=bearer, bearerFormat=JWT"]
    E --> F["Add securitySchemes.OAuth2Password<br/>password flow, tokenUrl=/api/v1/auth/token"]
    F --> G[For each path]
    G --> H{path == /health?}
    H -->|yes| G
    H -->|no| I{path startswith /api/v1/?}
    I -->|no| G
    I -->|yes| J{POST and in public set<br/>login, token, refresh, logout?}
    J -->|yes| G
    J -->|no| K["operation.security = [{BearerAuth: []}]"]
    K --> G
    G --> L[cache and return]
```

The effect is that Swagger UI shows a padlock on every protected operation and lets a developer authorise once with a pasted access token.

## 4.3 Configuration — `app/config.py`

```python
class Settings(BaseSettings):
    database_url: str                      # REQUIRED — no default
    secret_key: str = "change-in-production"
    upload_dir: str = "uploads"
    measurement_upload_dir: str = "uploads/measurements"
    max_image_size_mb: int = 10
    max_pdf_size_mb: int = 50
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    initial_admin_email/password/name
    seed_admin_email/password/name
    seed_user_email/password/name
    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self.secret_key
    class Config:
        env_file = ".env"
        extra = "ignore"
```

| Design point | Consequence |
|--------------|-------------|
| `database_url` has no default | The process refuses to start without it — a fail-fast guard against silently connecting to the wrong database |
| `effective_jwt_secret` | `JWT_SECRET` can be rotated independently of `SECRET_KEY`; if unset, `SECRET_KEY` is used |
| `extra = "ignore"` | The shared root `.env` contains Postgres/pgAdmin/Vite keys that are not `Settings` fields; ignoring extras prevents startup failure |
| `env_file = ".env"` | Read relative to the process CWD — hence `copy ..\.env .env` in `START.md` and `setup_and_run.bat` |
| Environment variables win over the file | Docker Compose passes `DATABASE_URL`, `SECRET_KEY`, `UPLOAD_DIR=/app/uploads`, `JWT_SECRET`, and the six seed variables explicitly |

## 4.4 Database Access — `app/database.py`

```python
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

| Choice | Reason |
|--------|--------|
| `pool_pre_ping=True` | Issues a lightweight `SELECT 1` before handing out a pooled connection, which prevents "server closed the connection unexpectedly" after idle periods or a Postgres restart |
| `autocommit=False` | Explicit transaction boundaries; every CRUD write calls `db.commit()` |
| `autoflush=False` | Prevents surprise flushes mid-query; the code flushes explicitly with `db.flush()` where an ID is needed before commit (e.g. `create_equipment`, `create_user`) |
| Generator dependency | FastAPI guarantees the `finally` block runs after the response is produced, so sessions are always returned to the pool |

**No global exception handler exists**, so an uncaught exception rolls back implicitly on session close and returns a FastAPI 500.

## 4.5 Dependencies — `app/dependencies/auth.py`

| Symbol | Type | Behaviour |
|--------|------|-----------|
| `WRITE_ROLES` | `{"super_admin", "admin"}` | Roles permitted to mutate data |
| `bearer_scheme` | `HTTPBearer(auto_error=False)` | `auto_error=False` lets the code emit its own 401 body and `WWW-Authenticate` header |
| `_user_role(user)` | `str` | Prefers `user.role`; otherwise derives from the `roles` relationship, mapping `super_admin` → `super_admin`, any of `admin`/`plant_admin`/`engineer` → `admin`, else `user` |
| `get_current_user(credentials, db)` | `User` | 401 when: no credentials, non-bearer scheme, decode failure, bad `sub`, user missing, `is_active == False` |
| `require_write_access(current_user)` | `User` | 403 `"Insufficient permissions"` when `_user_role(...)` is not in `WRITE_ROLES` |

`require_write_access` depends on `get_current_user`, so listing it in a route's `dependencies=[...]` implies authentication as well.

## 4.6 Models — `app/models/`

`models/__init__.py` re-exports every model class. `alembic/env.py` imports `app.models` precisely so that `Base.metadata` is fully populated for autogenerate and `target_metadata` comparison.

### 4.6.1 `Equipment` (`equipment_masters`)

| Group | Columns |
|-------|---------|
| Identity | `id` UUID PK (default `uuid.uuid4`) |
| Location | `plant_name`, `area`, `line` — all `String(255) NOT NULL` |
| Asset | `machine_name` (255, NOT NULL), `machine_id` (100, nullable, **unique**, indexed), `machine_type` (50, NOT NULL), `machine_criticality` (20, NOT NULL), `manufacturer`, `model`, `serial_number` |
| Mechanical | `rated_power_kw` Numeric(10,2), `rated_rpm` Integer, `drive_type`, `load_type`, `foundation_type`, `coupling_details` |
| Rotating | `bearing_details` Text, `bearing_number_de/nde`, `gearbox_ratio` Numeric(8,3), `gear_teeth`, `motor_pole_count`, `fan_blades`, `pump_vanes`, `direction_of_rotation` |
| Operating | `operating_speed_min/max`, `load_range_min/max` Numeric(5,2), `normal_operating_load` Numeric(5,2), `process_details` Text, `operating_environment` `ARRAY(String)` |
| Lubrication | `lubrication_type`, `installation_date` Date, `last_maintenance_date` Date, `maintenance_notes` Text |
| Image | `equipment_image_path` String(500) |
| AI readiness | `asset_status` (default `"Active"`), `machine_train_configured`, `bearing_database_mapped`, `operating_mode_configured` — Booleans defaulting to `False` |
| Timestamps | `created_at`, `updated_at` (`onupdate=datetime.utcnow`) |
| Relationship | `sensors` → `SensorConfiguration`, `cascade="all, delete-orphan"` |

### 4.6.2 `SensorConfiguration` (`sensor_configurations`)

`id`, `equipment_id` (FK CASCADE, NOT NULL), `sensor_type` (NOT NULL), `mounting_location` (NOT NULL), `orientation` (NOT NULL), `mounting_method`, `sensitivity` Numeric(10,4), `sensitivity_unit`, `sampling_rate` (string label), `sampling_rate_custom` Integer, `frequency_range`, `frequency_range_custom_min/max`, `is_active` (default `True`), `device_id` String(64) **unique + indexed**, `created_at`. Back-reference `equipment`.

`device_id` is the join key for the edge acquisition API and is deliberately a free-form MAC-style string rather than a UUID.

### 4.6.3 Measurement models (`models/measurement.py`)

| Model | Table | Purpose | Notable columns |
|-------|-------|---------|-----------------|
| `PlotConfiguration` | `plot_configurations` | One processing profile per sensor | `sensor_id` **unique**, `channel_count`, `active_channel`, `sampling_rate_hz` Numeric(12,4) default 25600, `fft_lines` default 1600, `frequency_max_hz`, `data_type` default `acceleration`, `enabled_plots` JSONB |
| `SensorDataUpload` | `sensor_data_uploads` | Upload lifecycle record | `pdf_path`, `parsed_data_path`, `sample_count`, three status triplets (`parse_*`, `plots_*`, `features_*`), `original_filename`, `source` (default `manual`), `created_at`, `parsed_at` |
| `PlotResult` | `plot_results` | Cached plot series | `plot_type`, `channel`, `title`, `x_label`, `y_label`, `x_data`/`y_data` JSONB, `metadata_` mapped to column `metadata`, `point_count`, `sampling_rate_hz`, `fft_lines`, `frequency_max_hz`, `config_fingerprint`, `status` |
| `MeasurementUploadData` | `measurement_upload_data` | Durable copy of the file | `upload_id` **unique**, `file_content` `LargeBinary`, `parsed_data` JSONB, `file_format`, `channel_count`, `sample_count` |
| `SensorBaseline` | `sensor_baselines` | Append-only reference captures | `source_upload_id` (FK **SET NULL**), `name`, `description`, `labels` JSONB, `file_content`, `parsed_data`, `sampling_rate_hz`, `is_primary`, `captured_at` |
| `BaselinePlotResult` | `baseline_plot_results` | Cached baseline plots | Same shape as `PlotResult`, keyed by `baseline_id` |
| `FeatureDefinition` | `feature_definitions` | Feature catalogue | `code` **unique**, `name`, `unit`, `description`, `sort_order`, `is_active` |
| `FeatureThresholdRule` | `feature_threshold_rules` | Evaluation rules | `feature_code` FK, `rule_type`, `machine_type` (nullable = global), `normal_max`, `warning_max`, `normal_min`, `warning_min`, `metadata_`, `is_active` |
| `MeasurementChannelFeature` | `measurement_channel_features` | Scalar feature values | `upload_id`, `sensor_id`, `channel`, `feature_code`, `value` Numeric(18,8), `unit`, `status`, `metadata_`, `computed_at` |
| `MeasurementChannelFeatureTrend` | `measurement_channel_feature_trends` | Per-segment series | Adds `segment_index`, `time_s` |
| `BaselineChannelFeature` | `baseline_channel_features` | Baseline feature values | Same as measurement features but keyed by `baseline_id`; `status` defaults to `normal` |

**The `metadata_` naming pattern.** `metadata` is reserved on SQLAlchemy declarative classes, so the attribute is named `metadata_` and explicitly mapped: `Column("metadata", JSONB, ...)`. Pydantic response models expose it back as `metadata`.

### 4.6.4 User models (`models/user.py`)

| Model | Table | Columns |
|-------|-------|---------|
| `Role` | `roles` | `id`, `name` (unique, indexed), `description`, `created_at` |
| `User` | `users` | `id`, `email` (unique, indexed), `password_hash`, `full_name`, `role` (String(50), default `"user"`), `is_active`, `must_change_password`, `last_login_at`, `created_at`, `updated_at` |
| `UserRole` | `user_roles` | Composite PK `(user_id, role_id)`, `assigned_at` |
| `RefreshToken` | `refresh_tokens` | `id`, `user_id` (indexed), `token_hash` (String(64), unique, indexed), `expires_at`, `revoked_at`, `created_at` |

`User.roles` is a many-to-many via `secondary="user_roles"`. The scalar `users.role` column (added in migration 008) is the **authoritative** value used by `_user_role`, `create_access_token`, and `user_to_me_dict`; the M2M table is the legacy path retained for backwards compatibility.

## 4.7 Schemas — `app/schemas/`

### 4.7.1 `schemas/equipment.py`

* `SensorConfigBase` — all sensor fields; `device_id` carries `max_length=64` and a description.
* `SensorConfigCreate` — inherits base unchanged.
* `SensorConfigUpdate` — every field `Optional` for PATCH semantics.
* `SensorConfigOut` — adds `id`, `equipment_id`, `created_at`; `from_attributes = True`.
* `EquipmentBase` — 40 fields. Location and asset identity default to `""` rather than being required, which lets the frontend save partial drafts. Contains one validator:
  ```python
  @field_validator("machine_id", mode="before")
  def normalize_machine_id(cls, v): return None if v == "" else v
  ```
  This converts an empty string to `NULL`, which is essential because `machine_id` is `UNIQUE` — many empty strings would collide, many `NULL`s do not.
* `EquipmentCreate` — adds `sensors: Optional[List[SensorConfigCreate]] = []`.
* `EquipmentUpdate` — 36 optional fields; used with `model_dump(exclude_unset=True)` so omitted keys are untouched.
* `EquipmentOut`, `EquipmentListItem`, `AIReadinessOut`, `PaginatedEquipment`.

### 4.7.2 `schemas/measurement.py`

```python
PLOT_TYPES = ["time_waveform","circular_time_waveform","fft_spectrum","envelope_spectrum","trend_plot"]
PLOT_TYPE_ALIASES = {"psd": "circular_time_waveform", "rms_trend": "trend_plot"}
DATA_TYPES = ["acceleration","velocity","displacement"]
```

`PlotConfigBase` constraints: `channel_count` 1–32, `active_channel ≥ 0`, `sampling_rate_hz > 0`, `fft_lines` 64–65536, `frequency_max_hz > 0`.

Four validators:
1. `validate_data_type` — membership in `DATA_TYPES`.
2. `validate_plots` — canonicalises aliases, drops unknowns, de-duplicates, and rejects an empty result.
3. `PlotConfigCreate.validate_channel_index` (model validator) — `active_channel < channel_count`.
4. `PlotConfigOut.normalize_plots_on_read` + `clamp_channel_on_read` — repairs legacy rows on read: unknown plot types are dropped, an empty list becomes all five types, and an out-of-range `active_channel` is clamped to `channel_count − 1` using `object.__setattr__`.

`SensorDataUploadOut` carries a non-persisted `has_stored_data: bool` that routers populate from a `measurement_upload_data` existence check.

### 4.7.3 `schemas/feature.py`

Eight models: `ChannelFeatureOut`, `FeaturesSummaryOut`, `ChannelHealthOverviewOut`, `UploadFeaturesOut`, `FactorTrendSeriesOut`, `UploadFactorTrendsOut`, `BaselineFeaturesOut`, `FeatureCompareItemOut`, `FeatureCompareOut`.

### 4.7.4 `schemas/auth.py`, `schemas/baseline.py`, `schemas/acquisition.py`

* `LoginRequest` uses `EmailStr` (so a malformed email returns 422 before any DB access) and `password: str = Field(min_length=1)`.
* `TokenResponse` — `access_token`, `refresh_token`, `token_type="bearer"`, `expires_in` (seconds).
* `UserMeResponse` — includes `roles: List[str]` and `plants: List[str]`.
* `BaselineOut` adds two computed fields, `plot_count` and `plots_status`, filled by the router helper.
* `EdgeAcquisitionConfigOut` mirrors the Sensovibe edge JSON contract exactly, including camelCase field names (`acquisitionFormula`, `totalChannelCount`, `windowType`, `overlapPercentage`) and the `platformSensorId` field documented as *"Internal UUID — use for upload API until device_id upload is added"*.

## 4.8 CRUD Layer — `app/crud/`

### 4.8.1 `crud/equipment.py`

| Function | Behaviour |
|----------|-----------|
| `get_equipment_list(db, page, page_size, plant_name, machine_type, machine_criticality)` | `plant_name` uses `ILIKE %value%`; type and criticality use equality; returns `(total, items)` with `ORDER BY created_at DESC` and offset/limit |
| `get_equipment_by_id`, `get_equipment_by_machine_id` | Single-row lookups |
| `create_equipment(db, data)` | `model_dump(exclude={"sensors"})` → `Equipment`; `db.flush()` to obtain the id; inserts each nested sensor; single `commit` |
| `update_equipment(db, id, data)` | `model_dump(exclude_unset=True)` then `setattr` per field |
| `delete_equipment` | `db.delete` → ORM cascade removes sensors, and DB `ON DELETE CASCADE` removes all descendants |
| `update_image_path(db, id, path)` | Sets `equipment_image_path` (also used with `None` to clear) |
| `get_sensors_by_equipment`, `get_sensor_by_id`, `get_sensor_by_device_id`, `create_sensor`, `update_sensor`, `delete_sensor` | Sensor CRUD |
| `compute_ai_readiness(equipment)` | Five boolean checks → `score = int(sum(checks)/len(checks)*100)` |

The five readiness checks are: `machine_train_configured`, `asset_status not in (None, "")`, `len(sensors) > 0`, `bearing_database_mapped`, and `operating_speed_min is not None and operating_speed_max is not None`. Each is worth 20 %.

### 4.8.2 `crud/measurement.py`

Plot-config functions (`get_plot_config_by_sensor`, `create_plot_config` — which raises `ValueError` if one already exists — `update_plot_config`, `upsert_plot_config`), upload-lifecycle functions (`create_upload_record`, `mark_upload_parsed`, `mark_upload_failed`, `mark_upload_plots_ready`, `mark_upload_plots_failed`, `get_upload_by_id`), listing (`list_uploads_by_sensor` with date/status filters and pagination, `get_stored_upload_ids`), and plot-result access (`get_plot_results`, `delete_plot_results`).

Date filtering uses `_date_start(d) = datetime.combine(d, time.min)` and `_date_end(d) = datetime.combine(d, time.max)` so a single-day range is inclusive of the whole day.

`config_to_dict` converts a `PlotConfiguration` row into the plain dict the services expect; `default_config_dict(channel_count)` supplies `{channel_count, active_channel: 0, sampling_rate_hz: 25600.0, fft_lines: 1600, frequency_max_hz: None, data_type: "acceleration", enabled_plots: PLOT_TYPES}` when no configuration row exists.

### 4.8.3 `crud/baseline.py`

`save_upload_data`, `get_upload_data_by_upload_id`, `create_baseline` (clears the previous primary flag first when `set_as_primary`), `get_baseline_by_id`, `list_baselines_by_sensor` (newest first), `get_primary_baseline`, `set_baseline_primary`, `delete_baseline_plot_results`, `count_baseline_plot_results` (only `status == "ready"`), `get_baseline_plot_results`.

### 4.8.4 `crud/feature.py`

`get_active_threshold_rules(db, machine_type)` implements a **specific-then-global** lookup: if a `machine_type` is supplied and machine-specific active rules exist, they are returned; otherwise the rules with `machine_type IS NULL` are returned. (The current caller passes no machine type, so the global set is always used.)

Also: `get_feature_definitions` (active, ordered by `sort_order`), `get_definition_map`, `delete_measurement_features`, `delete_measurement_feature_trends`, `get_measurement_features`, `get_measurement_feature_trends`, `delete_baseline_features`, `get_baseline_features`, `mark_upload_features_ready`, `mark_upload_features_failed`.

### 4.8.5 `crud/user.py`

`SUPPORTED_ROLES = ["super_admin","admin","user"]`. `primary_role(role_names)` collapses a role list to one canonical role. `get_user_by_email` **lowercases** the input before comparison, and `create_user` lowercases on write — so email is effectively case-insensitive. All user reads use `joinedload(User.roles)` to avoid N+1 queries. Token functions: `create_refresh_token_record`, `get_refresh_token_by_hash` (with a nested `joinedload` down to `User.roles`), `revoke_refresh_token`, `revoke_all_user_refresh_tokens`, `super_admin_exists`.

## 4.9 Services — `app/services/`

### 4.9.1 `auth_service.py`

| Function | Detail |
|----------|--------|
| `pwd_context` | `CryptContext(schemes=["bcrypt"], deprecated="auto")` |
| `hash_password(p)` / `verify_password(p, h)` | bcrypt via passlib |
| `create_access_token(user_id, roles)` | Payload `{sub, exp, type:"access", roles}`; HS256; returns `(token, expires_in_seconds)` |
| `decode_access_token(token)` | Verifies the signature and `exp`, then rejects any token whose `type != "access"` |
| `_hash_refresh_token(t)` | `hashlib.sha256(t.encode()).hexdigest()` — 64 hex chars, matching `String(64)` |
| `create_refresh_token(db, user_id)` | `secrets.token_urlsafe(48)` (≈64 chars, 384 bits of entropy); stores only the hash |
| `validate_refresh_token(db, plain)` | Raises `ValueError` for: unknown hash, revoked, expired (naive datetimes are coerced to UTC), inactive user |
| `authenticate_user(db, email, password)` | Returns `None` for unknown user, inactive user, or wrong password — the caller emits one generic 401 so the three cases are indistinguishable to an attacker |
| `user_to_me_dict(user)` | Prefers the scalar `user.role`; falls back to the M2M names or `["user"]`; `plants` is always `[]` |

### 4.9.2 `seed.py`

`seed_super_admin(db)`:
* If a super admin already exists, it additionally clears a stale `must_change_password` flag on the configured `INITIAL_ADMIN_EMAIL` account (a legacy-data repair) and returns.
* Otherwise, if both `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD` are set, it creates the account with `role_names=["super_admin"]` and `must_change_password=False`; if not, it logs a warning and does nothing.

`seed_role_users(db)` calls `_seed_user_if_missing` twice, for `SEED_ADMIN_*` (role `admin`) and `SEED_USER_*` (role `user`). Both are no-ops when the env values are blank or the email already exists. The whole routine is therefore idempotent and safe on every restart.

### 4.9.3 `pdf_parser.py`

Supported inputs (from the module docstring): `timestamp_,ch0,ch1,...` (Excel export), `timestamp,ch0,ch1,...`, and tab- or space-separated rows with epoch or float timestamps.

| Function | Behaviour |
|----------|-----------|
| `_clean_cell(v)` | Strips whitespace, `"`, `'`, and the BOM `﻿` |
| `_split_line(line)` | Delimiter precedence: tab → semicolon (only when no comma) → comma → any whitespace run |
| `_is_timestamp_header(cell)` | Normalised membership in `{timestamp,time,t,index,sample,datetime,date}` or any cell starting with `timestamp` |
| `_is_header_row(parts)` | True when the first cell is a timestamp header **or** any later cell matches `^ch(\d+)$` (case-insensitive) |
| `_detect_channel_count_from_header/_text` | Counts `chN` columns |
| `_parse_numeric_row(parts, n)` | `float()` the timestamp and the first `n` values; pads short rows with `0.0`; returns `None` on `ValueError`/`IndexError` |
| `parse_measurement_text(text, channel_count)` | Detects the effective channel count (header wins over the argument), iterates lines, skips blanks/headers/unparseable rows, and appends `0.0` for missing channels. Raises `ValueError` with a diagnostic message when no row parsed |
| `parse_sensor_pdf(path, n)` | `pdfplumber`: prefers `page.extract_tables()` (Excel→PDF preserves table structure) and joins cells with commas; falls back to `page.extract_text()`. Raises if nothing extractable |
| `parse_sensor_csv(path, n)` | Tries encodings `utf-8-sig`, `utf-8`, `latin-1` in order |
| `parse_sensor_file(path, n)` | Dispatches on extension; raises for anything other than `.csv`/`.pdf` |
| `parse_pdf_text` | Backwards-compatible alias of `parse_measurement_text` |

### 4.9.4 `signal_processing.py`

**`resolve_time_seconds(timestamps, fs)`** — the timestamp heuristic, applied in order:

```mermaid
flowchart TD
    A[timestamps array, length n] --> B{n == 0}
    B -->|yes| C[return as-is]
    B -->|no| D{n == 1}
    D -->|yes| E[return index time i/fs]
    D -->|no| F{span == 0 or std < 1e-12}
    F -->|yes| E
    F -->|no| G{max > 1e9 → epoch?}
    G -->|yes| H[rel = ts − ts0; if max > 1e12 divide by 1000]
    H --> I{rel_last < expected_span × 0.01}
    I -->|yes| E
    I -->|no| J[return rel]
    G -->|no| K[return ts − ts0]
```

The `× 0.01` test catches the common case where every row in a batch shares one epoch second: the apparent span is far smaller than `(n−1)/fs`, so index-derived time is used instead.

| Function | Output |
|----------|--------|
| `compute_time_waveform(ts, samples, fs)` | `{x: resolved time (s), y: samples, x_label:"Time (s)", y_label:"Amplitude", title:"Time Waveform", metadata:{plot_style:"line"}}` |
| `compute_circular_time_waveform(ts, samples, max_points=2048)` | Decimates by striding, then maps `θ = linspace(0, 2π, n, endpoint=False)`, `x = A·cos θ`, `y = A·sin θ`. Requires ≥4 samples |
| `compute_fft_spectrum(samples, fs, fft_lines, frequency_max_hz)` | Truncates to `min(fft_lines, n)`, applies a **Hann window** (`np.hanning`), computes `abs(fft(windowed))[:n//2] × 2/n` (single-sided amplitude scaling), builds `fftfreq(n, 1/fs)[:n//2]`, optionally masks to `frequency_max_hz`. Metadata records `fft_lines` and `sampling_rate_hz` |
| `compute_envelope_spectrum(...)` | Hilbert transform → `abs(analytic)` → subtract the mean (removes the DC pedestal) → FFT of the envelope. Retitled "Envelope Spectrum", y-label "Envelope Magnitude" |
| `compute_trend_plot(ts, samples, fs, num_segments=32)` | Splits into 32 equal segments, computes RMS per segment, and places each point at the segment mid-time |

### 4.9.5 `plot_generator.py`

`PLOT_COMPUTERS` is a dict of five lambdas mapping a plot type to its signal-processing call with the right configuration arguments — the registry that makes adding a sixth plot type a one-line change.

| Function | Behaviour |
|----------|-----------|
| `normalize_plot_types(enabled)` | Canonicalises aliases, filters to known computers, de-duplicates, falls back to all five |
| `load_parsed_data(path)` / `save_parsed_data(path, data)` | JSON I/O; `save` creates parent directories |
| `resolve_active_channel(parsed, requested)` | Returns the requested channel if it exists in the parsed data, else the lowest available channel, else 0 |
| `generate_plot(parsed, plot_type, channel, config)` | Canonicalise → validate → resolve channel → look up samples → run the computer → wrap in `PlotSeriesOut` |
| `generate_all_plots(upload_id, sensor_id, path, config)` | Loads, resolves the active channel once, and generates every enabled plot for that channel |

### 4.9.6 `plot_storage.py`

```python
ALGORITHM_VERSION = "v1"

def compute_config_fingerprint(config) -> str:
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "sampling_rate_hz": float(config["sampling_rate_hz"]),
        "fft_lines": config.get("fft_lines"),
        "frequency_max_hz": config.get("frequency_max_hz"),
        "data_type": config.get("data_type", "acceleration"),
        "enabled_plots": sorted(normalize_plot_types(config.get("enabled_plots"))),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:32]
```

Note what is **excluded**: `active_channel` and `channel_count`. Changing the viewed channel must not invalidate the cache, because plots are computed for *all* channels and stored per channel.

`persist_all_plot_results(db, upload, parsed_path, config)`:
1. Load parsed JSON, compute the fingerprint, normalise the enabled list.
2. `delete_plot_results(upload.id, fingerprint)` — idempotent re-computation.
3. For each available channel × each enabled plot type: `generate_plot` → build a `PlotResult` row.
4. `db.add_all(rows)` + `commit`. Returns the row count.

`get_or_load_all_plots(db, upload, config, channel)` — the cache-or-compute read path:

```mermaid
flowchart TD
    A[request] --> B{upload.parsed_data_path set?}
    B -->|no| C["raise ValueError — Upload has no parsed data → 422"]
    B -->|yes| D[fingerprint = compute_config_fingerprint]
    D --> E[load parsed JSON, resolve channel]
    E --> F["read stored rows for upload + fingerprint + channel"]
    F --> G{rows exist AND<br/>set of plot_types == expected set?}
    G -->|no| H[persist_all_plot_results → mark_upload_plots_ready → refresh → re-read]
    G -->|yes| I[use stored rows]
    H --> I
    I --> J[read ALL rows for fingerprint → available_channels]
    J --> K[map rows to PlotSeriesOut, sort by enabled_plots order]
    K --> L[AllPlotsOut]
```

The set comparison (not merely "any rows exist") means enabling a sixth plot type later automatically triggers recomputation.

`get_or_load_single_plot` delegates to the above and filters, raising `ValueError` when the requested type is absent for the channel.

### 4.9.7 `baseline_storage.py`

`persist_baseline_plot_results(db, baseline, parsed_data, config)` mirrors `persist_all_plot_results` but takes the parsed dict directly from the baseline row (no filesystem dependency) and writes `BaselinePlotResult` rows. `baseline_plot_to_series(row)` maps a row back to `PlotSeriesOut`.

### 4.9.8 `feature_extraction.py`

Constants: `SHAFT_FREQ_MIN_HZ = 5.0`, `SHAFT_FREQ_MAX_HZ = 120.0`, `FFT_BAND_MAX_HZ = 500.0`, `SEGMENT_COUNT = 32`.

The ten features computed by `extract_channel_features(samples, fs)`:

| # | `feature_code` | Formula | Unit |
|---|----------------|---------|------|
| 1 | `rms` | `sqrt(mean(x²))` | `scaled_eng` |
| 2 | `peak` | `max(|x|)` | `scaled_eng` |
| 3 | `crest_factor` | `peak / rms` (0 when `rms < 1e-30`) | `dimensionless` |
| 4 | `kurtosis` | Excess kurtosis `m₄/v² − 3` (0 when variance `< 1e-30`) | `dimensionless` |
| 5 | `fft_band_energy_0_500` | `Σ spectrum²` over `f ≤ 500 Hz` | `scaled_eng_sq` |
| 6 | `amplitude_1x` | Magnitude at the estimated shaft frequency | `scaled_eng` |
| 7 | `amplitude_2x` | Magnitude at `2 × f_shaft` | `scaled_eng` |
| 8 | `amplitude_3x` | Magnitude at `3 × f_shaft` | `scaled_eng` |
| 9 | `envelope_rms` | `sqrt(mean(|hilbert(x)|²))` | `scaled_eng` |
| 10 | `noise_floor` | `20·log₁₀(max(mean(spectrum), 1e-30))` | `dB` |

**Shaft-frequency estimation** (`_estimate_shaft_hz`): take the FFT bin with maximum magnitude inside 5–120 Hz (i.e. 300–7200 RPM, the practical range for industrial rotating machinery). If no bin falls in that band, use the global maximum. `_magnitude_at_freq` then picks the nearest bin via `argmin(|freqs − target|)`. Features 6–8 carry metadata `{estimated_shaft_hz, sampling_rate_hz, sample_count}` so the estimate is auditable.

**`extract_segment_trends(samples, fs, num_segments=32)`** splits the signal into equal segments, runs the full feature extraction on each, and returns `{trend_x, trend_y, value, unit, metadata}` per feature code, where `trend_x` is the mid-point time of each segment in seconds and `value` is the whole-signal scalar.

> Performance characteristic: this function calls `extract_channel_features` once per segment **per feature code**, i.e. `10 × 32 = 320` full extractions per channel, each performing an FFT and a Hilbert transform on the segment. This is the dominant cost of the upload pipeline and the reason the frontend polls `features_status` every 3 seconds and sets a 120-second HTTP timeout.

`extract_all_channels` and `extract_all_channel_trends` iterate `range(effective_channel_count)` and skip channels with fewer than 4 samples.

### 4.9.9 `threshold_evaluator.py`

Four status constants (`normal`, `warning`, `critical`, `no_baseline`) and a `ThresholdRule` dataclass with `from_row()` for ORM conversion.

`evaluate_feature(code, value, rule, channel_rms, baseline_value)` supports five rule types:

| `rule_type` | Logic |
|-------------|-------|
| `absolute_max` | `value ≤ normal_max` → normal; `≤ warning_max` → warning; else critical. Returns normal if `warning_max` is `None` |
| `absolute_db` | Identical arithmetic (dB values are negative, so the ordering still holds) |
| `range` | Normal when `normal_min ≤ v ≤ normal_max`; warning when `warning_min ≤ v ≤ warning_max`; else critical. Missing bounds default to `0.0` / `inf` |
| `percent_rms` | `pct = 100·v/channel_rms`; `< normal_max` → normal; `< warning_max` → warning; else critical. Returns normal when RMS is missing or `< 1e-30` |
| `percent_baseline` | Returns **`no_baseline`** when there is no baseline value. Otherwise `pct = 100·v/baseline`; `≤ normal_max` (default 120) → normal; `≤ warning_max` (default 150) → warning; `≤ metadata.critical_percent` → warning; else critical |
| anything else | `normal` (safe default) |

`status_to_health_level(status)` maps to the display strings `Critical`, `Warning`, `Normal`, `No baseline`.

### 4.9.10 `feature_storage.py`

| Function | Behaviour |
|----------|-----------|
| `_load_parsed_for_upload(db, upload)` | Prefers `measurement_upload_data.parsed_data` (DB); falls back to the JSON file; raises `ValueError` if neither is available |
| `ensure_upload_features_ready(db, upload, fs)` | Returns immediately when `features_status == "ready"` **and** rows actually exist (guards against a status/row mismatch). Requires `parse_status == "parsed"`. Resets a `failed` status to `pending` before retrying. Computes, persists, marks ready |
| `_baseline_ref_map(db, sensor_id)` | Builds `{(channel, feature_code): value}` from the sensor's **primary** baseline; empty dict when there is none |
| `persist_upload_features_and_trends(db, upload, parsed, fs)` | The core writer — see below |
| `copy_upload_features_to_baseline(db, upload_id, baseline)` | Copies feature rows into `baseline_channel_features`, forcing `status = "normal"` (a baseline is by definition the reference) |
| `features_summary_from_rows(rows)` | Counts by status plus `total`; unknown statuses are counted as `normal` |

`persist_upload_features_and_trends` flow:
1. Load active threshold rules → `{feature_code: rule}`.
2. Build the baseline reference map.
3. `extract_all_channels` and `extract_all_channel_trends`.
4. Delete any existing feature and trend rows for the upload (idempotent recompute).
5. For each channel: capture `channel_rms`, then for each of the 10 codes evaluate the status and build a `MeasurementChannelFeature`; for each trend point build a `MeasurementChannelFeatureTrend`.
6. `db.bulk_save_objects(...)` for both lists, then a single `commit`. Returns `(feature_rows, trend_rows)`.

`bulk_save_objects` is used deliberately: a typical 8-channel upload writes `8 × 10 = 80` feature rows and `8 × 10 × 32 = 2560` trend rows, and the bulk path skips per-object ORM identity-map overhead.

### 4.9.11 `acquisition_config.py`

Defaults used when a sensor has no plot configuration: `DEFAULT_SAMPLE_RATE_HZ = 256_000.0`, `DEFAULT_LOR = 51_200`, `DEFAULT_FMAX_HZ = 15_000.0`, `DEFAULT_CHANNEL_COUNT = 8`, `DEFAULT_WINDOW = "HANNING"`, `DEFAULT_MINUTES = "1"`, `DEFAULT_AVERAGING = 1`, `DEFAULT_OVERLAP = 0`.

`compute_acquisition_formula(sample_rate, lor, overlap, average_count)` returns:

| Field | Formula |
|-------|---------|
| `frequencyResolutionHz` | `sample_rate / lor` |
| `blockTimeSeconds` | `lor / sample_rate` |
| `requiredSamples` | `lor` |
| `totalAcquisitionTimeSeconds` | `blockTime × averageCount` |
| `stepSizeSamples` | `lor × (1 − overlap)`, floored at `lor` when the result is ≤ 0 |
| `sampleRateHz`, `overlapDecimal`, `averageCount`, `fmaxHz`, `lor` | Pass-through |

`_axis_from_orientation` maps the sensor's orientation to `HORIZONTAL` / `AXIAL` / `VERTICAL` (default). `build_channels` emits one entry per channel with `channelIndex` starting at **1** (edge convention) while the platform's own channels are 0-based (`ch0`).

`build_edge_acquisition_config(sensor, plot_config)` prefers the sensor's saved plot configuration and falls back to the defaults, then assembles the full payload, including `sensorId` (the `device_id`, or the sensor UUID as a fallback) and `platformSensorId` (always the UUID).

## 4.10 Routers — endpoint inventory

| Router | Prefix | Tag | Router-level dependency | Endpoints |
|--------|--------|-----|-------------------------|-----------|
| `auth` | `/api/v1/auth` | Authentication | none | 5 |
| `equipment` | `/api/v1/equipment` | Equipment | `get_current_user` | 13 |
| `lookups` | `/api/v1/lookups` | Lookups | `get_current_user` | 2 |
| `measurements` | `/api/v1/measurements` | Measurements | `get_current_user` | 14 |
| `baselines` | `/api/v1/baselines` | Baselines | `get_current_user` | 8 |
| (app) | `/health` | — | none | 1 |

Full request/response documentation is in **Section 5.0**.

## 4.11 Middleware, Filters, and Interceptors

The backend registers exactly **one** middleware: `CORSMiddleware`. There is no logging middleware, no rate limiter, no request-ID injector, and no global exception handler.

Cross-cutting behaviour is instead implemented through FastAPI's dependency system:

| Concern | Mechanism |
|---------|-----------|
| Authentication | `dependencies=[Depends(get_current_user)]` at router level |
| Authorisation | `dependencies=[Depends(require_write_access)]` at route level |
| Session lifecycle | `Depends(get_db)` generator |
| Validation | Pydantic request models |
| Serialisation | `response_model=` on every route |
| OpenAPI security metadata | `app.openapi = custom_openapi` |

## 4.12 Logging

Two call sites use `logging`:

| Location | Logger | Messages |
|----------|--------|----------|
| `services/seed.py` | `logging.getLogger("uvicorn")` | "Super admin already exists — skipping seed", "Seeded super admin user: …", "Seeded admin user: …", "Cleared must_change_password for seeded admin (legacy flag): …", and a warning when the initial-admin env variables are absent |
| `routers/equipment.py::create_equipment` | `logging.getLogger("uvicorn")` (imported inline) | `[CREATE_EQUIPMENT] plant_name=… area=… machine_name=… machine_type=…` |

Everything else relies on Uvicorn's default access log. Alembic logging is configured in `alembic.ini`: root and `sqlalchemy.engine` at `WARN`, `alembic` at `INFO`, formatted as `%(levelname)-5.5s [%(name)s] %(message)s` to stderr.

## 4.13 Caching

There is no in-memory or external cache (no Redis, no `functools.lru_cache`). Caching is **database-backed and content-addressed**:

| Cache | Table | Key | Invalidation |
|-------|-------|-----|--------------|
| Plot series | `plot_results` | `(upload_id, plot_type, channel, config_fingerprint)` — a unique constraint | New fingerprint ⇒ new rows; `delete_plot_results(upload_id, fingerprint)` before each recompute |
| Baseline plot series | `baseline_plot_results` | `(baseline_id, plot_type, channel, config_fingerprint)` | Same pattern |
| Feature values | `measurement_channel_features` | `(upload_id, channel, feature_code)` | Full delete-then-insert per upload |
| Feature trends | `measurement_channel_feature_trends` | `(upload_id, channel, feature_code, segment_index)` | Full delete-then-insert per upload |
| OpenAPI schema | Process memory | `app.openapi_schema` | Process restart |

On the client, TanStack Query provides a second cache layer with a 30-second default `staleTime`.

## 4.14 Transactions

| Pattern | Example |
|---------|---------|
| Single-statement commit | Most CRUD writes: mutate → `db.commit()` → `db.refresh()` |
| Flush-then-insert-children | `create_equipment`: `add(equipment)` → `flush()` (assigns the PK) → add sensors → single `commit()` — so equipment and its sensors are atomic |
| Bulk insert in one transaction | `persist_upload_features_and_trends`: two `bulk_save_objects` calls then one `commit` |
| Delete-then-insert | `persist_all_plot_results` commits the delete inside `delete_plot_results`, then commits the inserts — **two transactions**, so a crash between them leaves the upload with no cached plots (self-healing: the next read recomputes) |
| Multi-step without an outer transaction | `POST /measurements/upload` commits at each stage (record → parsed → upload data → plots → features). A failure part-way leaves an upload row whose status columns record exactly how far it got — the design intentionally favours partial visibility over all-or-nothing |

## 4.15 Dependency Injection

FastAPI's `Depends` is the only DI mechanism. Three provider levels are used:

```mermaid
graph LR
    A["Depends(get_db)"] --> B[Session]
    C["Depends(bearer_scheme)"] --> D[HTTPAuthorizationCredentials]
    B --> E["Depends(get_current_user)"]
    D --> E
    E --> F["Depends(require_write_access)"]
    E --> G[Route handler]
    F --> G
```

Router-level `dependencies=[...]` apply to every route in the router without appearing in the handler signature (used for authentication). Route-level `dependencies=[...]` add write-role enforcement. Handler parameters (`db: Session = Depends(get_db)`) inject values the handler actually uses.

## 4.16 Scheduler, Async Processing, Background Jobs

**None exist.** There is no Celery, APScheduler, `BackgroundTasks`, or cron integration. Every operation is synchronous within its request:

* Parsing, plot computation, and feature extraction all run inline inside `POST /measurements/upload`.
* On-demand recomputation happens inside the corresponding `GET` (`ensure_upload_features_ready`, `get_or_load_all_plots`).

The two `async def` handlers (`upload_image`, `upload_sensor_data`, `upload_baseline`) are async only because `await file.read()` is required by Starlette's `UploadFile`; all subsequent work is CPU-bound and blocking.

**Operational consequence.** Under Uvicorn's default single worker, a large upload's feature extraction blocks the event loop. Section 11 discusses this and the available mitigations.

## 4.17 Exception Handling (backend)

| Layer | Behaviour |
|-------|-----------|
| Services | Raise `ValueError` with a human-readable message; never raise `HTTPException` |
| Routers | Translate: `except ValueError as e: raise HTTPException(422, str(e))` |
| Auth dependency | Raises 401 with `headers={"WWW-Authenticate": "Bearer"}` |
| Non-fatal stage failure | `try/except Exception` around plots and features inside the upload endpoint; the error string is written to `plots_error` / `features_error` and the request still succeeds |
| Fatal stage failure | Parse failure calls `mark_upload_failed` then raises 422 `f"PDF parsing failed: {e}"` |
| Best-effort operations | `POST /auth/logout` swallows `ValueError` from an invalid token and still returns 204 |
| Cleanup | `POST /baselines/upload` removes its temp file in a `finally` block |
| Unhandled | No custom handler — FastAPI returns a generic 500 |

## 4.18 Alembic Migrations

| Rev | Down-rev | Title | Objects created / altered |
|-----|----------|-------|---------------------------|
| 001 | — | initial schema | `equipment_masters` (40 cols), unique `uq_equipment_machine_id`, indexes on `plant_name` and `machine_type`; `sensor_configurations` + index on `equipment_id` |
| 002 | 001 | machine_id nullable | `ALTER equipment_masters.machine_id → NULL` |
| 003 | 002 | measurement tables | `plot_configurations` + unique index on `sensor_id`; `sensor_data_uploads` + index on `sensor_id` |
| 004 | 003 | auth tables | `roles` (+unique name index), `users` (+unique email index), `user_roles`, `refresh_tokens` (+2 indexes); bulk-inserts 5 roles: `super_admin`, `plant_admin`, `engineer`, `operator`, `viewer` |
| 005 | 004 | sensor device_id | `sensor_configurations.device_id` + unique index |
| 006 | 005 | plot_results | `plot_results` + 2 indexes + unique `(upload_id, plot_type, channel, config_fingerprint)`; adds `plots_status`, `plots_error`, `plots_computed_at` to `sensor_data_uploads` |
| 007 | 006 | upload data and baselines | `measurement_upload_data`, `sensor_baselines` (+2 indexes), `baseline_plot_results` (+index +unique constraint) |
| 008 | 007 | user role column | Adds `users.role` default `'user'`; backfills `super_admin` and `admin` from `user_roles`; inserts roles `admin` and `user` with `ON CONFLICT DO NOTHING`; adds `CHECK (role IN ('super_admin','admin','user'))` |
| 009 | 008 | upload history fields | Adds `original_filename` and `source` to `sensor_data_uploads`; backfills `original_filename` from `measurement_upload_data`; creates the composite index `(sensor_id, created_at)` |
| 010 | 009 | channel features and trends | **Idempotent** (uses `_table_exists` / `_column_exists` via `sa.inspect`). Adds `features_status/_error/_computed_at`; creates `feature_definitions`, `feature_threshold_rules` (+index), `measurement_channel_features` (+unique +index), `baseline_channel_features` (+unique +index); seeds 10 feature definitions and 10 threshold rules only when the tables are empty |
| 011 | 010 | feature trends table | Creates `measurement_channel_feature_trends` (+unique +composite index); returns early if the table already exists |

Migrations 010 and 011 are explicitly written to recover from a partially applied 010 — their docstrings say *"idempotent for partial installs"* and *"partial 010 recovery"*.

### 4.18.1 `alembic/env.py`

```python
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))   # repo-root .env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))          # make `app` importable
from app.database import Base
import app.models                                                          # register all models
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
target_metadata = Base.metadata
```

The placeholder URL in `alembic.ini` (`driver://user:pass@localhost/dbname`) is always overwritten. Online mode uses `poolclass=pool.NullPool` so migrations do not hold pooled connections.

## 4.19 Backend Utility Scripts

| Script | Purpose | Notes |
|--------|---------|-------|
| `scripts/create_sample_sensor_pdf.py` | Generates `backend/sample_sensor_data.pdf` with a `timestamp,ch0,ch1` header and 512 rows at `fs = 25600`. `ch0 = 0.5·sin(2π·120t) + 0.1·sin(2π·480t)`, `ch1 = 0.3·sin(2π·60t)` | Requires `reportlab`, which is **not** in `requirements.txt`; the script prints an install hint and re-raises |
| `scripts/test_auth_phase1.py` | End-to-end auth smoke test with `fastapi.testclient.TestClient`: seed → login → `/me` (asserts `super_admin` in roles) → refresh → logout (204) → `/me` without auth (401) | Hits the real configured database; not a pytest test and not part of a suite |

## 4.20 Edge Acquisition Script — `scripts/vibration.py`

A standalone reader for a Xilinx ZedBoard-class device, outside the FastAPI process:

* Connects with `iio.Context("ip:192.168.1.34")` and `ctx.set_timeout(0)`.
* Finds device `cf_axi_adc`; exits with an error if absent.
* Enables channels `voltage0` … `voltage7` and records each channel's `scale` attribute.
* Allocates `iio.Buffer(dev, 4096)` and loops on `buf.refill()`.
* Reads raw `int32`, reshapes to `(-1, 8)` interleaved, then **shifts left 8 and arithmetic-shifts right 8** to discard an 8-bit status header while sign-extending the 24-bit ADC value.
* Prints the latest raw count per channel on one refreshing console line.
* Handles `KeyboardInterrupt` gracefully and `OSError` with a hardware troubleshooting hint.

This script demonstrates the acquisition side of the contract that `/api/v1/measurements/acquisition` serves configuration for; it does not itself call the API.
