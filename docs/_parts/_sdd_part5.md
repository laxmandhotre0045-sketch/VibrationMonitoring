---

# 6.0 Database Documentation

## 6.1 Database Identity

| Property | Value | Source |
|----------|-------|--------|
| Engine | PostgreSQL 16 | `docker-compose.yml` → `image: postgres:16` |
| Database name | `vibration_platform` | `.env` → `POSTGRES_DB` |
| Owner / role | `vibration_user` | `.env` → `POSTGRES_USER` |
| Host port | `5433` (mapped to container `5432`) | `docker-compose.yml` |
| Connection URL (container network) | `postgresql://vibration_user:***@postgres:5432/vibration_platform` | `docker-compose.yml` → `DATABASE_URL` |
| Driver | `psycopg2-binary` 2.9.9 | `requirements.txt` |
| Storage engine | PostgreSQL uses a single integrated storage engine; tables are heap-organised with MVCC. There is no per-table engine choice as in MySQL. | — |
| Character set / encoding | `UTF8` — the default for the `postgres:16` image (`initdb` default, `en_US.utf8` locale). No `ENCODING` override is issued anywhere in the code. | — |
| Collation | Image default (`en_US.utf8`). No per-column `COLLATE` clause exists in any migration. |
| Schema | `public` (no explicit schema is set) |
| UUID generation | `gen_random_uuid()` as a server default in migrations; `uuid.uuid4` as a Python-side default in the ORM. `gen_random_uuid()` is built into PostgreSQL 13+, so no `pgcrypto` extension is required. |
| Migration tool | Alembic — 11 revisions, head `011` |
| Table count | 17 |
| Column count | 215 |

## 6.2 Entity Relationship Diagram

```mermaid
erDiagram
    equipment_masters ||--o{ sensor_configurations : "has sensors (CASCADE)"
    sensor_configurations ||--o| plot_configurations : "one profile (UNIQUE, CASCADE)"
    sensor_configurations ||--o{ sensor_data_uploads : "captures (CASCADE)"
    sensor_configurations ||--o{ measurement_upload_data : "denormalised FK (CASCADE)"
    sensor_configurations ||--o{ plot_results : "denormalised FK (CASCADE)"
    sensor_configurations ||--o{ sensor_baselines : "references (CASCADE)"
    sensor_configurations ||--o{ baseline_plot_results : "denormalised FK (CASCADE)"
    sensor_configurations ||--o{ measurement_channel_features : "denormalised FK (CASCADE)"
    sensor_configurations ||--o{ measurement_channel_feature_trends : "denormalised FK (CASCADE)"
    sensor_configurations ||--o{ baseline_channel_features : "denormalised FK (CASCADE)"

    sensor_data_uploads ||--o| measurement_upload_data : "raw bytes (UNIQUE, CASCADE)"
    sensor_data_uploads ||--o{ plot_results : "cached plots (CASCADE)"
    sensor_data_uploads ||--o{ measurement_channel_features : "features (CASCADE)"
    sensor_data_uploads ||--o{ measurement_channel_feature_trends : "trends (CASCADE)"
    sensor_data_uploads ||--o{ sensor_baselines : "promoted from (SET NULL)"

    sensor_baselines ||--o{ baseline_plot_results : "cached plots (CASCADE)"
    sensor_baselines ||--o{ baseline_channel_features : "reference features (CASCADE)"

    feature_definitions ||--o{ feature_threshold_rules : "code FK"
    feature_definitions ||--o{ measurement_channel_features : "code FK"
    feature_definitions ||--o{ measurement_channel_feature_trends : "code FK"
    feature_definitions ||--o{ baseline_channel_features : "code FK"

    users ||--o{ user_roles : "assignment (CASCADE)"
    roles ||--o{ user_roles : "assignment (CASCADE)"
    users ||--o{ refresh_tokens : "sessions (CASCADE)"
```

## 6.3 Relationship Catalogue

| # | Parent | Child | FK column | Cardinality | On delete | Declared in |
|---|--------|-------|-----------|-------------|-----------|-------------|
| 1 | `equipment_masters` | `sensor_configurations` | `equipment_id` | 1 : N | CASCADE | 001 |
| 2 | `sensor_configurations` | `plot_configurations` | `sensor_id` (UNIQUE) | 1 : 0..1 | CASCADE | 003 |
| 3 | `sensor_configurations` | `sensor_data_uploads` | `sensor_id` | 1 : N | CASCADE | 003 |
| 4 | `sensor_data_uploads` | `plot_results` | `upload_id` | 1 : N | CASCADE | 006 |
| 5 | `sensor_configurations` | `plot_results` | `sensor_id` | 1 : N | CASCADE | 006 |
| 6 | `sensor_data_uploads` | `measurement_upload_data` | `upload_id` (UNIQUE) | 1 : 0..1 | CASCADE | 007 |
| 7 | `sensor_configurations` | `measurement_upload_data` | `sensor_id` | 1 : N | CASCADE | 007 |
| 8 | `sensor_configurations` | `sensor_baselines` | `sensor_id` | 1 : N | CASCADE | 007 |
| 9 | `sensor_data_uploads` | `sensor_baselines` | `source_upload_id` | 1 : N | **SET NULL** | 007 |
| 10 | `sensor_baselines` | `baseline_plot_results` | `baseline_id` | 1 : N | CASCADE | 007 |
| 11 | `sensor_configurations` | `baseline_plot_results` | `sensor_id` | 1 : N | CASCADE | 007 |
| 12 | `feature_definitions` | `feature_threshold_rules` | `feature_code` → `code` | 1 : N | (default NO ACTION) | 010 |
| 13 | `sensor_data_uploads` | `measurement_channel_features` | `upload_id` | 1 : N | CASCADE | 010 |
| 14 | `sensor_configurations` | `measurement_channel_features` | `sensor_id` | 1 : N | CASCADE | 010 |
| 15 | `feature_definitions` | `measurement_channel_features` | `feature_code` | 1 : N | NO ACTION | 010 |
| 16 | `sensor_baselines` | `baseline_channel_features` | `baseline_id` | 1 : N | CASCADE | 010 |
| 17 | `sensor_configurations` | `baseline_channel_features` | `sensor_id` | 1 : N | CASCADE | 010 |
| 18 | `feature_definitions` | `baseline_channel_features` | `feature_code` | 1 : N | NO ACTION | 010 |
| 19 | `sensor_data_uploads` | `measurement_channel_feature_trends` | `upload_id` | 1 : N | CASCADE | 011 |
| 20 | `sensor_configurations` | `measurement_channel_feature_trends` | `sensor_id` | 1 : N | CASCADE | 011 |
| 21 | `feature_definitions` | `measurement_channel_feature_trends` | `feature_code` | 1 : N | NO ACTION | 011 |
| 22 | `users` | `user_roles` | `user_id` (PK part) | 1 : N | CASCADE | 004 |
| 23 | `roles` | `user_roles` | `role_id` (PK part) | 1 : N | CASCADE | 004 |
| 24 | `users` | `refresh_tokens` | `user_id` | 1 : N | CASCADE | 004 |

**Why relationship 9 differs.** `sensor_baselines.source_upload_id` is `ON DELETE SET NULL` so that deleting a measurement upload never destroys the baseline promoted from it. The baseline keeps its own copy of the file bytes and parsed data, so it remains fully self-sufficient — only the provenance link is lost.

**Why `sensor_id` is repeated on child tables.** `plot_results`, `measurement_upload_data`, `baseline_plot_results`, and all three feature tables carry a direct `sensor_id` in addition to their `upload_id`/`baseline_id`. This is a deliberate denormalisation: it lets a query filter by sensor without joining through the upload or baseline, and it guarantees the row is removed when the sensor is deleted even if the intermediate path changes.

## 6.4 Table Reference

Legend for the **Nullable** column: `NO` = `NOT NULL`; `YES` = nullable; `PK` = primary key.

---

### 6.4.1 `equipment_masters`

**Purpose.** One row per physical machine — the digital twin master record. Every downstream measurement is ultimately traceable to a row here.
**Used by.** `crud/equipment.py`; endpoints 7–20; the Equipment Master pages; the analysis page's equipment/sensor selectors.
**CRUD.** Create (`POST /equipment/`), Read (list + detail), Update (`PUT`/`PATCH`), Delete (`DELETE`, cascading).

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `plant_name` | `VARCHAR(255)` | NO | — | Plant in the asset hierarchy; filterable with `ILIKE` |
| `area` | `VARCHAR(255)` | NO | — | Functional area within the plant |
| `line` | `VARCHAR(255)` | NO | — | Production line |
| `machine_name` | `VARCHAR(255)` | NO | — | Human-readable machine label |
| `machine_id` | `VARCHAR(100)` | YES | `NULL` | Plant asset code. **UNIQUE**; empty strings are coerced to `NULL` so multiple blanks are allowed |
| `machine_type` | `VARCHAR(50)` | NO | — | One of the 13 `machine-types` lookup values; drives conditional form fields and diagnostic expectations |
| `machine_criticality` | `VARCHAR(20)` | NO | — | Low / Medium / High / Critical |
| `manufacturer` | `VARCHAR(255)` | YES | — | OEM |
| `model` | `VARCHAR(255)` | YES | — | Model designation |
| `serial_number` | `VARCHAR(100)` | YES | — | OEM serial |
| `rated_power_kw` | `NUMERIC(10,2)` | YES | — | Nameplate power; used to normalise amplitude against load |
| `rated_rpm` | `INTEGER` | YES | — | Nameplate speed; the basis for shaft-frequency and harmonic markers |
| `drive_type` | `VARCHAR(50)` | YES | — | Direct / Belt / Gear / Chain / VFD / Hydraulic |
| `load_type` | `VARCHAR(50)` | YES | — | Constant / Variable / Intermittent / Cyclic / Shock |
| `foundation_type` | `VARCHAR(50)` | YES | — | Affects expected vibration transmission |
| `coupling_details` | `VARCHAR(50)` | YES | — | Coupling family |
| `bearing_details` | `TEXT` | YES | — | Free-text bearing specification |
| `bearing_number_de` | `VARCHAR(100)` | YES | — | Drive-end bearing designation; required for BPFO/BPFI computation |
| `bearing_number_nde` | `VARCHAR(100)` | YES | — | Non-drive-end bearing designation |
| `gearbox_ratio` | `NUMERIC(8,3)` | YES | — | Reduction ratio |
| `gear_teeth` | `INTEGER` | YES | — | Tooth count for gear-mesh frequency |
| `motor_pole_count` | `INTEGER` | YES | — | 2–12; for electrical fault frequencies |
| `fan_blades` | `INTEGER` | YES | — | Blade-pass frequency input |
| `pump_vanes` | `INTEGER` | YES | — | Vane-pass frequency input |
| `direction_of_rotation` | `VARCHAR(30)` | YES | — | Clockwise / Counter-Clockwise / Bidirectional |
| `operating_speed_min` | `INTEGER` | YES | — | Lower speed envelope; part of AI readiness |
| `operating_speed_max` | `INTEGER` | YES | — | Upper speed envelope; part of AI readiness |
| `load_range_min` | `NUMERIC(5,2)` | YES | — | Minimum load % |
| `load_range_max` | `NUMERIC(5,2)` | YES | — | Maximum load % |
| `normal_operating_load` | `NUMERIC(5,2)` | YES | — | Typical load % |
| `process_details` | `TEXT` | YES | — | Process narrative |
| `operating_environment` | `VARCHAR[]` | YES | — | PostgreSQL text array of the 13 environment values |
| `lubrication_type` | `VARCHAR(50)` | YES | — | Grease / Oil Bath / … |
| `installation_date` | `DATE` | YES | — | Commissioning date |
| `last_maintenance_date` | `DATE` | YES | — | Last intervention |
| `maintenance_notes` | `TEXT` | YES | — | Free text |
| `equipment_image_path` | `VARCHAR(500)` | YES | — | Filesystem path to the uploaded photo |
| `asset_status` | `VARCHAR(30)` | YES | `'Active'` | Active / Inactive / Under Maintenance / Decommissioned |
| `machine_train_configured` | `BOOLEAN` | YES | `false` | AI readiness flag (manual) |
| `bearing_database_mapped` | `BOOLEAN` | YES | `false` | AI readiness flag (manual) |
| `operating_mode_configured` | `BOOLEAN` | YES | `false` | AI readiness flag (manual) |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Insert time; the list sort key |
| `updated_at` | `TIMESTAMPTZ` | YES | `now()` | ORM sets `onupdate=utcnow` |

**Constraints.** PK `id`; UNIQUE `uq_equipment_machine_id (machine_id)`.
**Indexes.** `ix_equipment_plant_name (plant_name)`, `ix_equipment_machine_type (machine_type)`, plus the unique index backing `machine_id`.
**Performance note.** `plant_name` filtering uses `ILIKE '%value%'`, which cannot use the plain B-tree index — a leading-wildcard match forces a sequential scan. See §14.6.

---

### 6.4.2 `sensor_configurations`

**Purpose.** A measurement point on a machine — the unit that owns captures, plots, features, and baselines.
**Used by.** `crud/equipment.py` sensor functions; endpoints 16–19; every measurement and baseline endpoint (via `sensor_id`).

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key; used as `sensor_id` everywhere downstream |
| `equipment_id` | `UUID` | NO | — | FK → `equipment_masters.id` CASCADE |
| `sensor_type` | `VARCHAR(50)` | NO | — | One of 14 sensor types; influences the edge `transducerType` |
| `mounting_location` | `VARCHAR(100)` | NO | — | Bearing Housing DE, Motor NDE, … |
| `orientation` | `VARCHAR(30)` | NO | — | Horizontal / Vertical / Axial / Radial / Tangential; mapped to the edge `machineAxis` |
| `mounting_method` | `VARCHAR(50)` | YES | — | Stud / Magnetic / Adhesive / … |
| `sensitivity` | `NUMERIC(10,4)` | YES | — | Transducer sensitivity; emitted as `sensitivityMvPerG` |
| `sensitivity_unit` | `VARCHAR(20)` | YES | — | mV/g, mV/mm/s, mV/µm, mA, V |
| `sampling_rate` | `VARCHAR(20)` | YES | — | Human label such as `"25600 Hz"` or `"Custom"` |
| `sampling_rate_custom` | `INTEGER` | YES | — | Numeric value when the label is `Custom` |
| `frequency_range` | `VARCHAR(20)` | YES | — | Label such as `"0-10000 Hz"` |
| `frequency_range_custom_min` | `INTEGER` | YES | — | Custom lower bound |
| `frequency_range_custom_max` | `INTEGER` | YES | — | Custom upper bound |
| `is_active` | `BOOLEAN` | YES | `true` | Soft enable/disable |
| `device_id` | `VARCHAR(64)` | YES | `NULL` | **UNIQUE** MAC-style edge identifier; the join key for `/measurements/acquisition` |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Insert time |

**Constraints.** PK `id`; FK `equipment_id`; UNIQUE index on `device_id`.
**Indexes.** `ix_sensor_equipment_id (equipment_id)`, `ix_sensor_configurations_device_id (device_id) UNIQUE`.

> Design observation: the sensor stores sampling rate and frequency range as *labels* for documentation, while the numeric values actually used for processing live in `plot_configurations`. The two are not synchronised by any code path.

---

### 6.4.3 `plot_configurations`

**Purpose.** The single processing profile per sensor. Its contents feed `compute_config_fingerprint`, so changing any of `sampling_rate_hz`, `fft_lines`, `frequency_max_hz`, `data_type`, or `enabled_plots` invalidates every cached plot for that sensor's uploads.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE; **UNIQUE** (one profile per sensor) |
| `channel_count` | `INTEGER` | NO | `1` | 1–32 |
| `active_channel` | `INTEGER` | NO | `0` | Default channel for plot reads; clamped on read |
| `sampling_rate_hz` | `NUMERIC(12,4)` | NO | `25600` | Governs the FFT frequency axis and all trend time axes |
| `fft_lines` | `INTEGER` | NO | `1600` | Lines of resolution; the FFT block is `2 × fft_lines` samples (64–65536) |
| `frequency_max_hz` | `NUMERIC(12,4)` | YES | `NULL` | Optional spectrum cut-off |
| `data_type` | `VARCHAR(30)` | NO | `'acceleration'` | acceleration / velocity / displacement |
| `enabled_plots` | `JSONB` | NO | `'[]'` | Array of plot-type strings; an empty array is treated as "all five" on read |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Insert time |
| `updated_at` | `TIMESTAMPTZ` | YES | `now()` | Set explicitly by `update_plot_config` |

**Indexes.** `ix_plot_config_sensor_id (sensor_id) UNIQUE`.

---

### 6.4.4 `sensor_data_uploads`

**Purpose.** The lifecycle record for one capture. Its three status triplets make the processing pipeline observable.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Also used as the on-disk filename stem |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `channel_count` | `INTEGER` | NO | — | Channels requested at upload time |
| `pdf_path` | `VARCHAR(500)` | NO | — | Path to the original file (CSV or PDF, despite the column name) |
| `parsed_data_path` | `VARCHAR(500)` | YES | — | Path to the parsed JSON sidecar |
| `sample_count` | `INTEGER` | YES | — | Rows parsed |
| `parse_status` | `VARCHAR(20)` | NO | `'pending'` | `pending` → `parsed` \| `failed` |
| `parse_error` | `TEXT` | YES | — | Parser message on failure |
| `plots_status` | `VARCHAR(20)` | NO | `'pending'` | `pending` → `ready` \| `failed` |
| `plots_error` | `TEXT` | YES | — | Plot computation message |
| `plots_computed_at` | `TIMESTAMPTZ` | YES | — | Last successful plot computation |
| `features_status` | `VARCHAR(20)` | NO | `'pending'` | `pending` → `ready` \| `failed` |
| `features_error` | `TEXT` | YES | — | Feature computation message |
| `features_computed_at` | `TIMESTAMP` | YES | — | Last successful feature computation (note: added in 010 as naive `DateTime`) |
| `original_filename` | `VARCHAR(255)` | YES | — | User-supplied filename; backfilled by 009 |
| `source` | `VARCHAR(20)` | NO | `'manual'` | Ingestion origin; only `manual` is produced today |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Capture-record creation, used as the timeline position |
| `parsed_at` | `TIMESTAMPTZ` | YES | — | Parse completion |

**Indexes.** `ix_sensor_upload_sensor_id (sensor_id)`, `ix_sensor_data_uploads_sensor_id_created_at (sensor_id, created_at)`.
**Why the composite index exists.** Every timeline query is `WHERE sensor_id = ? AND created_at BETWEEN ? AND ? ORDER BY created_at DESC` — the composite index serves the filter and the sort together.

---

### 6.4.5 `measurement_upload_data`

**Purpose.** The durable copy of the capture: original bytes plus the parsed arrays, both in PostgreSQL. This is what makes `POST /baselines/from-upload/{id}` independent of the filesystem.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `upload_id` | `UUID` | NO | — | FK → `sensor_data_uploads.id` CASCADE; **UNIQUE** (1 : 0..1) |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `original_filename` | `VARCHAR(255)` | NO | — | As uploaded |
| `file_format` | `VARCHAR(10)` | NO | — | `csv` or `pdf` |
| `file_content` | `BYTEA` | NO | — | The complete original file |
| `parsed_data` | `JSONB` | NO | — | `{timestamps, channels, sample_count, channel_count, detected_channel_count}` |
| `channel_count` | `INTEGER` | NO | — | Effective channel count |
| `sample_count` | `INTEGER` | NO | — | Row count |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Insert time |

**Indexes.** `ix_measurement_upload_data_sensor_id (sensor_id)`; unique index backing `upload_id`.
**Storage note.** `BYTEA` and `JSONB` values beyond ~2 kB are TOAST-compressed and stored out of line, so wide-row reads that do not select these columns remain cheap. A 50 MB upload therefore does not slow down `SELECT upload_id FROM measurement_upload_data`.

---

### 6.4.6 `plot_results`

**Purpose.** The plot cache. One row per (upload, plot type, channel, fingerprint).

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `upload_id` | `UUID` | NO | — | FK → `sensor_data_uploads.id` CASCADE |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `plot_type` | `VARCHAR(40)` | NO | — | One of the five canonical types |
| `channel` | `INTEGER` | NO | — | 0-based channel index |
| `title` | `VARCHAR(120)` | NO | — | Display title from the DSP routine |
| `x_label` | `VARCHAR(80)` | NO | — | Axis label |
| `y_label` | `VARCHAR(80)` | NO | — | Axis label |
| `x_data` | `JSONB` | NO | — | X array |
| `y_data` | `JSONB` | NO | — | Y array |
| `metadata` | `JSONB` | NO | `'{}'` | Plot-specific extras (`plot_style`, `fft_lines`, `block_size`, `averages`, `sampling_rate_hz`, `num_segments`, `samples`); mapped to `metadata_` in Python |
| `point_count` | `INTEGER` | NO | — | `len(x)`, stored for cheap size inspection |
| `sampling_rate_hz` | `NUMERIC(12,4)` | NO | — | Rate used at computation time |
| `fft_lines` | `INTEGER` | YES | — | Lines used |
| `frequency_max_hz` | `NUMERIC(12,4)` | YES | — | Cut-off used |
| `config_fingerprint` | `VARCHAR(64)` | NO | — | 32-hex-char SHA-256 prefix of the processing configuration |
| `computed_at` | `TIMESTAMPTZ` | NO | `now()` | Computation timestamp |
| `status` | `VARCHAR(20)` | NO | `'ready'` | Only `ready` rows are read |

**Constraints.** UNIQUE `uq_plot_results_upload_plot_channel_fingerprint (upload_id, plot_type, channel, config_fingerprint)`.
**Indexes.** `ix_plot_results_upload_id`, `ix_plot_results_sensor_id`.

---

### 6.4.7 `sensor_baselines`

**Purpose.** Append-only reference captures. The code comment is explicit: *"Historical baseline records — all rows kept (append-only) for RAG / learning."*

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `source_upload_id` | `UUID` | YES | `NULL` | FK → `sensor_data_uploads.id` **SET NULL**; `NULL` for direct uploads |
| `name` | `VARCHAR(200)` | NO | — | User-supplied label |
| `description` | `TEXT` | YES | — | Free text |
| `labels` | `JSONB` | NO | `'[]'` | Tag array for future classification |
| `original_filename` | `VARCHAR(255)` | NO | — | Provenance |
| `file_format` | `VARCHAR(10)` | NO | — | `csv` / `pdf` |
| `file_content` | `BYTEA` | NO | — | Complete original bytes — the reason a baseline survives upload deletion |
| `parsed_data` | `JSONB` | NO | — | Parsed channel arrays |
| `channel_count` | `INTEGER` | NO | — | Channels |
| `sample_count` | `INTEGER` | NO | — | Samples |
| `sampling_rate_hz` | `NUMERIC(12,4)` | NO | — | Rate captured from the plot configuration at creation time |
| `is_primary` | `BOOLEAN` | NO | `false` | Display/comparison default; at most one `true` per sensor, enforced in application code |
| `captured_at` | `TIMESTAMPTZ` | YES | — | Physical capture time; defaults to `utcnow()` when not supplied |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Row creation; the list sort key |

**Indexes.** `ix_sensor_baselines_sensor_id`, `ix_sensor_baselines_created_at`.
**Integrity note.** The "one primary per sensor" rule is enforced by `create_baseline` and `set_baseline_primary` (both clear the previous primary first), **not** by a partial unique index. A concurrent double set-primary could therefore produce two primaries; `get_primary_baseline` mitigates this by ordering `created_at DESC` and taking the first.

---

### 6.4.8 `baseline_plot_results`

Identical column set to `plot_results` with `baseline_id` in place of `upload_id`:

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` |
| `baseline_id` | `UUID` | NO | FK → `sensor_baselines.id` CASCADE |
| `sensor_id` | `UUID` | NO | FK → `sensor_configurations.id` CASCADE |
| `plot_type` | `VARCHAR(40)` | NO | — |
| `channel` | `INTEGER` | NO | — |
| `title` / `x_label` / `y_label` | `VARCHAR(120/80/80)` | NO | — |
| `x_data` / `y_data` | `JSONB` | NO | — |
| `metadata` | `JSONB` | NO | `'{}'` |
| `point_count` | `INTEGER` | NO | — |
| `sampling_rate_hz` | `NUMERIC(12,4)` | NO | — |
| `fft_lines` | `INTEGER` | YES | — |
| `frequency_max_hz` | `NUMERIC(12,4)` | YES | — |
| `config_fingerprint` | `VARCHAR(64)` | NO | — |
| `computed_at` | `TIMESTAMPTZ` | NO | `now()` |
| `status` | `VARCHAR(20)` | NO | `'ready'` |

**Constraints.** UNIQUE `uq_baseline_plot_results_baseline_plot_channel_fingerprint`.
**Indexes.** `ix_baseline_plot_results_baseline_id`.

---

### 6.4.9 `feature_definitions`

**Purpose.** The catalogue of the ten computed features — the reference table for names, units, and display order.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | (Python-side `uuid4`) | Surrogate key |
| `code` | `VARCHAR(40)` | NO | — | **UNIQUE**; the FK target for all feature tables |
| `name` | `VARCHAR(120)` | NO | — | Display name |
| `unit` | `VARCHAR(30)` | NO | — | `scaled_eng`, `scaled_eng_sq`, `dimensionless`, `dB` |
| `description` | `TEXT` | YES | — | Explanation of the metric |
| `sort_order` | `INTEGER` | NO | `0` | Display order (0–9) |
| `is_active` | `BOOLEAN` | NO | `true` | Soft disable |

**Seeded rows (migration 010).**

| code | name | unit | sort_order | description |
|------|------|------|-----------|-------------|
| `rms` | RMS | `scaled_eng` | 0 | Root mean square amplitude |
| `peak` | Peak | `scaled_eng` | 1 | Maximum absolute amplitude |
| `crest_factor` | Crest Factor | `dimensionless` | 2 | Peak / RMS |
| `kurtosis` | Kurtosis | `dimensionless` | 3 | Excess kurtosis |
| `fft_band_energy_0_500` | FFT Band Energy (0-500 Hz) | `scaled_eng_sq` | 4 | Sum of squared FFT magnitudes 0-500 Hz |
| `amplitude_1x` | 1X Amplitude | `scaled_eng` | 5 | FFT magnitude at running speed |
| `amplitude_2x` | 2X Amplitude | `scaled_eng` | 6 | FFT magnitude at 2× running speed |
| `amplitude_3x` | 3X Amplitude | `scaled_eng` | 7 | FFT magnitude at 3× running speed |
| `envelope_rms` | Envelope RMS | `scaled_eng` | 8 | RMS of Hilbert envelope |
| `noise_floor` | Noise Floor | `dB` | 9 | Mean FFT magnitude in dB |

---

### 6.4.10 `feature_threshold_rules`

**Purpose.** Configurable evaluation rules turning a feature value into a status.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `uuid4` | Surrogate key |
| `feature_code` | `VARCHAR(40)` | NO | — | FK → `feature_definitions.code` |
| `rule_type` | `VARCHAR(30)` | NO | — | `absolute_max`, `absolute_db`, `range`, `percent_rms`, `percent_baseline` |
| `machine_type` | `VARCHAR(80)` | YES | `NULL` | `NULL` = global rule; a value scopes the rule to a machine type |
| `normal_max` | `NUMERIC(18,8)` | YES | — | Upper bound of the normal band |
| `warning_max` | `NUMERIC(18,8)` | YES | — | Upper bound of the warning band |
| `normal_min` | `NUMERIC(18,8)` | YES | — | Lower bound (range rules) |
| `warning_min` | `NUMERIC(18,8)` | YES | — | Lower warning bound (range rules) |
| `metadata` | `JSONB` | NO | `'{}'` | Extra parameters, e.g. `{"critical_percent": 150.0}` |
| `is_active` | `BOOLEAN` | NO | `true` | Soft disable |

**Indexes.** `ix_feature_threshold_rules_code_machine (feature_code, machine_type)`.

**Seeded rows (migration 010).** All ten are global (`machine_type = NULL`).

| feature_code | rule_type | normal_max | warning_max | normal_min | warning_min | metadata |
|--------------|-----------|-----------|-------------|-----------|-------------|----------|
| `rms` | `absolute_max` | 0.01 | 0.02 | — | — | `{}` |
| `peak` | `absolute_max` | 0.05 | 0.10 | — | — | `{}` |
| `crest_factor` | `range` | 3.0 | 5.0 | 1.4 | 3.0 | `{}` |
| `kurtosis` | `absolute_max` | 3.5 | 5.0 | — | — | `{}` |
| `fft_band_energy_0_500` | `percent_baseline` | 120.0 | 150.0 | — | — | `{}` |
| `amplitude_1x` | `percent_rms` | 20.0 | 40.0 | — | — | `{}` |
| `amplitude_2x` | `percent_rms` | 10.0 | 20.0 | — | — | `{}` |
| `amplitude_3x` | `percent_rms` | 5.0 | 15.0 | — | — | `{}` |
| `envelope_rms` | `percent_baseline` | 100.0 | 125.0 | — | — | `{"critical_percent": 150.0}` |
| `noise_floor` | `absolute_db` | −60.0 | −54.0 | — | — | `{}` |

> The migration tuple order is `(code, rule_type, machine_type, normal_max, warning_max, normal_min, warning_min, metadata)` — note that `machine_type` is the third element and is `None` for every seeded rule, which is why the frontend mirror in `lib/feature-threshold-lines.ts` uses the same numbers with no machine scoping.

---

### 6.4.11 `measurement_channel_features`

**Purpose.** Evaluated scalar feature values per upload and channel — the source for the Status (Health) tables and summary cards.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `uuid4` | Surrogate key |
| `upload_id` | `UUID` | NO | — | FK → `sensor_data_uploads.id` CASCADE |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `channel` | `INTEGER` | NO | — | 0-based channel |
| `feature_code` | `VARCHAR(40)` | NO | — | FK → `feature_definitions.code` |
| `value` | `NUMERIC(18,8)` | NO | — | Computed value |
| `unit` | `VARCHAR(30)` | NO | — | Copied from the extractor |
| `status` | `VARCHAR(20)` | NO | — | `normal` / `warning` / `critical` / `no_baseline` |
| `metadata` | `JSONB` | NO | `'{}'` | e.g. `{estimated_shaft_hz, sampling_rate_hz, sample_count}` or `{band_hz:[0,500]}` |
| `computed_at` | `TIMESTAMP` | NO | — | Single timestamp shared by the whole batch |

**Constraints.** UNIQUE `uq_measurement_channel_feature (upload_id, channel, feature_code)`.
**Indexes.** `ix_measurement_channel_features_upload (upload_id)`.
**Row volume.** `channels × 10`. An 8-channel upload writes 80 rows.

---

### 6.4.12 `measurement_channel_feature_trends`

**Purpose.** Per-segment feature series inside a single capture — the data behind the ten trend cards.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `uuid4` | Surrogate key |
| `upload_id` | `UUID` | NO | — | FK → `sensor_data_uploads.id` CASCADE |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `channel` | `INTEGER` | NO | — | 0-based channel |
| `feature_code` | `VARCHAR(40)` | NO | — | FK → `feature_definitions.code` |
| `segment_index` | `INTEGER` | NO | — | 0-based segment number |
| `time_s` | `NUMERIC(18,8)` | NO | — | Segment mid-point time in seconds |
| `value` | `NUMERIC(18,8)` | NO | — | Feature value for that segment |
| `computed_at` | `TIMESTAMP` | NO | — | Batch timestamp |

**Constraints.** UNIQUE `uq_measurement_channel_feature_trend (upload_id, channel, feature_code, segment_index)`.
**Indexes.** `ix_measurement_channel_feature_trends_upload (upload_id, channel)` — composite, because every read is scoped to one channel.
**Row volume.** `channels × 10 × ~32`. An 8-channel upload writes about 2560 rows. This is by far the largest table by row count.

---

### 6.4.13 `baseline_channel_features`

**Purpose.** The reference feature values a capture is compared against.

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `uuid4` | Surrogate key |
| `baseline_id` | `UUID` | NO | — | FK → `sensor_baselines.id` CASCADE |
| `sensor_id` | `UUID` | NO | — | FK → `sensor_configurations.id` CASCADE |
| `channel` | `INTEGER` | NO | — | 0-based channel |
| `feature_code` | `VARCHAR(40)` | NO | — | FK → `feature_definitions.code` |
| `value` | `NUMERIC(18,8)` | NO | — | Reference value |
| `unit` | `VARCHAR(30)` | NO | — | Unit |
| `status` | `VARCHAR(20)` | NO | `'normal'` | Always written as `normal` by `copy_upload_features_to_baseline` |
| `metadata` | `JSONB` | NO | `'{}'` | Copied from the source feature row |
| `computed_at` | `TIMESTAMP` | NO | — | Copy timestamp |

**Constraints.** UNIQUE `uq_baseline_channel_feature (baseline_id, channel, feature_code)`.
**Indexes.** `ix_baseline_channel_features_baseline (baseline_id)`.

---

### 6.4.14 `roles`

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `name` | `VARCHAR(50)` | NO | — | **UNIQUE** role name |
| `description` | `VARCHAR(255)` | YES | — | Human description |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Insert time |

**Seeded rows.** Migration 004 inserts five: `super_admin` ("Full platform access"), `plant_admin` ("Manage users and data within assigned plants"), `engineer` ("Equipment and vibration analysis CRUD"), `operator` ("View dashboards and plots"), `viewer` ("Read-only access"). Migration 008 adds two more: `admin` ("Application administrator with full write access.") and `user` ("Read-only platform user.") with `ON CONFLICT (name) DO NOTHING`.

**Total: 7 rows.** Only three (`super_admin`, `admin`, `user`) are used by the current authorisation logic; the other four are legacy and are still mapped defensively by `_user_role` / `primary_role` (`plant_admin` and `engineer` collapse to `admin`).

**Indexes.** `ix_roles_name (name) UNIQUE`.

---

### 6.4.15 `users`

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key; the JWT `sub` |
| `email` | `VARCHAR(255)` | NO | — | **UNIQUE**, stored lower-case, the login identifier |
| `password_hash` | `VARCHAR(255)` | NO | — | bcrypt hash (never the password) |
| `full_name` | `VARCHAR(150)` | NO | — | Display name |
| `role` | `VARCHAR(50)` | NO | `'user'` | Authoritative role; `CHECK` constrained |
| `is_active` | `BOOLEAN` | NO | `true` | Disabling a user invalidates authentication immediately |
| `must_change_password` | `BOOLEAN` | NO | `false` | Forces the `/change-password` redirect |
| `last_login_at` | `TIMESTAMPTZ` | YES | — | Updated on every successful login |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Insert time |
| `updated_at` | `TIMESTAMPTZ` | YES | `now()` | ORM `onupdate` |

**Constraints.** PK `id`; UNIQUE `email`; `CHECK ck_users_role_allowed: role IN ('super_admin','admin','user')`.
**Indexes.** `ix_users_email (email) UNIQUE`.

---

### 6.4.16 `user_roles`

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `user_id` | `UUID` | PK part | — | FK → `users.id` CASCADE |
| `role_id` | `UUID` | PK part | — | FK → `roles.id` CASCADE |
| `assigned_at` | `TIMESTAMPTZ` | YES | `now()` | Assignment time |

Composite primary key `(user_id, role_id)` prevents duplicate assignments. This table is the legacy many-to-many path; `users.role` is authoritative.

---

### 6.4.17 `refresh_tokens`

| Column | Type | Nullable | Default | Purpose |
|--------|------|----------|---------|---------|
| `id` | `UUID` | PK | `gen_random_uuid()` | Surrogate key |
| `user_id` | `UUID` | NO | — | FK → `users.id` CASCADE |
| `token_hash` | `VARCHAR(64)` | NO | — | **UNIQUE** SHA-256 hex digest of the plaintext token |
| `expires_at` | `TIMESTAMPTZ` | NO | — | Issue time + `jwt_refresh_expire_days` (7) |
| `revoked_at` | `TIMESTAMPTZ` | YES | `NULL` | Set on logout and on rotation |
| `created_at` | `TIMESTAMPTZ` | YES | `now()` | Issue time |

**Indexes.** `ix_refresh_tokens_token_hash (token_hash) UNIQUE`, `ix_refresh_tokens_user_id (user_id)`.
**Retention.** Rows are never deleted — only marked revoked. The table grows by one row per login and per refresh. See §14.7 for the recommended cleanup job.

## 6.5 Constraint Summary

### 6.5.1 Primary keys

Every table uses a surrogate `UUID` primary key except `user_roles`, which uses the composite natural key `(user_id, role_id)`.

### 6.5.2 Unique constraints and unique indexes

| Object | Table | Columns |
|--------|-------|---------|
| `uq_equipment_machine_id` | `equipment_masters` | `machine_id` |
| `ix_sensor_configurations_device_id` | `sensor_configurations` | `device_id` |
| `ix_plot_config_sensor_id` | `plot_configurations` | `sensor_id` |
| column-level UNIQUE | `measurement_upload_data` | `upload_id` |
| `uq_plot_results_upload_plot_channel_fingerprint` | `plot_results` | `upload_id, plot_type, channel, config_fingerprint` |
| `uq_baseline_plot_results_baseline_plot_channel_fingerprint` | `baseline_plot_results` | `baseline_id, plot_type, channel, config_fingerprint` |
| column-level UNIQUE | `feature_definitions` | `code` |
| `uq_measurement_channel_feature` | `measurement_channel_features` | `upload_id, channel, feature_code` |
| `uq_measurement_channel_feature_trend` | `measurement_channel_feature_trends` | `upload_id, channel, feature_code, segment_index` |
| `uq_baseline_channel_feature` | `baseline_channel_features` | `baseline_id, channel, feature_code` |
| `ix_roles_name` | `roles` | `name` |
| `ix_users_email` | `users` | `email` |
| `ix_refresh_tokens_token_hash` | `refresh_tokens` | `token_hash` |

### 6.5.3 Check constraints

| Constraint | Table | Definition |
|------------|-------|------------|
| `ck_users_role_allowed` | `users` | `role IN ('super_admin','admin','user')` |

This is the only `CHECK` constraint in the schema. All other value domains (plot types, statuses, machine types, rule types) are enforin application code — Pydantic validators, service-layer constants, or the frontend lookup lists — not in the database.

### 6.5.4 Default values

| Kind | Examples |
|------|----------|
| Server-side (`server_default`) | `gen_random_uuid()` for PKs, `now()` for timestamps, `'pending'` for statuses, `'ready'` for plot status, `'Active'` for `asset_status`, `'manual'` for `source`, `'user'` for `users.role`, `true`/`false` for booleans, `'[]'::jsonb` / `'{}'::jsonb` for JSONB |
| Python-side (ORM `default=`) | `uuid.uuid4` for feature-table PKs, `datetime.utcnow` for `computed_at`, `list`/`dict` for JSONB attributes |

Note the mixture: tables created in migrations 001–009 use `server_default` for IDs, while the feature tables created in 010–011 rely on the Python-side `uuid4` default. Inserting into the feature tables with raw SQL therefore requires an explicit `id`.

### 6.5.5 Complete index inventory (24 indexes)

| Index | Table | Columns | Unique | Purpose |
|-------|-------|---------|--------|---------|
| PK indexes (17) | all tables | primary key | ✔ | Identity lookup |
| `ix_equipment_plant_name` | `equipment_masters` | `plant_name` | — | Plant filter (limited use — see §14.6) |
| `ix_equipment_machine_type` | `equipment_masters` | `machine_type` | — | Type filter |
| `uq_equipment_machine_id` | `equipment_masters` | `machine_id` | ✔ | Asset-code uniqueness + duplicate check |
| `ix_sensor_equipment_id` | `sensor_configurations` | `equipment_id` | — | Sensor list per machine |
| `ix_sensor_configurations_device_id` | `sensor_configurations` | `device_id` | ✔ | Edge acquisition lookup |
| `ix_plot_config_sensor_id` | `plot_configurations` | `sensor_id` | ✔ | Config lookup + one-per-sensor rule |
| `ix_sensor_upload_sensor_id` | `sensor_data_uploads` | `sensor_id` | — | Uploads per sensor |
| `ix_sensor_data_uploads_sensor_id_created_at` | `sensor_data_uploads` | `sensor_id, created_at` | — | Timeline range query + sort |
| `ix_plot_results_upload_id` | `plot_results` | `upload_id` | — | Cache read |
| `ix_plot_results_sensor_id` | `plot_results` | `sensor_id` | — | Sensor-scoped reads |
| `uq_plot_results_*` | `plot_results` | 4 columns | ✔ | Cache identity |
| `ix_measurement_upload_data_sensor_id` | `measurement_upload_data` | `sensor_id` | — | Sensor-scoped reads |
| `ix_sensor_baselines_sensor_id` | `sensor_baselines` | `sensor_id` | — | Baseline list |
| `ix_sensor_baselines_created_at` | `sensor_baselines` | `created_at` | — | Chronological ordering |
| `ix_baseline_plot_results_baseline_id` | `baseline_plot_results` | `baseline_id` | — | Cache read |
| `uq_baseline_plot_results_*` | `baseline_plot_results` | 4 columns | ✔ | Cache identity |
| `ix_feature_threshold_rules_code_machine` | `feature_threshold_rules` | `feature_code, machine_type` | — | Rule resolution |
| `ix_measurement_channel_features_upload` | `measurement_channel_features` | `upload_id` | — | Feature read |
| `uq_measurement_channel_feature` | `measurement_channel_features` | 3 columns | ✔ | One value per feature/channel |
| `ix_measurement_channel_feature_trends_upload` | `measurement_channel_feature_trends` | `upload_id, channel` | — | Trend read (channel-scoped) |
| `uq_measurement_channel_feature_trend` | `measurement_channel_feature_trends` | 4 columns | ✔ | One value per segment |
| `ix_baseline_channel_features_baseline` | `baseline_channel_features` | `baseline_id` | — | Reference read |
| `uq_baseline_channel_feature` | `baseline_channel_features` | 3 columns | ✔ | One value per feature/channel |
| `ix_roles_name` | `roles` | `name` | ✔ | Role lookup by name |
| `ix_users_email` | `users` | `email` | ✔ | Login lookup |
| `ix_refresh_tokens_token_hash` | `refresh_tokens` | `token_hash` | ✔ | Refresh validation |
| `ix_refresh_tokens_user_id` | `refresh_tokens` | `user_id` | — | Bulk revocation |

## 6.6 Triggers, Views, Stored Procedures, Functions

**None of these objects exist in the schema.** A full search of `backend/alembic/versions/` finds no `CREATE TRIGGER`, `CREATE VIEW`, `CREATE FUNCTION`, or `CREATE PROCEDURE` statement. The only database-side executable code invoked anywhere is the built-in `gen_random_uuid()` and `now()` functions used as column defaults.

Everything that would conventionally be a trigger is done in Python:

| Conventional trigger | Where it is done instead |
|----------------------|--------------------------|
| `updated_at` maintenance | SQLAlchemy `onupdate=datetime.utcnow` on `Equipment.updated_at`, `User.updated_at`; explicit assignment in `update_plot_config` |
| Cascading soft-state updates | Explicit `mark_upload_*` functions in `crud/measurement.py` and `crud/feature.py` |
| Single-primary-baseline enforcement | `crud/baseline.py::create_baseline` / `set_baseline_primary` |
| Audit trail | Not implemented (`created_at`/`updated_at` only) |

## 6.7 Normalisation Analysis

The schema is essentially in **Third Normal Form**, with four deliberate, documented denormalisations.

**Normal-form assessment**

| Table group | Form | Reasoning |
|-------------|------|-----------|
| `equipment_masters` | 3NF | All 40 attributes depend on the machine's identity alone. `operating_environment` uses a PostgreSQL array rather than a junction table — strictly a 1NF deviation, but the array is a closed, non-queried lookup set used only for display and filtering in the UI |
| `sensor_configurations`, `plot_configurations` | 3NF | Single-key dependency; the 1:1 with `plot_configurations` is enforced by a unique index |
| `sensor_data_uploads`, `measurement_upload_data` | 3NF (vertical partition) | The heavy `BYTEA`/`JSONB` payload is split into its own table so lifecycle queries never touch it |
| `feature_definitions`, `feature_threshold_rules` | 3NF | Classic reference/rule pair keyed by `code` |
| Feature/trend/plot tables | 3NF w.r.t. their composite business keys | Each non-key column depends on the whole key (`upload_id, channel, feature_code[, segment_index]`) |
| `users`, `roles`, `user_roles`, `refresh_tokens` | 3NF | Standard RBAC shape |

**Intentional denormalisations**

| # | Denormalisation | Rationale | Risk accepted |
|---|-----------------|-----------|---------------|
| 1 | `sensor_id` duplicated on 6 child tables | Enables sensor-scoped queries and cascade deletion without multi-level joins | The value could theoretically diverge from the parent's `sensor_id`; nothing enforces agreement |
| 2 | `plot_results` / `baseline_plot_results` store computed arrays | FFT and Hilbert transforms are far too expensive to run per page view | Stale rows if the algorithm changes without bumping `ALGORITHM_VERSION` |
| 3 | `users.role` alongside `user_roles` | A single scalar avoids a join on every authenticated request and is `CHECK`-constrained | Two sources of truth; `_user_role` prefers the scalar and falls back to the relationship |
| 4 | `sampling_rate_hz`, `fft_lines`, `frequency_max_hz` copied onto every plot row | Makes each cached row self-describing and auditable without reading `plot_configurations` | Redundant storage (negligible relative to the arrays) |

**Missing normalisation, noted honestly.** `plant_name`, `area`, and `line` are free-text strings on every equipment row rather than a normalised plant hierarchy. The plant selector works around this by deriving its options from `SELECT DISTINCT plant_name` over the equipment master (`GET /api/v1/lookups/plants`) and filtering on an exact case-insensitive match, so it does filter real data. But with no plant entity there is nothing to enforce spelling: a typo on one equipment row silently becomes a new plant in the dropdown, and renaming a plant means updating every row carrying the old string.

## 6.8 Data-Volume Model

For one 8-channel capture of 4096 samples per channel:

| Table | Rows | Approximate size |
|-------|------|------------------|
| `sensor_data_uploads` | 1 | < 1 kB |
| `measurement_upload_data` | 1 | file bytes + parsed JSONB (≈ 2 × the CSV size) |
| `plot_results` | 8 channels × 5 plots = **40** | Each row holds two arrays; the time waveform alone is 2 × 4096 numbers |
| `measurement_channel_features` | 8 × 10 = **80** | < 1 kB each |
| `measurement_channel_feature_trends` | 8 × 10 × 32 = **2560** | < 200 B each |
| **Total per capture** | **≈ 2682 rows** | Dominated by `plot_results` JSONB |

Promoting that capture to a baseline adds 1 + 40 + 80 = **121 rows** plus another copy of the file bytes and parsed data.

## 6.9 SQL Examples

The application never issues raw SQL except inside migrations; these queries are the SQL equivalents of what SQLAlchemy generates, and are useful for operational inspection.

**Equipment list with filters (endpoint 8)**
```sql
SELECT count(*) FROM equipment_masters
WHERE plant_name ILIKE '%Pune%' AND machine_type = 'Pump';

SELECT id, plant_name, area, line, machine_name, machine_id,
       machine_type, machine_criticality, manufacturer,
       asset_status, equipment_image_path, created_at
FROM equipment_masters
WHERE plant_name ILIKE '%Pune%' AND machine_type = 'Pump'
ORDER BY created_at DESC
OFFSET 0 LIMIT 20;
```

**Timeline query (endpoint 30) — uses `ix_sensor_data_uploads_sensor_id_created_at`**
```sql
SELECT * FROM sensor_data_uploads
WHERE sensor_id = $1
  AND created_at >= $2::date
  AND created_at <= ($3::date + time '23:59:59.999999')
ORDER BY created_at DESC
OFFSET 0 LIMIT 50;
```

**Stored-data probe for a whole page in one round trip**
```sql
SELECT upload_id FROM measurement_upload_data
WHERE upload_id IN ($1, $2, $3, ...);
```

**Plot cache read (endpoint 32)**
```sql
SELECT * FROM plot_results
WHERE upload_id = $1
  AND config_fingerprint = $2
  AND status = 'ready'
  AND channel = $3
ORDER BY channel, plot_type;
```

**Feature read with definition names (endpoint 35)**
```sql
SELECT f.channel, f.feature_code, d.name AS feature_name,
       f.value, f.unit, f.status, f.metadata, f.computed_at
FROM measurement_channel_features f
JOIN feature_definitions d ON d.code = f.feature_code
WHERE f.upload_id = $1 AND f.channel = $2
ORDER BY f.channel, f.feature_code;
```

**Baseline comparison (endpoint 37)**
```sql
SELECT u.feature_code, u.channel,
       u.value AS upload_value,
       b.value AS baseline_value,
       CASE WHEN b.value > 1e-30
            THEN 100.0 * u.value / b.value END AS percent_of_baseline,
       u.status
FROM measurement_channel_features u
LEFT JOIN baseline_channel_features b
       ON b.baseline_id = $2
      AND b.channel = u.channel
      AND b.feature_code = u.feature_code
WHERE u.upload_id = $1 AND u.channel = $3;
```

**Trend series for one channel (endpoint 36)**
```sql
SELECT feature_code, segment_index, time_s, value
FROM measurement_channel_feature_trends
WHERE upload_id = $1 AND channel = $2
ORDER BY feature_code, segment_index;
```

**Threshold rule resolution**
```sql
-- machine-specific first
SELECT * FROM feature_threshold_rules
WHERE is_active = true AND machine_type = 'Pump';
-- fall back to global
SELECT * FROM feature_threshold_rules
WHERE is_active = true AND machine_type IS NULL;
```

**Refresh-token validation**
```sql
SELECT rt.*, u.*
FROM refresh_tokens rt
JOIN users u ON u.id = rt.user_id
WHERE rt.token_hash = $1;
-- then: revoked_at IS NULL, expires_at > now(), u.is_active
```

**Operational queries**
```sql
-- Uploads whose pipeline did not complete
SELECT id, original_filename, parse_status, plots_status, features_status,
       parse_error, plots_error, features_error, created_at
FROM sensor_data_uploads
WHERE parse_status <> 'parsed'
   OR plots_status  <> 'ready'
   OR features_status <> 'ready'
ORDER BY created_at DESC;

-- Sensors with more than one primary baseline (integrity check)
SELECT sensor_id, count(*) FROM sensor_baselines
WHERE is_primary GROUP BY sensor_id HAVING count(*) > 1;

-- Distinct cached fingerprints per upload (cache-churn indicator)
SELECT upload_id, count(DISTINCT config_fingerprint) AS fingerprints
FROM plot_results GROUP BY upload_id HAVING count(DISTINCT config_fingerprint) > 1;

-- Largest tables
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
```

## 6.10 Performance Considerations (database)

| Consideration | Detail |
|---------------|--------|
| Cache-first reads | Plot endpoints read `plot_results` instead of recomputing; only a fingerprint change or an incomplete plot-type set triggers computation |
| Bulk writes | `bulk_save_objects` for the 80 + 2560 feature/trend rows avoids per-object ORM overhead |
| Batched existence probe | `get_stored_upload_ids` uses one `IN` query per page instead of one query per row |
| Eager loading | Every user read uses `joinedload(User.roles)`; refresh validation uses a nested `joinedload` down to `User.roles` |
| Composite indexes matched to access paths | `(sensor_id, created_at)` for the timeline; `(upload_id, channel)` for trends; `(feature_code, machine_type)` for rules |
| TOAST | Large `BYTEA`/`JSONB` values are stored out of line and compressed automatically |
| `pool_pre_ping` | Prevents stale-connection errors at the cost of one extra round trip per checkout |
| Known weaknesses | `ILIKE '%…%'` cannot use a B-tree index; `plot_results` rows are read whole (both arrays) even when only one axis is needed; `refresh_tokens` grows unboundedly; per-page KPI counts in the equipment list are computed from the current page, not the whole table |

## 6.11 Backup and Recovery

The repository contains no backup automation. The recoverable state is:

| Asset | Location | Recovery |
|-------|----------|----------|
| Database | Docker volume `postgres_data` | `pg_dump`/`pg_restore` or a volume snapshot |
| Uploaded images | Docker volume `uploads_data` → `/app/uploads` | Volume snapshot. **Not** reconstructible from the database |
| Measurement files and parsed JSON | `uploads_data` → `/app/uploads/measurements` | **Reconstructible**: `measurement_upload_data.file_content` and `.parsed_data` hold the same information. `sensor_baselines` likewise |
| Schema | `backend/alembic/versions` | `alembic upgrade head` recreates the structure |

Because the parsed JSON sidecar is only a cache of `measurement_upload_data.parsed_data`, losing the measurements directory does not lose data — but `get_or_load_all_plots` reads the **file**, not the database, so plot reads for pre-existing uploads would fail with `"Upload has no parsed data"` until the sidecar is regenerated. Feature computation is unaffected because `_load_parsed_for_upload` prefers the database.

## 6.12 Migration Runbook

```bash
# apply everything
cd backend && alembic upgrade head

# inspect
alembic current
alembic history --verbose

# step back one revision
alembic downgrade -1

# regenerate a revision after changing models
alembic revision --autogenerate -m "description"
```

In Docker the backend image runs `alembic upgrade head && uvicorn app.main:app`, so migrations are applied automatically on every container start.

**Downgrade coverage.** Every revision implements `downgrade()`. Revisions 010 and 011 guard their downgrades with existence checks, so they are safe to run against a partially migrated database. Note that `downgrade` of 001 drops both initial tables and therefore all data.

## 6.13 Data Dictionary Quick Reference

| Table | Rows per capture | Primary access path | Cascade parent |
|-------|------------------|---------------------|----------------|
| `equipment_masters` | — | `id`, `machine_id`, filters | — |
| `sensor_configurations` | — | `equipment_id`, `device_id` | `equipment_masters` |
| `plot_configurations` | — | `sensor_id` | `sensor_configurations` |
| `sensor_data_uploads` | 1 | `(sensor_id, created_at)` | `sensor_configurations` |
| `measurement_upload_data` | 1 | `upload_id` | `sensor_data_uploads` |
| `plot_results` | 40 | `(upload_id, fingerprint, channel)` | `sensor_data_uploads` |
| `measurement_channel_features` | 80 | `upload_id` | `sensor_data_uploads` |
| `measurement_channel_feature_trends` | 2560 | `(upload_id, channel)` | `sensor_data_uploads` |
| `sensor_baselines` | 0 or 1 | `sensor_id`, `is_primary` | `sensor_configurations` |
| `baseline_plot_results` | 0 or 40 | `baseline_id` | `sensor_baselines` |
| `baseline_channel_features` | 0 or 80 | `baseline_id` | `sensor_baselines` |
| `feature_definitions` | 10 (static) | `code` | — |
| `feature_threshold_rules` | 10 (static) | `(feature_code, machine_type)` | — |
| `users` / `roles` / `user_roles` / `refresh_tokens` | — | `email` / `name` / composite / `token_hash` | — |

## 6.14 End-to-End Database Flow

The canonical request path from browser to disk and back:

```mermaid
flowchart TD
    A["Frontend component<br/>useQuery / useMutation"] --> B["src/api/*.ts<br/>axios + Bearer"]
    B --> C["FastAPI router<br/>routers/*.py"]
    C --> D["Pydantic request model<br/>schemas/*.py"]
    D --> E["Service layer<br/>services/*.py"]
    E --> F["CRUD layer<br/>crud/*.py"]
    F --> G["SQLAlchemy Session<br/>database.py"]
    G --> H[("PostgreSQL")]
    H --> G
    G --> F
    F --> E
    E --> I["Pydantic response model"]
    I --> C
    C --> B
    B --> J["Normaliser<br/>feature-api-normalize.ts"]
    J --> K["React Query cache"]
    K --> A
```

Worked example — reading the FFT spectrum of channel 2 of an upload:

```mermaid
sequenceDiagram
    autonumber
    participant UI as DetailedAnalysisTab
    participant Q as React Query
    participant AX as axios 'api'
    participant RT as get_all_plots
    participant MC as crud.measurement
    participant PS as plot_storage
    participant PG as plot_generator
    participant SP as signal_processing
    participant DB as PostgreSQL
    participant FS as Filesystem

    UI->>Q: queryKey ["plots","upload",id,2]
    Q->>AX: GET /uploads/{id}/plots?channel=2
    AX->>RT: HTTP + Bearer
    RT->>MC: get_upload_by_id
    MC->>DB: SELECT sensor_data_uploads WHERE id = ?
    RT->>MC: get_plot_config_by_sensor
    MC->>DB: SELECT plot_configurations WHERE sensor_id = ?
    RT->>PS: get_or_load_all_plots(cfg, channel=2)
    PS->>PS: compute_config_fingerprint(cfg)
    PS->>FS: load_parsed_data(parsed_data_path)
    PS->>MC: get_plot_results(upload, fingerprint, channel=2)
    MC->>DB: SELECT plot_results ...
    alt cache hit with the complete plot-type set
        DB-->>PS: 5 rows
    else miss or incomplete
        PS->>PG: generate_plot × channels × types
        PG->>SP: compute_fft_spectrum / hilbert / rms …
        PS->>DB: DELETE old fingerprint rows, INSERT new rows, COMMIT
        PS->>MC: mark_upload_plots_ready
        PS->>MC: get_plot_results (re-read)
    end
    PS->>MC: get_plot_results(all channels) → available_channels
    PS-->>RT: AllPlotsOut (ordered by enabled_plots)
    RT-->>AX: 200 JSON
    AX-->>Q: cache under the query key
    Q-->>UI: plots[] → buildDiagnosticChartOption → ECharts
```

---

# 7.0 Authentication & Security

## 7.1 Authentication Model

| Property | Value |
|----------|-------|
| Scheme | Bearer token (`Authorization: Bearer <jwt>`) |
| Access token | JWT, HS256, 30-minute default lifetime |
| Refresh token | Opaque random string, 7-day default lifetime, stored **hashed** |
| Session storage (client) | `sessionStorage` — cleared when the browser tab closes |
| Server session state | Only `refresh_tokens`; access tokens are stateless |
| Password hashing | bcrypt via `passlib.CryptContext(schemes=["bcrypt"], deprecated="auto")` |
| Identity claim | `sub` = `users.id` (UUID string) |

### 7.1.1 Access-token payload

```json
{
  "sub": "3f2a1c8e-...-9d",
  "exp": 1780000000,
  "type": "access",
  "roles": ["super_admin"]
}
```

`decode_access_token` verifies the signature and expiry via `jose.jwt.decode`, then applies an additional guard: `if payload.get("type") != "access": raise JWTError("Invalid token type")`. This makes it impossible to present a token minted for another purpose as an access token.

**The `roles` claim is informational only.** `get_current_user` ignores it and re-reads the user from the database on every request, so a role change or a deactivation takes effect immediately rather than at the next token refresh.

### 7.1.2 Refresh-token design

| Aspect | Implementation | Security property |
|--------|----------------|-------------------|
| Generation | `secrets.token_urlsafe(48)` | 384 bits from a CSPRNG |
| Storage | `sha256(token)` hex in `refresh_tokens.token_hash` | A database dump does not yield usable tokens |
| Lookup | By hash, on a unique index | Constant-time index lookup, no plaintext comparison |
| Revocation | `revoked_at` timestamp | Server-side invalidation, unlike a JWT |
| Rotation | Every refresh revokes the presented token and issues a new one | Replay of a used token fails |
| Bulk revocation | `revoke_all_user_refresh_tokens(user_id)` exists in `crud/user.py` | Available for "sign out everywhere"; **no endpoint calls it today** |

## 7.2 Authorisation Model

### 7.2.1 Role hierarchy

| Role | Read | Write | Settings page | Source of truth |
|------|------|-------|---------------|-----------------|
| `super_admin` | ✔ | ✔ | ✔ | `users.role` |
| `admin` | ✔ | ✔ | ✔ | `users.role` |
| `user` | ✔ | ✘ (403) | ✘ (redirect to `/unauthorized`) | `users.role` |

Legacy role names are collapsed defensively: `plant_admin` and `engineer` → `admin`; anything unrecognised → `user`.

### 7.2.2 Enforcement points

```mermaid
flowchart TD
    A[Request] --> B["Router dependency<br/>get_current_user"]
    B -->|401| Z1[Reject]
    B --> C{Write route?}
    C -->|no| D[Handler]
    C -->|yes| E["require_write_access<br/>_user_role in WRITE_ROLES?"]
    E -->|no → 403| Z2[Reject]
    E -->|yes| D

    subgraph CLIENT["Client-side (defence in depth, not a control)"]
        F["ProtectedRoute roles=[...] → /unauthorized"]
        G["Sidebar filters NAV_ITEMS by hasRole"]
        H["canWrite gates buttons and inputs"]
    end
```

The client-side checks are **usability affordances only**. Every mutating endpoint independently enforces `require_write_access`, so bypassing the UI does not bypass authorisation.

### 7.2.3 Client-side gating inventory

| Location | Gate |
|----------|------|
| `App.tsx` | `ALL_ROLES` on Dashboard/Equipment/Analysis; `WRITE_ROLES` on equipment create/edit; `ADMIN_ROLES` on Settings |
| `Sidebar.tsx` | `NAV_ITEMS.filter(i => hasRole(i.roles))` — Settings is hidden for role `user` |
| `EquipmentMasterList.tsx` | `canWrite` hides Add / Edit / Delete |
| `VibrationAnalysis.tsx` | `canWrite` disables the file input and upload button, and shows "Read-only users cannot upload sensor data." |
| `DetailedAnalysisTab.tsx` | `canWrite` disables Save Plot Configuration |
| `AnalysisSummaryPanel.tsx` | "Save as baseline" rendered only when `canWrite` |
| `BaselineManagementPanel.tsx` | "Set as Primary" rendered only when `canWrite` |

## 7.3 Sessions and Cookies

The platform uses **no cookies and no server-side sessions**. Tokens live in `sessionStorage` and are attached by an axios request interceptor.

| Option | Chosen | Consequence |
|--------|--------|-------------|
| `sessionStorage` | ✔ | Cleared on tab close; not shared across tabs; not sent automatically, so CSRF is structurally impossible |
| `localStorage` | ✘ | Would survive restarts but widen the XSS exfiltration window |
| `httpOnly` cookie | ✘ | Would be XSS-proof for token theft but require CSRF defences |

`allow_credentials=True` is set on the CORS middleware even though no cookies are used — harmless but unnecessary.

## 7.4 Password Storage

| Property | Value |
|----------|-------|
| Algorithm | bcrypt (`passlib` + `bcrypt` 4.0.1) |
| Cost factor | passlib default (12 rounds for bcrypt) |
| Salt | Generated per hash by bcrypt, embedded in the digest |
| Column | `users.password_hash VARCHAR(255)` |
| Verification | `pwd_context.verify(plain, hash)` — constant-time within bcrypt |
| Upgrade path | `deprecated="auto"` lets passlib mark older schemes for rehash if a scheme is ever added |
| Plaintext | Never stored, never logged. `Login.tsx` clears the password state immediately after a successful sign-in |
| Policy | **No complexity, length, rotation, or reuse policy is enforced** — only `min_length=1` at the API boundary |

## 7.5 Encryption

| Layer | Status |
|-------|--------|
| At rest | Not implemented. `file_content` is stored as plain `BYTEA`; no column-level encryption; no `pgcrypto` usage |
| In transit | Not configured in this repository. Everything is HTTP: nginx listens on 4173 without TLS, Uvicorn on 8000 without certificates, and CORS origins are all `http://`. TLS is expected to be terminated by an upstream proxy in production |
| Application-level hashing | bcrypt for passwords, SHA-256 for refresh tokens, SHA-256 for configuration fingerprints (non-security use) |
| Secrets | Supplied through environment variables; committed `.env` contains development values (see §7.11) |

## 7.6 Role and Permission Management

There is **no user-management API**. Accounts are created only by the startup seeding routine:

```mermaid
flowchart TD
    A[Application starts] --> B[lifespan hook]
    B --> C{super_admin exists?}
    C -->|yes| D[Clear stale must_change_password on INITIAL_ADMIN_EMAIL; log; skip]
    C -->|no| E{INITIAL_ADMIN_EMAIL and PASSWORD set?}
    E -->|no| F[Log warning; no admin created]
    E -->|yes| G["create_user(role_names=['super_admin'])"]
    B --> H[seed_role_users]
    H --> I{SEED_ADMIN_* set and email unused?}
    I -->|yes| J["create_user(role_names=['admin'])"]
    H --> K{SEED_USER_* set and email unused?}
    K -->|yes| L["create_user(role_names=['user'])"]
```

`create_user` writes both the scalar `users.role` (via `primary_role`) and the `user_roles` rows, keeping the two representations consistent for seeded accounts.

**Development accounts documented in the API description** (`main.py`):

| Role | Email | Password | Access |
|------|-------|----------|--------|
| `super_admin` | `admin@vibration.com` | `Admin@2024` | Full read + write |
| `admin` | `plantadmin@vibration.com` | `PlantAdmin@2024` | Read + write |
| `user` | `viewer@vibration.com` | `Viewer@2024` | Read only (GET) |

Only the first is seeded by the committed `.env` (`INITIAL_ADMIN_*`); the other two require `SEED_ADMIN_*` / `SEED_USER_*` to be set, which the committed `.env` does not do.

## 7.7 Security Filters and Middleware

| Control | Status | Detail |
|---------|--------|--------|
| CORS | ✔ | Explicit six-origin allow-list; no wildcard |
| Bearer extraction | ✔ | `HTTPBearer(auto_error=False)` + custom 401 with `WWW-Authenticate: Bearer` |
| Write-role guard | ✔ | `require_write_access` |
| Request validation | ✔ | Pydantic on every body, query, and path parameter |
| Security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options) | ✘ | No middleware sets them |
| Rate limiting | ✘ | See §7.10 |
| Request-size limit | Partial | Enforced per endpoint after the body is read, not at the server edge |
| Audit logging | ✘ | Only `created_at`/`updated_at` columns and one equipment-create log line |
| Trusted-host / host-header validation | ✘ | Not configured |

## 7.8 CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:4173", "http://localhost:3000",
        "http://127.0.0.1:5173", "http://127.0.0.1:4173", "http://127.0.0.1:3000",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
```

Enumerating origins rather than using `["*"]` is correct and is the reason `allow_credentials=True` is even legal (browsers reject the wildcard-plus-credentials combination). **Production deployment requires adding the real frontend origin to this list** — otherwise every browser request fails preflight.

## 7.9 CSRF

No CSRF protection exists, and none is required by the current design: the credential is a header value read from `sessionStorage`, and a cross-site request cannot read another origin's `sessionStorage` or forge the `Authorization` header. Cookie authentication would immediately create a CSRF requirement.

## 7.10 Rate Limiting and Brute-Force Resistance

| Aspect | Status |
|--------|--------|
| Server-side rate limiting | **None.** No `slowapi`, no reverse-proxy limit, no per-IP counter |
| Account lockout | **None** |
| Client-side deterrent | `Login.tsx` counts failures and displays "Multiple failed login attempts detected." after five — cosmetic only, resets on reload |
| Natural cost barrier | bcrypt at 12 rounds makes each verification ~100 ms of CPU, which throttles online guessing but also makes the login endpoint a cheap denial-of-service target |
| Timing side channel | `authenticate_user` returns early for an unknown email (no bcrypt run) but performs a full bcrypt verification for a known email, so response time distinguishes the two cases |

## 7.11 Input Validation and Injection Resistance

### 7.11.1 SQL injection

**Not reachable through the application code.** Every query is built with SQLAlchemy ORM expressions, which parameterise values. Even pattern matching is parameterised:

```python
query.filter(Equipment.plant_name.ilike(f"%{plant_name}%"))
```
The f-string builds the *pattern*, which is then bound as a parameter — the value never becomes SQL text. Type coercion adds a second barrier: `equipment_id: UUID` rejects anything that is not a UUID with a 422 before any database access.

The only raw SQL in the repository is inside migrations (`op.execute`, `sa.text`) with either literal statements or bound parameters — not user input.

### 7.11.2 Cross-site scripting

| Vector | Mitigation |
|--------|------------|
| Rendered data | React escapes all interpolated text by default |
| `dangerouslySetInnerHTML` | **Not used anywhere** in `src/` |
| Chart tooltips | ECharts tooltip formatters build HTML strings containing `plot.title`, `plot.x_label`, `plot.y_label`, and numeric values. These originate from server-generated constants (`"FFT Spectrum"`, `"Frequency (Hz)"`), not user input, so no injection path exists today. If plot titles ever became user-editable, these formatters would need escaping |
| Uploaded filenames | Rendered as text only |
| SVG assets | Static files in the repository, not user-supplied |
| Content-Security-Policy | Not set |

### 7.11.3 File-upload validation

| Check | Images | Measurements |
|-------|--------|--------------|
| Extension | Derived for storage | `.csv` / `.pdf` accepted |
| MIME | Allow-list of four image types | Allow-list of four text/PDF types (OR extension match) |
| Size | 10 MB | 50 MB |
| Content inspection | **None** — no magic-byte check | Parser rejects unparseable content with 422 |
| Filename handling | Only the extension is taken from the user; the stored name is `{equipment_id}.{ext}` | Stored name is `{upload_id}.csv|pdf` |
| Path traversal | Not possible — filenames are server-generated UUIDs |
| Execution risk | Files are written to `uploads/`, served only through `FileResponse` for images; measurement files are never served back |

The size check happens **after** `await file.read()`, so a 1 GB upload is fully buffered in memory before rejection. See §14.9.

### 7.11.4 Other validation surfaces

| Surface | Validation |
|---------|-----------|
| Numeric ranges | `channel` 0–31, `channel_count` 1–32, `fft_lines` 64–65536, `page_size` ≤ 100/200 |
| Enumerations | `data_type`, plot types, `users.role` (DB `CHECK`) |
| Emails | Pydantic `EmailStr` on login; the frontend also regex-checks |
| Dates | `from_date ≤ to_date` explicit check |
| UUIDs | Path/query type coercion |
| Business invariants | `active_channel < channel_count`; unique `machine_id`; `danger > warning` (client-side, Settings) |

## 7.12 Security Posture Summary

**Implemented well**

1. bcrypt password hashing with per-hash salts.
2. Hashed, revocable, single-use-rotating refresh tokens.
3. Short-lived access tokens with an explicit `type` guard.
4. Database re-validation of the user on every request, so deactivation is immediate.
5. Server-side authorisation independent of the UI.
6. Parameterised queries throughout — no SQL injection surface.
7. React's default escaping and no `dangerouslySetInnerHTML`.
8. Explicit CORS origin allow-list.
9. Credential errors that do not reveal whether an account exists.
10. `sessionStorage` rather than `localStorage`, and no cookies (hence no CSRF surface).

**Gaps, stated plainly**

| # | Gap | Impact | Location |
|---|-----|--------|----------|
| 1 | Development secrets committed to `.env` | `SECRET_KEY=vibration-platform-secret-key-change-in-production`, `POSTGRES_PASSWORD`, `INITIAL_ADMIN_PASSWORD=Admin@2024`, and the pgAdmin password are all in the repository. Anyone with repository access can forge JWTs against any deployment reusing these values | `.env` (note: `.gitignore` lists `.env`, so it is ignored going forward, but the file is present in the working tree) |
| 2 | No TLS in the shipped configuration | Tokens and passwords traverse plain HTTP | `nginx.conf`, compose ports, CORS origins |
| 3 | No rate limiting or lockout | Online password guessing and login-endpoint DoS are unmitigated | Application-wide |
| 4 | No password policy | A one-character password is accepted | `schemas/auth.py` |
| 5 | No password-change endpoint | `must_change_password` can force a redirect that the user cannot satisfy — a lock-out condition | `routers/auth.py`, `pages/ChangePassword.tsx` |
| 6 | No security headers | No CSP, HSTS, `X-Frame-Options`, or `X-Content-Type-Options` | `main.py` |
| 7 | No user-management API | Roles can only be changed by direct SQL | — |
| 8 | Refresh tokens accumulate forever | Unbounded table growth; revoked rows are never purged | `refresh_tokens` |
| 9 | Access tokens survive logout | Logout revokes only the refresh token; the access token stays valid for up to 30 minutes | `routers/auth.py::logout` |
| 10 | Size limits applied after full buffering | Memory-exhaustion vector on large uploads | `upload_image`, `upload_sensor_data`, `upload_baseline` |
| 11 | Login timing distinguishes known from unknown emails | Account enumeration by response time | `auth_service.authenticate_user` |
| 12 | Sensor update does not verify parent ownership | `PUT /equipment/{A}/sensors/{S}` succeeds even when sensor `S` belongs to equipment `B` | `routers/equipment.py::update_sensor` |
| 13 | Edge acquisition endpoints require a user token | An edge device must hold user credentials; there is no device-credential concept | `routers/measurements.py` |
| 14 | No audit trail | Who created, changed, or deleted an asset is not recorded | Schema-wide |

**Priority remediation order**

1. Rotate every secret and remove the committed `.env` from history; inject secrets at deploy time.
2. Terminate TLS and add HSTS plus the standard security headers.
3. Add rate limiting on `/auth/login`, `/auth/token`, and `/auth/refresh`.
4. Implement `POST /auth/change-password` (and enforce a password policy) so `must_change_password` is satisfiable.
5. Add the real production origin to the CORS allow-list.
6. Stream uploads with an edge-level body-size limit.
7. Add a scheduled purge of expired/revoked refresh tokens.
8. Add an ownership check to the sensor update and delete routes.
