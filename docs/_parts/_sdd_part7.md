---

# 11.0 Configuration Documentation

## 11.1 Configuration file inventory

| File | Scope | Consumed by |
|------|-------|-------------|
| `.env` | Whole stack | Docker Compose, backend `Settings`, Vite |
| `.gitignore` | Repository | git |
| `docker-compose.yml` | Orchestration | Docker Compose |
| `package-lock.json` (root) | — | Empty stub; no root `package.json` exists |
| `backend/requirements.txt` | Backend deps | pip |
| `backend/Dockerfile` | Backend image | Docker |
| `backend/.dockerignore` | Backend build context | Docker |
| `backend/alembic.ini` | Migration runner | Alembic |
| `backend/setup_and_run.bat` | Windows dev bootstrap | Developer |
| `frontend/package.json` | Frontend deps + scripts | npm |
| `frontend/vite.config.ts` | Dev server + build | Vite |
| `frontend/tsconfig.json`, `tsconfig.node.json` | Type checking | TypeScript |
| `frontend/tailwind.config.js` | Design tokens | Tailwind |
| `frontend/postcss.config.js` | CSS pipeline | PostCSS |
| `frontend/index.html` | SPA shell | Vite |
| `frontend/nginx.conf` | Production serving | nginx |
| `frontend/Dockerfile`, `.dockerignore` | Frontend image | Docker |
| `frontend/setup_and_run.bat` | Windows dev bootstrap | Developer |
| `START.md` | Runbook | Developer |

**Not present:** ESLint, Prettier, EditorConfig, Husky, `pytest.ini`/`pyproject.toml`, `.github/workflows`, `Makefile`, `.nvmrc`, `.python-version`.

## 11.2 `.env` — complete reference

```ini
# PostgreSQL
POSTGRES_USER=vibration_user
POSTGRES_PASSWORD=vibration_pass_2024
POSTGRES_DB=vibration_platform
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# pgAdmin
PGADMIN_EMAIL=admin@vibration.com
PGADMIN_PASSWORD=admin2024

# Backend
DATABASE_URL=postgresql://vibration_user:vibration_pass_2024@postgres:5432/vibration_platform
SECRET_KEY=vibration-platform-secret-key-change-in-production
UPLOAD_DIR=uploads
INITIAL_ADMIN_EMAIL=admin@vibration.com
INITIAL_ADMIN_PASSWORD=Admin@2024
INITIAL_ADMIN_NAME=Platform Administrator

# Frontend
VITE_API_BASE_URL=http://localhost:8000
```

| Variable | Consumer | Required | Default | Notes |
|----------|----------|----------|---------|-------|
| `POSTGRES_USER` | Compose (postgres, healthcheck, `DATABASE_URL`) | ✔ | — | |
| `POSTGRES_PASSWORD` | Compose | ✔ | — | |
| `POSTGRES_DB` | Compose | ✔ | — | |
| `POSTGRES_HOST` | Documentation only | ✘ | — | Not referenced by any code |
| `POSTGRES_PORT` | Documentation only | ✘ | — | Not referenced by any code |
| `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` | Compose (pgadmin) | ✔ for pgAdmin | — | |
| `DATABASE_URL` | `Settings.database_url`, `alembic/env.py` | **✔ — startup fails without it** | none | Host must be `postgres` in Docker, `localhost` when running the backend outside Docker |
| `SECRET_KEY` | `Settings.secret_key`; JWT fallback | ✘ | `change-in-production` | |
| `JWT_SECRET` | `Settings.jwt_secret` | ✘ | `""` → falls back to `SECRET_KEY` | Referenced by Compose but **absent from the committed `.env`** |
| `UPLOAD_DIR` | `Settings.upload_dir` | ✘ | `uploads` | Compose overrides to `/app/uploads` |
| `MEASUREMENT_UPLOAD_DIR` | `Settings.measurement_upload_dir` | ✘ | `uploads/measurements` | Never set anywhere |
| `MAX_IMAGE_SIZE_MB` | `Settings.max_image_size_mb` | ✘ | `10` | Never set |
| `MAX_PDF_SIZE_MB` | `Settings.max_pdf_size_mb` | ✘ | `50` | Never set |
| `JWT_ALGORITHM` | `Settings.jwt_algorithm` | ✘ | `HS256` | Never set |
| `JWT_ACCESS_EXPIRE_MINUTES` | `Settings` | ✘ | `30` | Never set |
| `JWT_REFRESH_EXPIRE_DAYS` | `Settings` | ✘ | `7` | Never set |
| `INITIAL_ADMIN_EMAIL` / `_PASSWORD` / `_NAME` | `seed_super_admin` | ✘ | `""`/`""`/`Platform Administrator` | Without the first two, no admin is created and a warning is logged |
| `SEED_ADMIN_EMAIL` / `_PASSWORD` / `_NAME` | `seed_role_users` | ✘ | `""`/`""`/`Plant Administrator` | Referenced by Compose; **absent from the committed `.env`** |
| `SEED_USER_EMAIL` / `_PASSWORD` / `_NAME` | `seed_role_users` | ✘ | `""`/`""`/`Read Only User` | Same |
| `VITE_API_BASE_URL` | `api/client.ts` | ✘ | `http://localhost:8000` | Inlined at **build** time, not runtime |

> Because `Settings.Config.extra = "ignore"`, the Postgres and pgAdmin keys are safely ignored by the backend even though they share the file.

## 11.3 `docker-compose.yml`

```yaml
services:
  postgres:   # postgres:16, port 5433:5432, volume postgres_data, healthcheck pg_isready 10s/5s/5
  pgadmin:    # dpage/pgadmin4:latest, port 5050:80, volume pgadmin_data, depends_on postgres
  backend:    # build ./backend, port 8000, env_file .env + 11 explicit env vars,
              # volume uploads_data:/app/uploads, depends_on postgres condition service_healthy
  frontend:   # build ./frontend target preview, build arg VITE_API_BASE_URL=http://localhost:8000,
              # port 4173, depends_on backend
volumes: postgres_data, pgadmin_data, uploads_data
```

Explicit backend environment overrides: `DATABASE_URL` (rebuilt from the Postgres variables with host `postgres`), `SECRET_KEY`, `UPLOAD_DIR=/app/uploads`, `JWT_SECRET`, `INITIAL_ADMIN_*` (3), `SEED_ADMIN_*` (3), `SEED_USER_*` (3).

**Port summary**

| Service | Host | Container |
|---------|------|-----------|
| PostgreSQL | 5433 | 5432 |
| pgAdmin | 5050 | 80 |
| Backend | 8000 | 8000 |
| Frontend | 4173 | 4173 |

## 11.4 `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y gcc libjpeg-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

`gcc` supports building any wheel-less dependency; `libjpeg-dev` and `zlib1g-dev` are Pillow's image-codec headers. Requirements are copied before the source so the dependency layer caches across code changes. Migrations run before the server starts, so a fresh volume is schema-complete on first boot.

## 11.5 `frontend/Dockerfile`

Three targets:

| Target | Base | Purpose | Command |
|--------|------|---------|---------|
| `base` | `node:20-alpine` | `npm ci` + copy source | — |
| `dev` | `base` | Hot-reload dev server | `npm run dev -- --host 0.0.0.0 --port 5173` |
| `build` | `base` | `ARG VITE_API_BASE_URL` → `npm run build` | — |
| `preview` | `nginx:alpine` | Serve `/app/dist` with the SPA fallback | `nginx -g "daemon off;"` |

The header comments document both usage modes verbatim, including the Windows volume-mount form (`-v "%cd%:/app" -v /app/node_modules`).

## 11.6 `frontend/nginx.conf`

```nginx
server {
    listen 4173;
    root /usr/share/nginx/html;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
}
```

`try_files … /index.html` is required for client-side routing — without it a refresh on `/analysis` would return 404. No gzip, cache-control, or security headers are configured.

## 11.7 `frontend/vite.config.ts`

| Setting | Value | Note |
|---------|-------|------|
| `plugins` | `react()` | JSX transform + fast refresh |
| `optimizeDeps.include` | `["plotly.js-dist-min", "react-plotly.js"]` | **Stale** — neither package is installed or imported; a leftover from the pre-ECharts implementation. Harmless but should be removed |
| `resolve.alias` | `@` → `./src` | Matches the `tsconfig` path mapping |
| `server.port` | 5173 | |
| `server.proxy["/api"]` | `http://localhost:8000`, `changeOrigin: true` | Available but unused, because all calls use the absolute `baseURL` |

## 11.8 `frontend/tsconfig.json`

| Option | Value | Effect |
|--------|-------|--------|
| `target` / `lib` | ES2020 / ES2020 + DOM + DOM.Iterable | Modern output |
| `module` / `moduleResolution` | ESNext / bundler | Vite-native resolution |
| `jsx` | `react-jsx` | No `import React` requirement (though the code imports it anyway) |
| `strict` | `true` | Full strictness including `strictNullChecks` |
| `noUnusedLocals` / `noUnusedParameters` | `false` | Unused symbols do not fail the build |
| `noFallthroughCasesInSwitch` | `true` | Guards the plot-type switch |
| `noEmit` | `true` | Vite emits; `tsc` only type-checks |
| `skipLibCheck` | `true` | Skips `.d.ts` checking for speed |
| `isolatedModules` | `true` | Required for esbuild transpilation |
| `paths` | `@/*` → `./src/*` | Absolute imports |

`tsconfig.node.json` is a `composite` project covering only `vite.config.ts`.

## 11.9 `frontend/tailwind.config.js`

| Section | Contents |
|---------|----------|
| `darkMode` | `["class"]` — toggled by `ThemeContext` on `<html>` |
| `content` | `./index.html`, `./src/**/*.{ts,tsx,js,jsx}` |
| `colors` | Semantic tokens bound to CSS variables + literal palettes: `signal` (light/dark/deep), `cta` (default/hover/foreground), `brand` (7 shades), `machine` (healthy/warning/critical/offline), `page.accent` |
| `backgroundImage` | 3 signal gradients (horizontal, vertical, hover) |
| `borderRadius` | `lg`/`md`/`sm` from `--radius`; `xl` 0.75rem; `2xl` 1rem |
| `fontFamily` | Inter → system-ui → sans-serif |
| `fontSize` | 10 enlarged steps plus a custom `overline` |
| `boxShadow` | `card`, `card-hover`, `nav`, `logo`, `signal`, `cta`, `cta-hover` |
| `keyframes` / `animation` | `fade-up` (0.35 s ease-out) |
| `plugins` | `tailwindcss-animate` |

## 11.10 `backend/alembic.ini`

`script_location = alembic`, `prepend_sys_path = .`, `version_path_separator = os`, and a placeholder `sqlalchemy.url` that `env.py` always overwrites. Logging: root/`sqlalchemy` at WARN, `alembic` at INFO, stderr handler, format `%(levelname)-5.5s [%(name)s] %(message)s`.

## 11.11 `.gitignore`

Ignores `.env`, `__pycache__/`, `*.pyc`, `*.pyo`, `.venv/`, `venv/`, `node_modules/`, `dist/`, `build/`, `.DS_Store`, `uploads/`, `*.egg-info/`, `.pytest_cache/`, `alembic/versions/__pycache__/`.

> `.env` is ignored, yet the file exists in the working tree with real development credentials — see security gap #1 in §7.12.

## 11.12 Configuration precedence

```mermaid
flowchart TD
    A[Process environment] -->|highest| C[Settings instance]
    B[.env in the process CWD] -->|lower| C
    D[Field defaults in config.py] -->|lowest| C
    E[Compose environment block] --> A
    F[Compose env_file .env] --> A
```

For the frontend, `VITE_API_BASE_URL` is resolved at **build** time: the Compose build arg becomes an `ENV` in the build stage, is inlined by Vite into the bundle, and cannot be changed without rebuilding.

---

# 12.0 Deployment Guide

## 12.1 Deployment topology

```mermaid
graph TB
    subgraph HOST["Docker host"]
        subgraph NET["Compose network"]
            PG[("postgres:16<br/>vibration_platform_db")]
            PA["pgadmin4<br/>vibration_platform_pgadmin"]
            BE["backend<br/>python:3.11-slim + uvicorn"]
            FE["frontend<br/>nginx:alpine"]
        end
        V1[(postgres_data)] --- PG
        V2[(pgadmin_data)] --- PA
        V3[(uploads_data)] --- BE
    end
    U[Browser] -->|:4173| FE
    U -->|:8000| BE
    A[Admin] -->|:5050| PA
    BE -->|postgres:5432| PG
    PA --> PG
```

## 12.2 Local development (from `START.md`)

**Step 1 — database**
```bash
docker-compose up -d          # postgres on 5433, pgAdmin on http://localhost:5050
```

**Step 2 — backend**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # Windows;  source .venv/bin/activate on POSIX
pip install -r requirements.txt
copy ..\.env .env              # cp ../.env .env on POSIX
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
API at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

> When running the backend outside Docker, `DATABASE_URL` must point at `localhost:5433`, not `postgres:5432`, because the container hostname does not resolve on the host and the published port is 5433.

**Step 3 — frontend**
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

**Step 4** — open `http://localhost:5173` and sign in with `admin@vibration.com` / `Admin@2024`.

Windows convenience scripts `backend/setup_and_run.bat` and `frontend/setup_and_run.bat` perform steps 2 and 3 respectively.

## 12.3 Full container deployment

```bash
docker-compose up -d --build
```

Startup order: `postgres` → healthcheck passes → `backend` (runs `alembic upgrade head`, then seeds users on lifespan) → `frontend`.

| Endpoint | URL |
|----------|-----|
| Frontend | `http://localhost:4173` |
| Backend | `http://localhost:8000` |
| Swagger | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |
| Health | `http://localhost:8000/health` |
| pgAdmin | `http://localhost:5050` |
| PostgreSQL | `localhost:5433` |

Common operations:
```bash
docker-compose logs -f backend
docker-compose restart backend
docker-compose down                 # stop, keep volumes
docker-compose down -v              # stop and DESTROY all data
docker-compose exec backend alembic current
docker-compose exec postgres psql -U vibration_user -d vibration_platform
```

## 12.4 Frontend build process

```mermaid
flowchart LR
    A[npm run build] --> B["tsc — type-check only (noEmit)"]
    B -->|errors| C[Build fails]
    B -->|clean| D[vite build]
    D --> E["Rollup: bundle, tree-shake, minify,<br/>inline import.meta.env.VITE_*"]
    E --> F[dist/ — index.html + hashed assets]
    F --> G[COPY --from=build /app/dist → nginx html root]
```

Because type-checking gates the bundle, a type error blocks deployment — this is the project's strongest automated quality gate.

## 12.5 Production readiness checklist

The repository ships a development configuration. Before production use:

| # | Action | Reason |
|---|--------|--------|
| 1 | Replace every secret (`SECRET_KEY`, `JWT_SECRET`, `POSTGRES_PASSWORD`, `PGADMIN_PASSWORD`, `INITIAL_ADMIN_PASSWORD`) and remove `.env` from the working tree | §7.12 gap 1 |
| 2 | Terminate TLS at a reverse proxy; add HSTS and the standard security headers | §7.12 gap 2 |
| 3 | Add the production origin to the CORS allow-list in `main.py` | Otherwise every request fails preflight |
| 4 | Rebuild the frontend with the production `VITE_API_BASE_URL` | The value is baked in at build time |
| 5 | Run Uvicorn with multiple workers or behind Gunicorn (`-k uvicorn.workers.UvicornWorker`) | Feature extraction is CPU-bound and blocks a single worker (§14.3) |
| 6 | Remove the pgAdmin service or restrict it to an internal network | It exposes full database access on 5050 |
| 7 | Do not publish PostgreSQL to the host | Only the backend needs it |
| 8 | Add rate limiting on the auth endpoints | §7.10 |
| 9 | Configure database backups of `postgres_data` and file backups of `uploads_data` | §6.11 |
| 10 | Add log aggregation and an uptime check against `/health` | No observability exists today |
| 11 | Set container resource limits | A large upload can consume significant memory (§14.9) |
| 12 | Schedule a purge of expired/revoked refresh tokens | §14.7 |

## 12.6 Reverse-proxy example

```nginx
server {
    listen 443 ssl http2;
    server_name sensovibe.example.com;
    ssl_certificate     /etc/ssl/certs/sensovibe.crt;
    ssl_certificate_key /etc/ssl/private/sensovibe.key;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;

    location / {                       # SPA
        proxy_pass http://frontend:4173;
    }
    location /api/ {                   # API
        proxy_pass http://backend:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 60M;      # above the 50 MB application limit
        proxy_read_timeout 180s;       # feature computation can exceed 60s
    }
}
```

`client_max_body_size` and `proxy_read_timeout` are the two settings most likely to cause confusing failures if left at nginx defaults (1 MB and 60 s).

## 12.7 Cloud deployment notes

The stack is portable to any container platform. Points that need attention:

| Concern | Guidance |
|---------|----------|
| Managed PostgreSQL (RDS, Cloud SQL, Azure Database) | Set `DATABASE_URL` to the managed endpoint; drop the `postgres` service; keep `pool_pre_ping=True` (it protects against proxy-idle disconnects) |
| Object storage instead of a volume | `uploads/` is written with `open()`/`os.remove()` and read with `FileResponse`; switching to S3/Blob requires code changes in `upload_image`, `get_image`, `delete_image`, `upload_sensor_data`, and `plot_generator.load_parsed_data` |
| Statelessness | Two of the three filesystem uses are already redundant with the database (`measurement_upload_data`, `sensor_baselines`). Only equipment images are filesystem-only |
| Horizontal scaling | Safe for reads. Concurrent writes to the same upload could duplicate plot computation, but the unique constraint on `plot_results` prevents duplicate rows |
| Migrations in multi-replica deployments | `alembic upgrade head` runs in the image `CMD`; with several replicas starting together, run migrations as a separate init job instead |
| Health probe | `GET /health` — liveness. A readiness probe should additionally verify database connectivity |

## 12.8 CI/CD

**No CI/CD configuration exists in the repository** — there is no `.github/workflows`, `.gitlab-ci.yml`, `Jenkinsfile`, or `azure-pipelines.yml`.

A pipeline matching the current toolchain would be:

```mermaid
flowchart LR
    A[Push / PR] --> B[Frontend: npm ci]
    B --> C["npm run build (tsc gate + bundle)"]
    A --> D[Backend: pip install -r requirements.txt]
    D --> E[alembic upgrade head against a throwaway DB]
    E --> F[python scripts/test_auth_phase1.py]
    C --> G[docker build frontend --target preview]
    F --> H[docker build backend]
    G --> I[Push images]
    H --> I
    I --> J[Deploy: migrate, then roll out]
```

---

# 13.0 Testing Documentation

## 13.1 Current state — stated plainly

The repository contains **one** executable test artefact: `backend/scripts/test_auth_phase1.py`. There is no test framework configuration, no test directory, no frontend test tooling, and no coverage measurement.

| Test type | Present | Evidence |
|-----------|---------|----------|
| Backend unit tests | ✘ | No `pytest`/`unittest` in `requirements.txt`; no `tests/` directory |
| Backend integration tests | Partial | `scripts/test_auth_phase1.py` uses `fastapi.testclient.TestClient` |
| Frontend unit tests | ✘ | No Vitest/Jest/Testing Library in `package.json` |
| Frontend E2E tests | ✘ | No Playwright/Cypress |
| API contract tests | ✘ | — |
| Load tests | ✘ | — |
| Coverage | ✘ | `.gitignore` mentions `.pytest_cache/`, indicating an intent that was never realised |

## 13.2 The existing smoke test

`backend/scripts/test_auth_phase1.py`:

```python
db = SessionLocal(); seed_super_admin(db); db.close()
client = TestClient(app)

r  = client.post("/api/v1/auth/login", json={"email": "admin@vibration.com", "password": "Admin@2024"})
assert r.status_code == 200
r2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
assert r2.status_code == 200 and "super_admin" in r2.json()["roles"]
r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}); assert r3.status_code == 200
r4 = client.post("/api/v1/auth/logout",  json={"refresh_token": r3.json()["refresh_token"]}); assert r4.status_code == 204
r5 = client.get("/api/v1/auth/me");       assert r5.status_code == 401
print("ALL TESTS PASSED")
```

Run with `cd backend && python scripts/test_auth_phase1.py`. It covers login, `/me`, refresh rotation, logout, and unauthenticated rejection. **It runs against the configured database**, so it must not be pointed at production.

## 13.3 Implicit quality gates

| Gate | Mechanism | Catches |
|------|-----------|---------|
| TypeScript strict compilation | `npm run build` runs `tsc` before bundling | Type errors, null-safety violations, wrong props, bad API shapes |
| Zod schemas | Runtime form validation | Malformed user input |
| Pydantic models | Runtime API validation | Malformed requests and non-conforming responses |
| Database constraints | PK, FK, UNIQUE, CHECK | Referential and domain violations |
| Alembic linearity | Single revision chain 001→011 | Divergent schema history |

## 13.4 Manual test plan

### 13.4.1 Authentication

| ID | Case | Steps | Expected |
|----|------|-------|----------|
| TA-01 | Valid login | admin@vibration.com / Admin@2024 | Redirect to `/`, toast, user menu shows SUPER ADMIN |
| TA-02 | Wrong password | Any user, bad password | 401, inline error, no redirect |
| TA-03 | Unknown email | nobody@x.com | Same message as TA-02 |
| TA-04 | Empty fields | Submit blank | Client-side field errors, no request sent |
| TA-05 | Malformed email | `abc` | "Enter a valid email address" |
| TA-06 | Caps Lock | Enable, focus password | Warning appears |
| TA-07 | Five failures | Repeat TA-02 ×5 | Warning banner appears |
| TA-08 | Deep-link preservation | Open `/analysis` unauthenticated, log in | Lands on `/analysis` |
| TA-09 | Token expiry | Wait 30 min, act | Silent refresh; work continues |
| TA-10 | Refresh expiry | Revoke/expire refresh, act | "Session expired" toast, redirect to `/login` |
| TA-11 | Logout | User menu → Sign Out | Redirect to `/login`; back button does not restore the session |
| TA-12 | Tab close | Close and reopen the tab | Login required (`sessionStorage`) |

### 13.4.2 Authorisation

| ID | Case | Expected |
|----|------|----------|
| TZ-01 | Role `user` opens `/settings` directly | Redirect to `/unauthorized` |
| TZ-02 | Role `user` views the equipment register | Add/Edit/Delete absent |
| TZ-03 | Role `user` `POST /equipment/` via curl | 403 "Insufficient permissions" |
| TZ-04 | Role `user` on the analysis page | Upload disabled with an explanatory note |
| TZ-05 | Role `admin` everywhere | Full write access; Settings visible |
| TZ-06 | No token on a protected endpoint | 401 with `WWW-Authenticate: Bearer` |
| TZ-07 | Tampered JWT | 401 "Invalid or expired token" |
| TZ-08 | Deactivated user with a valid token | 401 "User not found or inactive" |

### 13.4.3 Equipment

| ID | Case | Expected |
|----|------|----------|
| TE-01 | Create with all fields | 201; appears first in the register |
| TE-02 | Create with minimum fields | 201 (schema defaults permit it) |
| TE-03 | Duplicate `machine_id` | 409; error toast with the server message |
| TE-04 | Blank `machine_id` on two machines | Both succeed (`NULL` ≠ `NULL`) |
| TE-05 | Machine type = Gearbox | Ratio and gear-teeth fields appear |
| TE-06 | Machine type = Fan | Fan-blades field appears |
| TE-07 | Machine type = Motor | Pole-count field appears |
| TE-08 | Drive type = Gear Drive on a Pump | Gearbox fields appear |
| TE-09 | Add 3 sensors | All persist and appear on the review tab |
| TE-10 | Upload a 12 MB image | 400 "Image exceeds 10MB limit" |
| TE-11 | Upload a `.txt` renamed to `.jpg` | 400 (MIME check) |
| TE-12 | Edit and save | Values persist; `updated_at` changes |
| TE-13 | Delete | Row disappears; sensors and all measurements cascade |
| TE-14 | Search by partial name | Filters the current page |
| TE-15 | Filter by type | Server refetch; `total` changes |
| TE-16 | Paginate with 25+ machines | Prev/Next appear; range label correct |
| TE-17 | Tab away and back mid-wizard | Entered values are retained |

### 13.4.4 Measurement and analysis

| ID | Case | Expected |
|----|------|----------|
| TM-01 | Upload a valid 8-channel CSV | 201; all three statuses reach `ready` |
| TM-02 | Upload a valid PDF | Parsed via table extraction |
| TM-03 | Upload a `.docx` | 400 "File must be a CSV or PDF" |
| TM-04 | Upload a 60 MB file | 400 "File exceeds 50MB limit" |
| TM-05 | Upload a CSV with no numeric rows | 422; `parse_status = failed`; error visible |
| TM-06 | Header declares ch0–ch6 but 8 requested | 7 channels used (detected wins) |
| TM-07 | Rows shorter than the channel count | Padded with 0.0; no error |
| TM-08 | All timestamps identical | Time axis derived from the sample index |
| TM-09 | Epoch timestamps | Converted to relative seconds, or index time if the span is implausible |
| TM-10 | Switch channels | Plots reload for the new channel; cache reused |
| TM-11 | Change sampling rate and save config | Next plot read recomputes (new fingerprint) |
| TM-12 | Select a capture on the timeline | All four tabs update |
| TM-13 | Narrow the date range | Timeline refetches; day chips rebuild |
| TM-14 | Invalid range (from > to) | 400 from the API |
| TM-15 | Zoom a chart | Statistics recompute for the visible window |
| TM-16 | Double-click a chart | Zoom resets |
| TM-17 | Toggle thresholds | Lines, shading, and crossing markers appear/disappear |
| TM-18 | Fullscreen a chart | Chart fills the viewport and resizes correctly; Escape exits |
| TM-19 | Export PNG | File downloads with the expected name |
| TM-20 | Open Statistics | 12 rows consistent with the waveform |

### 13.4.5 Features and health

| ID | Case | Expected |
|----|------|----------|
| TF-01 | Open Status (Health) after upload | 5 summary cards + overview + 10-row table |
| TF-02 | No baseline exists | `percent_baseline` features show `No Baseline` |
| TF-03 | Create a baseline, revisit | Those features are evaluated; comparison table populates |
| TF-04 | Change the comparison baseline | Comparison refetches; % differences change |
| TF-05 | First-ever trend load | "Computing factor trends…" then 10 cards; 3-second polling stops at `ready` |
| TF-06 | Feature computation fails | Explicit failure message with a re-upload instruction |
| TF-07 | Switch channel | All feature panels reload for the new channel |
| TF-08 | API returns fewer than 10 features | Table still shows 10 rows, missing ones marked `No Baseline` |

### 13.4.6 Baselines

| ID | Case | Expected |
|----|------|----------|
| TB-01 | Save an upload as baseline with "set as primary" | Created; badge shows Primary; previous primary loses the badge |
| TB-02 | Save a second baseline without primary | Both listed; primary unchanged |
| TB-03 | Set a different baseline as primary | Exactly one Primary badge remains |
| TB-04 | Load a baseline for analysis | Charts render baseline data; "Loaded for Analysis" badge shows |
| TB-05 | Search baselines by name/date | List filters |
| TB-06 | Filter by status | Only matching baselines remain |
| TB-07 | Delete the source upload | Baseline survives; `source_upload_id` becomes null |
| TB-08 | Promote an upload lacking stored data | 422 with the re-upload instruction |

### 13.4.7 Settings

| ID | Case | Expected |
|----|------|----------|
| TS-01 | Edit a channel row and save | Persisted; overview tile turns green |
| TS-02 | Partially configure a channel | Tile shows amber "Partial" |
| TS-03 | Add rows up to 8 | Add button disables at the maximum |
| TS-04 | Delete a channel | Remaining rows renumber sequentially |
| TS-05 | Threshold with danger ≤ warning, enabled | Inline error; save blocked with an error toast |
| TS-06 | Valid thresholds | Matrix cell turns green "Saved" |
| TS-07 | Cancel after edits | Draft reverts to the saved state |
| TS-08 | Reload the browser | Settings restore from `localStorage` |
| TS-09 | Corrupt the `localStorage` value | Defaults load with an error banner |

### 13.4.8 Responsive and accessibility

| ID | Case | Expected |
|----|------|----------|
| TR-01 | 375 px width | No horizontal page scroll; tables scroll internally |
| TR-02 | 768 px | Grids collapse appropriately; search hidden below `md` |
| TR-03 | 1920 px | Full multi-column layouts |
| TR-04 | Collapse the sidebar | Width animates to 80 px; icons remain |
| TR-05 | Keyboard tab order | Focus rings visible on all interactive elements |
| TR-06 | `prefers-reduced-motion` | Card lift and login animations suppressed |

## 13.5 Recommended automated test suite

**Backend (`pytest` + `httpx`)**

| Layer | Targets |
|-------|---------|
| Unit — DSP | `compute_fft_spectrum` against a synthetic sine (peak at the right bin, amplitude within tolerance); `resolve_time_seconds` for all five branches; `compute_trend_plot` segment count |
| Unit — features | Each of the 10 extractors against known signals; `_estimate_shaft_hz` band behaviour; division guards at `1e-30` |
| Unit — thresholds | All five `rule_type` branches including `no_baseline` |
| Unit — parser | Comma/tab/semicolon/space, BOM, quoted cells, short rows, header detection, encoding fallbacks, zero-row failure |
| Unit — fingerprint | Stability across key order; change on each fingerprinted field; invariance to `active_channel`/`channel_count` |
| Integration | Full upload → plots → features pipeline on a fixture CSV; cache hit on a second read; recompute after a config change; baseline promotion copying features |
| Security | 401/403 matrix for every endpoint × role; refresh rotation and replay; inactive-user rejection |

**Frontend (Vitest + Testing Library)**

| Layer | Targets |
|-------|---------|
| Unit | `computeChartStatistics`, `downsampleWaveformSeries` (peak preservation), `computeSymmetricYAxisBounds`, `resolveVibrationFeatureKey` aliases, `enrichFeatureStatusItems` (always 10), `normalizeUploadFeaturesResponse` key aliasing, `isThresholdValid`, `migrateThresholds`, `groupUploadsByDay` |
| Component | `ProtectedRoute` decision matrix, `FeatureStatusTable` grouping, `GraphToolbar` action visibility, `SaveBaselineModal` validation |
| Integration | Login flow with a mocked API, upload flow, 401→refresh→retry through the interceptor |

**E2E (Playwright)** — the eleven user flows in §9.

---

# 14.0 Performance & Optimisation

## 14.1 Implemented optimisations

| # | Optimisation | Location | Effect |
|---|--------------|----------|--------|
| 1 | Content-addressed plot cache | `plot_results`, `baseline_plot_results` | Eliminates repeat FFT/Hilbert computation across page views and users |
| 2 | Bulk inserts | `bulk_save_objects` in `feature_storage` | ~2640 rows per upload written without per-object ORM overhead |
| 3 | Batched existence probe | `get_stored_upload_ids` | One `IN` query per page instead of N queries |
| 4 | Eager loading | `joinedload(User.roles)` everywhere | Removes the N+1 on every authenticated request |
| 5 | Composite indexes aligned to access paths | `(sensor_id, created_at)`, `(upload_id, channel)`, `(feature_code, machine_type)` | Index-only filtering and ordering |
| 6 | `pool_pre_ping` | `database.py` | Avoids stale-connection failures |
| 7 | Server-side pagination | equipment and uploads | Bounded result sets |
| 8 | Two-tier client cache | React Query `staleTime` 30 s (60 s for trend plots) | Suppresses duplicate requests |
| 9 | Min/max bucket decimation | `downsampleWaveformSeries` (8192 pts) | Renders 100k+ sample waveforms without losing peaks |
| 10 | Uniform decimation for spectra | `downsampleSeries` (2000 pts) | Smooth spectrum rendering |
| 11 | Adaptive line width | `applyAdaptiveLineWidth` | Keeps dense traces legible while zoomed |
| 12 | `memo` on chart components | `DiagnosticChart`, `EchartsDiagnosticChart` | Avoids re-rendering charts on unrelated state changes |
| 13 | `useMemo` on option builders | All chart wrappers | Rebuilds ECharts options only when inputs change |
| 14 | `notMerge` + `lazyUpdate` | `EchartsGraphViewport` | Predictable, batched chart updates |
| 15 | Tabs hidden rather than unmounted | `EquipmentForm`, `VibrationAnalysis` | Preserves chart instances, zoom state, and uncontrolled input values |
| 16 | Status polling only while pending | `useUploadFactorTrends.refetchInterval` | Stops polling as soon as `features_status` is terminal |
| 17 | Canvas renderer | `opts={{renderer:"canvas"}}` | Faster than SVG for tens of thousands of points |
| 18 | Docker layer caching | Requirements/package files copied before source | Fast rebuilds |
| 19 | Vite production bundling | Rollup tree-shaking + minification | Small, cache-busted assets |
| 20 | TOAST for large payloads | PostgreSQL automatic | Wide rows stay cheap when the blob columns are not selected |

## 14.2 Not implemented

| Item | Status | Consequence |
|------|--------|-------------|
| Route-level code splitting (`React.lazy`) | ✘ | Every page, including ECharts, is in the initial bundle |
| `manualChunks` in the Vite config | ✘ | No vendor/app split |
| Virtualised lists/tables | ✘ | A 200-row upload list renders every row |
| Image lazy loading | ✘ | Only one image type is served |
| HTTP cache headers | ✘ | nginx serves without `Cache-Control`; plot responses are not cacheable by the browser |
| gzip/brotli | ✘ | Not enabled in `nginx.conf`; JSON plot payloads are highly compressible |
| Service worker / offline | ✘ | — |
| Redis or in-process cache | ✘ | The database is the only cache |
| Background job queue | ✘ | See §14.3 |
| Streaming uploads | ✘ | See §14.9 |
| Connection-pool tuning | ✘ | SQLAlchemy defaults (pool size 5, overflow 10) |

## 14.3 The dominant performance characteristic

Feature extraction is the most expensive operation in the system, and it runs **synchronously inside the HTTP request**.

Cost model per channel:

```
extract_segment_trends → for each of 10 feature codes:
    for each of ~32 segments:
        extract_channel_features(segment)   → FFT + Hilbert + statistics
= 10 × 32 = 320 full extractions per channel
```

Each extraction performs `scipy.fft.fft` and `scipy.signal.hilbert` on the segment. For an 8-channel capture that is **2560 FFT+Hilbert pairs** on top of the whole-signal extraction. This is why:

* the API sets no server timeout but the client allows 120 s;
* the UI polls `features_status` every 3 seconds and shows "first load may take a few seconds";
* `ensure_upload_features_ready` short-circuits when rows already exist.

**Impact.** With Uvicorn's default single worker, a large upload blocks the event loop for the duration — other requests queue behind it.

**Optimisation opportunities, in order of value:**

1. **Compute once per segment, not once per feature.** `extract_channel_features` already returns all ten features. Restructuring `extract_segment_trends` to call it once per segment and fan the results out reduces the work by **10×** with no change in output.
2. Move the pipeline to a background worker (Celery/RQ/`BackgroundTasks`) so `POST /upload` returns immediately with `features_status = "pending"` — the UI already handles that state.
3. Run multiple Uvicorn workers so CPU-bound work does not block other requests.
4. Cache the FFT per segment across the features that need it (`fft_band_energy`, `amplitude_1x/2x/3x`, `noise_floor` all recompute the same spectrum).

## 14.4 Payload sizes

| Response | Approximate size | Note |
|----------|------------------|------|
| `GET /uploads/{id}/plots` (4096-sample waveform + 4 more plots) | Hundreds of kB of JSON | Two float arrays per plot; not gzipped by default |
| `GET /uploads/{id}/factor-trends` | ~10 × 32 × 2 floats | Small |
| `GET /uploads/{id}/features` | 10 rows | Small |
| `GET /equipment/` (20 items) | Small | Uses the slim `EquipmentListItem` projection |

Enabling gzip at the proxy is the single highest-value network optimisation, because float-array JSON compresses extremely well.

## 14.5 Frontend rendering

| Aspect | Behaviour |
|--------|-----------|
| Initial bundle | React + Router + Query + axios + ECharts + framer-motion + lucide + date-fns + zod + react-hook-form, all eagerly loaded |
| Chart mount | ECharts initialises a canvas per chart; the Status tab can mount 10 compact charts simultaneously |
| Resize handling | Triple-fire (`immediate`, `rAF`, `+150 ms`) plus `ResizeObserver` per chart |
| Fullscreen | Four scheduled resizes plus a `ResizeObserver` |
| Animation | `framer-motion` entrance animations on cards, staggered table rows (`delay: i × 0.03`) |

The heaviest screen is Status (Health) with ten `HealthMetricCard` instances, each owning an ECharts instance and a `ResizeObserver`.

## 14.6 Known query weaknesses

| Query | Weakness | Remedy |
|-------|----------|--------|
| `plant_name ILIKE '%value%'` | Leading wildcard prevents B-tree index use → sequential scan | `pg_trgm` GIN index, or a prefix-only match |
| Equipment KPI counts | Computed from the current page in the frontend, so "Critical Assets" reflects 20 rows, not the fleet | Add server-side aggregate counts |
| `plot_results` reads | Always selects both full arrays | Add a projection when only metadata is needed |
| `refresh_tokens` | Grows by one row per login and per refresh, never pruned | Scheduled `DELETE WHERE expires_at < now() OR revoked_at IS NOT NULL` |
| Trend rows | ~2560 rows per upload accumulate indefinitely | Retention policy or aggregation for old captures |

## 14.7 Recommended maintenance jobs

```sql
-- Purge dead refresh tokens (safe: revoked or expired only)
DELETE FROM refresh_tokens
WHERE revoked_at IS NOT NULL OR expires_at < now() - interval '7 days';

-- Drop superseded plot caches (keep only the current fingerprint per upload)
DELETE FROM plot_results pr
WHERE pr.config_fingerprint <> (
  SELECT p2.config_fingerprint FROM plot_results p2
  WHERE p2.upload_id = pr.upload_id ORDER BY p2.computed_at DESC LIMIT 1
);

-- Routine statistics maintenance
VACUUM ANALYZE measurement_channel_feature_trends;
VACUUM ANALYZE plot_results;
```

## 14.8 Scalability profile

| Dimension | Current ceiling | Limiting factor |
|-----------|-----------------|-----------------|
| Concurrent users (read) | High | Cached plots; stateless auth |
| Concurrent uploads | Low | Synchronous CPU-bound pipeline on a single worker |
| Captures per sensor | High | Indexed, paginated, date-filtered |
| Channels per capture | 32 | Schema and validation limit |
| Samples per capture | Bounded by the 50 MB file limit and memory | Whole file and all arrays held in memory during processing |
| Equipment records | High | Indexed and paginated |
| Horizontal scaling | Read-safe | Filesystem-backed equipment images are the only true local state |

## 14.9 Memory profile of an upload

```
await file.read()                    → entire file in memory (up to 50 MB)
parse_measurement_text               → Python lists of floats (~3–8× the CSV size)
save_parsed_data                     → JSON serialisation of the same structure
save_upload_data                     → bytes + parsed dict passed to the ORM
persist_all_plot_results             → per-channel numpy arrays + result lists
persist_upload_features_and_trends   → scalars + trends dicts + ~2640 ORM objects
```

Peak memory can be several multiples of the uploaded file size. The size check occurs **after** the full read, so a rejected 200 MB upload is still buffered first. Recommended mitigations: enforce the limit at the reverse proxy (`client_max_body_size`), stream to disk in chunks, and set container memory limits.

---

# 15.0 Troubleshooting & Error Handling

## 15.1 Error-handling architecture

```mermaid
flowchart TD
    subgraph FE["Frontend"]
        A1[Zod / react-hook-form] --> A2[Field errors]
        A3[axios interceptor] --> A4{401?}
        A4 -->|yes| A5[refresh + retry] -->|fails| A6["auth:session-expired → toast → /login"]
        A4 -->|no| A7[reject]
        A7 --> A8[React Query isError]
        A8 --> A9[Inline message + optional Retry]
        A10[Mutation onError] --> A11[Error toast]
    end
    subgraph BE["Backend"]
        B1[Pydantic] -->|422| OUT
        B2[Auth dependency] -->|401/403| OUT
        B3[Handler guards] -->|400/404/409| OUT
        B4[Service ValueError] --> B5[Router → 422] --> OUT
        B6[Stage exception] --> B7[mark_*_failed → status column] --> B8[200/201 with error recorded]
        B9[Unhandled] -->|500| OUT
    end
    OUT([HTTP response]) --> A3
```

## 15.2 Backend error catalogue

| Status | Message | Endpoint(s) | Cause |
|--------|---------|-------------|-------|
| 400 | `File must be an image (JPEG, PNG, WebP, GIF)` | equipment image | Disallowed MIME |
| 400 | `Image exceeds 10MB limit` | equipment image | Size |
| 400 | `File must be a CSV or PDF` | upload | Disallowed type |
| 400 | `File exceeds 50MB limit` | upload | Size |
| 400 | `Invalid plot type. Allowed: [...]` | single plot endpoints | Unknown plot type |
| 400 | `from_date must be on or before to_date` | uploads list | Range inversion |
| 401 | `Not authenticated` | any protected | Missing or non-bearer credentials |
| 401 | `Invalid or expired token` | any protected | Signature, expiry, `type`, or `sub` failure |
| 401 | `User not found or inactive` | any protected | Deleted or deactivated user |
| 401 | `Incorrect email or password` | login, token | Bad credentials |
| 401 | `Invalid refresh token` / `Refresh token revoked` / `Refresh token expired` / `User inactive` | refresh | Refresh validation |
| 403 | `Insufficient permissions` | all write endpoints | Role `user` |
| 404 | `Equipment not found` | equipment routes | Unknown id |
| 404 | `Sensor not found` | sensor, configure, uploads, baselines | Unknown id |
| 404 | `Image not found` / `Image file not found on disk` | image download | No path, or path missing |
| 404 | `Lookup 'X' not found` | lookups | Unknown key |
| 404 | `Plot configuration not found for this sensor` | configure GET/PUT | No profile |
| 404 | `No sensor found with device_id 'X'. …` | acquisition | Unmapped device |
| 404 | `Upload not found` | upload routes | Unknown id |
| 404 | `Baseline not found` / `No primary baseline set for this sensor` / `No primary baseline for this sensor` | baseline routes, compare | Missing baseline |
| 404 | `Parsed upload not found` | from-upload | Upload absent or unparsed |
| 404 | `Plot {type} not found` | baseline single plot | Type not produced |
| 409 | `Machine ID 'X' already exists` | equipment create | Duplicate |
| 422 | Pydantic detail array | any | Schema violation |
| 422 | `PDF parsing failed: …` | upload | Parser failure |
| 422 | `Upload not parsed: …` | plots, features, trends | Wrong lifecycle state |
| 422 | `Feature compute failed: …` | features, trends, compare | Extraction failure |
| 422 | `Parse failed: …` / `Baseline plot compute failed: …` | baseline upload / from-upload | Baseline pipeline |
| 422 | `Upload file data not in DB. Re-upload the file after migration 007.` | from-upload | Pre-migration upload |
| 422 | `Upload has no parsed data` | plots | Missing `parsed_data_path` |
| 500 | Generic | any | Unhandled exception (no global handler) |

## 15.3 Frontend error surfaces

| Surface | Message pattern | Location |
|---------|-----------------|----------|
| Login | Server `detail`, else "Sign in failed. Please check your credentials." | `Login.tsx` |
| Session | "Session expired" toast + redirect | `AuthContext` |
| Equipment save | Server `detail`, else "Failed to save equipment. Please try again." | `EquipmentForm` |
| Equipment delete | "Failed to delete equipment." | `EquipmentMasterList` |
| Equipment list | "Failed to load equipment." + "Make sure the backend is running on port 8000." | `EquipmentMasterList` |
| Equipment detail | "Failed to load equipment." | `EquipmentMaster` |
| Plots | "Failed to load plots: {detail}" or "Try another channel or select a different capture." | `DetailedAnalysisTab` |
| Features | "Unable to load feature data for CH-n." | `StatusHealthTab` |
| Comparison | "Unable to load feature comparison data." + Retry | `FeatureComparisonSection` |
| Trends | Server `detail`, else "Failed to load factor trends. Re-upload the file if features were not computed." | `FeatureTrendCardsSection` |
| Baselines | "Unable to load baselines for this sensor." + Retry | `BaselineManagementPanel` |
| Settings | "Unable to load saved vibration settings. Showing defaults." | `VibrationSettingsModule` |
| Settings validation | "Fix threshold rows where danger must be greater than warning before saving." | `VibrationSettingsModule` |

## 15.4 Diagnostic runbook

| Symptom | Likely cause | Check | Fix |
|---------|--------------|-------|-----|
| Backend exits immediately on start | `DATABASE_URL` unset | Container logs; `env` | Provide `DATABASE_URL`; `copy ..\.env .env` for local runs |
| `could not translate host name "postgres"` | Backend running on the host with the container URL | `DATABASE_URL` | Use `localhost:5433` outside Docker |
| Login returns 401 for the seeded admin | No admin was seeded | Startup logs for "Seeded super admin user" or the warning | Set `INITIAL_ADMIN_EMAIL`/`_PASSWORD` and restart |
| All requests fail with a CORS error | Origin not in the allow-list | Browser console | Add the origin to `main.py` |
| Frontend calls the wrong API host | `VITE_API_BASE_URL` baked at build time | Network tab | Rebuild with the correct value |
| 401 loop on every request | Refresh failing repeatedly | Network tab for `/auth/refresh` | Clear `sessionStorage`, re-login; verify `JWT_SECRET` did not change |
| Upload returns 422 "PDF parsing failed" | Unrecognised layout | The `detail` reports the configured and detected channel counts | Ensure a `timestamp,ch0,ch1,…` header and numeric rows |
| Upload succeeds, no plots | Plot stage failed non-fatally | `plots_status` / `plots_error` on the upload record | Read `plots_error`; verify sample count ≥ 4 |
| Upload succeeds, no features | Feature stage failed | `features_status` / `features_error` | Read `features_error`; re-request `/features` to trigger recompute |
| Trend cards spin forever | `features_status` never becomes terminal | Poll the `/factor-trends` response | Check backend logs for an exception in extraction |
| Plots empty for a channel | Channel not present in the file | `available_channels` in the response | Select an available channel |
| Charts do not resize after fullscreen | Resize race | — | The four scheduled resizes normally cover it; toggling fullscreen again forces a resize |
| Baseline promotion returns 422 | Upload predates migration 007 | `measurement_upload_data` row missing | Re-upload the file |
| Settings lost after reload | `localStorage` cleared or corrupt | DevTools → Application → Local Storage | Reconfigure; the module falls back to defaults with a banner |
| Equipment image 404 | Volume not mounted or file removed | `uploads_data` contents | Re-upload the image |
| Migration fails mid-way | Partially applied 010 | `alembic current` | 010/011 are idempotent — re-run `alembic upgrade head` |
| Slow first analysis load | Cold plot/feature cache | Timing of the first vs second request | Expected; subsequent loads are cached |

## 15.5 Log locations

| Source | Where |
|--------|-------|
| Uvicorn access and error logs | `docker-compose logs backend` (stdout) |
| Seeding messages | Same, logger `uvicorn` |
| Equipment-create trace | Same, `[CREATE_EQUIPMENT] …` |
| Alembic | Same, INFO level |
| PostgreSQL | `docker-compose logs postgres` |
| nginx | `docker-compose logs frontend` |
| Frontend auth trace | Browser console, `[Auth]` prefix, dev builds only |

---

# 16.0 Appendix

## 16.1 Glossary

| Term | Definition |
|------|-----------|
| **Baseline** | A stored reference capture representing known-good machine condition, used as the comparison target for health evaluation |
| **Capture / Upload** | One measurement file ingested for a sensor, with its parsed arrays and derived artefacts |
| **Channel** | One signal stream within a capture (`ch0`, `ch1`, …); typically one sensor axis |
| **Config fingerprint** | A 32-hex-character SHA-256 prefix of the processing parameters, used as the cache key for computed plots |
| **Crest factor** | Peak ÷ RMS; approximately 3 for Gaussian signals, elevated for impulsive faults |
| **DE / NDE** | Drive End / Non-Drive End — the two bearing positions on a rotating machine |
| **Digital twin** | The complete asset master record that gives measurements engineering context |
| **Envelope spectrum** | FFT of the Hilbert envelope; reveals amplitude-modulation sidebands characteristic of bearing defects |
| **Excess kurtosis** | Fourth standardised moment minus 3; ≈ 0 for Gaussian noise, higher for spiky signals |
| **FFT** | Fast Fourier Transform — converts a time signal to its frequency spectrum |
| **Feature** | A scalar descriptor of a channel (one of the ten in the catalogue) |
| **Frequency resolution (Δf)** | `fs / N` — the spacing between FFT bins |
| **Hann window** | A tapering function applied before the FFT to reduce spectral leakage |
| **Hilbert transform** | Produces the analytic signal whose magnitude is the envelope |
| **LOR** | Lines of Resolution — the FFT line count used by edge acquisition |
| **Nyquist frequency** | `fs / 2` — the highest frequency representable at a given sample rate |
| **Orbit / Circular waveform** | Amplitude mapped onto a circle: `x = A·cos θ`, `y = A·sin θ` |
| **Primary baseline** | The baseline flagged as the default comparison target for a sensor |
| **RMS** | Root mean square — the energy-equivalent amplitude |
| **Shaft frequency (1×)** | Rotational frequency in Hz = RPM ÷ 60 |
| **Trend (segment)** | A feature evaluated on successive time segments *within one capture* |
| **1× / 2× / 3×** | Amplitudes at the shaft frequency and its second and third harmonics |

## 16.2 Abbreviations

| Abbrev. | Expansion |
|---------|-----------|
| ADC | Analogue-to-Digital Converter |
| API | Application Programming Interface |
| ASGI | Asynchronous Server Gateway Interface |
| BPFO / BPFI | Ball Pass Frequency Outer / Inner race |
| CM | Condition Monitoring |
| CMMS | Computerised Maintenance Management System |
| CORS | Cross-Origin Resource Sharing |
| CRUD | Create, Read, Update, Delete |
| CSPRNG | Cryptographically Secure Pseudo-Random Number Generator |
| CSRF | Cross-Site Request Forgery |
| DSP | Digital Signal Processing |
| FK / PK | Foreign Key / Primary Key |
| HSTS | HTTP Strict Transport Security |
| IEPE | Integrated Electronics Piezo-Electric |
| IIO | Industrial I/O (Linux subsystem) |
| JSONB | PostgreSQL binary JSON type |
| JWT | JSON Web Token |
| MEMS | Micro-Electro-Mechanical System |
| MVCC | Multi-Version Concurrency Control |
| ORM | Object-Relational Mapper |
| PM | Preventive Maintenance |
| RAG | Retrieval-Augmented Generation |
| RBAC | Role-Based Access Control |
| RTD | Resistance Temperature Detector |
| SPA | Single-Page Application |
| TOAST | The Oversized-Attribute Storage Technique (PostgreSQL) |
| UDP | User Datagram Protocol |
| UUID | Universally Unique Identifier |
| VFD | Variable Frequency Drive |
| XSS | Cross-Site Scripting |

## 16.3 API summary table

| # | Method | Path | Auth | Success | Primary tables |
|---|--------|------|------|---------|----------------|
| 1 | GET | `/health` | Public | 200 | — |
| 2 | POST | `/api/v1/auth/login` | Public | 200 | users, refresh_tokens |
| 3 | POST | `/api/v1/auth/token` | Public | 200 | users, refresh_tokens |
| 4 | POST | `/api/v1/auth/refresh` | Public | 200 | refresh_tokens |
| 5 | POST | `/api/v1/auth/logout` | Public | 204 | refresh_tokens |
| 6 | GET | `/api/v1/auth/me` | Auth | 200 | users, roles |
| 7 | POST | `/api/v1/equipment/` | Write | 201 | equipment_masters, sensor_configurations |
| 8 | GET | `/api/v1/equipment/` | Auth | 200 | equipment_masters |
| 9 | GET | `/api/v1/equipment/{id}` | Auth | 200 | equipment_masters, sensor_configurations |
| 10 | PUT | `/api/v1/equipment/{id}` | Write | 200 | equipment_masters |
| 11 | PATCH | `/api/v1/equipment/{id}` | Write | 200 | equipment_masters |
| 12 | DELETE | `/api/v1/equipment/{id}` | Write | 204 | equipment_masters (+cascade) |
| 13 | POST | `/api/v1/equipment/{id}/image` | Write | 200 | equipment_masters + FS |
| 14 | GET | `/api/v1/equipment/{id}/image` | Auth | 200 | equipment_masters + FS |
| 15 | DELETE | `/api/v1/equipment/{id}/image` | Write | 204 | equipment_masters + FS |
| 16 | GET | `/api/v1/equipment/{id}/sensors` | Auth | 200 | sensor_configurations |
| 17 | POST | `/api/v1/equipment/{id}/sensors` | Write | 201 | sensor_configurations |
| 18 | PUT | `/api/v1/equipment/{id}/sensors/{sid}` | Write | 200 | sensor_configurations |
| 19 | DELETE | `/api/v1/equipment/{id}/sensors/{sid}` | Write | 204 | sensor_configurations (+cascade) |
| 20 | GET | `/api/v1/equipment/{id}/ai-readiness` | Auth | 200 | equipment_masters, sensor_configurations |
| 21 | GET | `/api/v1/lookups/` | Auth | 200 | equipment_masters (`plants` key) |
| 21a | GET | `/api/v1/lookups/plants` | Auth | 200 | equipment_masters |
| 22 | GET | `/api/v1/lookups/{name}` | Auth | 200 | — |
| 23 | POST | `/api/v1/measurements/configure` | Write | 200 | plot_configurations |
| 24 | GET | `/api/v1/measurements/configure/{sensor_id}` | Auth | 200 | plot_configurations |
| 25 | PUT | `/api/v1/measurements/configure/{sensor_id}` | Write | 200 | plot_configurations |
| 26 | GET | `/api/v1/measurements/acquisition` | Auth | 200 | sensor_configurations, plot_configurations |
| 27 | GET | `/api/v1/measurements/acquisition/by-sensor/{sensor_id}` | Auth | 200 | same |
| 28 | GET | `/api/v1/measurements/acquisition/{device_id}` | Auth | 200 | same |
| 29 | POST | `/api/v1/measurements/upload` | Write | 201 | 5 tables + FS |
| 30 | GET | `/api/v1/measurements/uploads` | Auth | 200 | sensor_data_uploads, measurement_upload_data |
| 31 | GET | `/api/v1/measurements/uploads/{id}` | Auth | 200 | same |
| 32 | GET | `/api/v1/measurements/uploads/{id}/plots` | Auth | 200 | plot_results |
| 33 | GET | `/api/v1/measurements/uploads/{id}/plots/{type}` | Auth | 200 | plot_results |
| 34 | GET | `/api/v1/measurements/plot-types` | Auth | 200 | — |
| 35 | GET | `/api/v1/measurements/uploads/{id}/features` | Auth | 200 | measurement_channel_features + rules |
| 36 | GET | `/api/v1/measurements/uploads/{id}/factor-trends` | Auth | 200 | measurement_channel_feature_trends |
| 37 | GET | `/api/v1/measurements/uploads/{id}/features/compare` | Auth | 200 | measurement + baseline features |
| 38 | GET | `/api/v1/baselines` | Auth | 200 | sensor_baselines, baseline_plot_results |
| 39 | GET | `/api/v1/baselines/primary` | Auth | 200 | sensor_baselines |
| 40 | GET | `/api/v1/baselines/{id}` | Auth | 200 | sensor_baselines |
| 41 | PATCH | `/api/v1/baselines/{id}/primary` | Write | 200 | sensor_baselines |
| 42 | POST | `/api/v1/baselines/upload` | Write | 201 | sensor_baselines, baseline_plot_results |
| 43 | POST | `/api/v1/baselines/from-upload/{id}` | Write | 201 | 3 baseline tables |
| 44 | GET | `/api/v1/baselines/{id}/plots` | Auth | 200 | baseline_plot_results |
| 45 | GET | `/api/v1/baselines/{id}/plots/{type}` | Auth | 200 | baseline_plot_results |
| 46 | GET | `/api/v1/baselines/{id}/features` | Auth | 200 | baseline_channel_features |
| 47 | GET | `/api/v1/dashboard/summary` | Auth | 200 | equipment_masters, sensor_configurations, sensor_data_uploads, measurement_channel_features, feature_definitions |

## 16.4 Database summary table

| # | Table | Columns | PK | FKs | Indexes | Purpose |
|---|-------|---------|----|-----|---------|---------|
| 1 | `equipment_masters` | 40 | `id` | — | 3 | Machine master record |
| 2 | `sensor_configurations` | 16 | `id` | 1 | 2 | Measurement point |
| 3 | `plot_configurations` | 11 | `id` | 1 | 1 (unique) | Processing profile |
| 4 | `sensor_data_uploads` | 18 | `id` | 1 | 2 | Capture lifecycle |
| 5 | `measurement_upload_data` | 10 | `id` | 2 | 2 | Durable file + parsed data |
| 6 | `plot_results` | 18 | `id` | 2 | 3 | Plot cache |
| 7 | `sensor_baselines` | 16 | `id` | 2 | 2 | Reference captures |
| 8 | `baseline_plot_results` | 18 | `id` | 2 | 2 | Baseline plot cache |
| 9 | `feature_definitions` | 7 | `id` | — | 1 (unique code) | Feature catalogue |
| 10 | `feature_threshold_rules` | 10 | `id` | 1 | 1 | Evaluation rules |
| 11 | `measurement_channel_features` | 10 | `id` | 3 | 2 | Scalar feature values |
| 12 | `measurement_channel_feature_trends` | 9 | `id` | 3 | 2 | Segment trend values |
| 13 | `baseline_channel_features` | 10 | `id` | 3 | 2 | Reference feature values |
| 14 | `roles` | 4 | `id` | — | 1 (unique) | Role catalogue |
| 15 | `users` | 10 | `id` | — | 1 (unique) + CHECK | Accounts |
| 16 | `user_roles` | 3 | `(user_id, role_id)` | 2 | — | Role assignment |
| 17 | `refresh_tokens` | 6 | `id` | 1 | 2 | Session tokens |

## 16.5 Backend class / module summary

| Type | Name | File | Responsibility |
|------|------|------|----------------|
| Config | `Settings` | `config.py` | Environment-bound configuration |
| Infra | `engine`, `SessionLocal`, `Base`, `get_db` | `database.py` | Persistence plumbing |
| Entity | `Equipment` | `models/equipment.py` | `equipment_masters` |
| Entity | `SensorConfiguration` | `models/sensor.py` | `sensor_configurations` |
| Entity | `PlotConfiguration`, `SensorDataUpload`, `PlotResult`, `MeasurementUploadData`, `SensorBaseline`, `BaselinePlotResult`, `FeatureDefinition`, `FeatureThresholdRule`, `MeasurementChannelFeature`, `MeasurementChannelFeatureTrend`, `BaselineChannelFeature` | `models/measurement.py` | Measurement domain |
| Entity | `Role`, `User`, `UserRole`, `RefreshToken` | `models/user.py` | Identity domain |
| Controller | `routers/auth.py` | 5 endpoints | Authentication |
| Controller | `routers/equipment.py` | 14 endpoints | Asset master |
| Controller | `routers/lookups.py` | 2 endpoints | Reference lists |
| Controller | `routers/measurements.py` | 15 endpoints | Ingestion, plots, features |
| Controller | `routers/baselines.py` | 9 endpoints | Baselines |
| Repository | `crud/equipment.py` | 13 functions | Equipment + sensor access |
| Repository | `crud/measurement.py` | 15 functions | Config + upload + plot access |
| Repository | `crud/baseline.py` | 10 functions | Baseline access |
| Repository | `crud/feature.py` | 11 functions | Feature + rule access |
| Repository | `crud/user.py` | 12 functions | Identity access |
| Service | `auth_service.py` | 9 functions | Hashing, JWT, refresh lifecycle |
| Service | `seed.py` | 3 functions | Idempotent account seeding |
| Service | `pdf_parser.py` | 11 functions | CSV/PDF → channel arrays |
| Service | `signal_processing.py` | 6 functions | The five DSP routines |
| Service | `plot_generator.py` | 6 functions + registry | Plot orchestration |
| Service | `plot_storage.py` | 7 functions | Fingerprinting and caching |
| Service | `baseline_storage.py` | 3 functions | Baseline plot persistence |
| Service | `feature_extraction.py` | 9 functions | Ten features + trends |
| Service | `feature_storage.py` | 6 functions | Evaluation and persistence |
| Service | `threshold_evaluator.py` | `ThresholdRule` + 2 functions | Rule evaluation |
| Service | `acquisition_config.py` | 4 functions | Edge JSON generation |
| Dependency | `dependencies/auth.py` | 4 symbols | AuthN / AuthZ |

## 16.6 Frontend component summary

| Group | Count | Components |
|-------|-------|-----------|
| Pages | 9 | Login, Dashboard, EquipmentMasterList, EquipmentMaster (New/Edit), VibrationAnalysis, Settings, Unauthorized, ChangePassword, ModulePages |
| Layout | 6 | AppShell, Sidebar, TopNav, PageHero, ComingSoon, nav-config |
| UI primitives | 6 (+2 docs) | Button, FormField (+4 inputs), GlassCard, MultiSelect, SectionCard, Toast |
| Auth | 1 | ProtectedRoute |
| Charts (shared) | 6 | GraphWorkspace, GraphToolbar, GraphStatisticsPanel, GraphChannelSelector, ThresholdZoneLegend, EchartsGraphViewport |
| Analysis (root) | 12 | AnalysisSectionHeader, AnalysisSummaryPanel, CaptureTimeline, CaptureTimelinePanel, CaptureTimelineSection, ChartHeader, CompactDateRangeBar, DiagnosticChart, PlotChart, PlotSelector, SaveBaselineModal, analysis-layout |
| Analysis / charts | 4 | EchartsDiagnosticChart + 3 deprecated re-exports |
| Analysis / baseline | 3 | BaselineManagementPanel, BaselineDetailCard, baseline-utils |
| Analysis / health | 13 | StatusHealthTab, StatusHealthSection, HealthChannelSelector, HealthSummaryCards, ChannelHealthOverviewCard, FeatureStatusTable, FeatureStatusBadge, FeatureComparisonSection, FeatureTrendCardsSection, HealthMetricCard, HealthThresholdsTable, HealthInfoBanner, HealthEmptyState, SensorThresholdConfig |
| Analysis / workspace | 7 | AnalysisWorkspace, AnalysisTabNav, DetailedAnalysisTab, StatisticsTab, TrendAnalysisTab, SelectedCapturePanel, BaselineSelectionPanel |
| Equipment | 9 | EquipmentForm, EquipmentPageShell, DigitalTwinHeader, FormStepper, MachineVisualizationPanel, SensorMountingDiagram, AssetHealthPanel, AssetIntelligencePanel, CompletenessEngine |
| Equipment / industrial | 3 | ProgressRing, CriticalityIndicator, IndustrialEmptyState |
| Equipment / tabs | 6 | Basic, Mechanical, Rotating, Operating, Sensors, Review |
| Settings | 10 | SettingsSectionCard, SettingsTabNav, ToggleSwitch, DeviceInfoCard, ChannelConfigurationSection, ChannelMappingOverview, ThresholdConfigurationSection, ThresholdCoverageMatrix, SettingsPageActions, VibrationSettingsModule |
| Brand | 5 | HeroIntelligenceBg, LoginIntelligenceBg, SensorPulseRings, VibrationWave, VibrationIntelligenceBg |
| Contexts | 3 | AuthContext, LayoutContext, ThemeContext |
| Hooks | 6 | useEchartsResize, useHealthStatusData, useFeatureHealthDashboard, useUploadFactorTrends, useHistoricalTrendData, useVibrationSettings |
| Lib modules | 30 | See §3.19 |
| Type modules | 9 | See §3.20 |
| API modules | 5 | client, auth, equipment, measurements, baselines |

## 16.7 Folder-by-folder file index

| Path | Why it exists | Connects to |
|------|---------------|-------------|
| `.env` | Single source of environment values for all three tiers | Compose, `Settings`, `alembic/env.py`, Vite |
| `docker-compose.yml` | Orchestrates the four services with correct ordering and volumes | All Dockerfiles, `.env` |
| `START.md` | Four-step local runbook | Developer workflow |
| `scripts/vibration.py` | Reference edge acquisition reader for a ZedBoard/IIO ADC | Conceptually pairs with `/measurements/acquisition` |
| `backend/Dockerfile` | Reproducible backend image; migrates then serves | `requirements.txt`, `app/` |
| `backend/alembic.ini` | Migration runner configuration | `alembic/env.py` |
| `backend/alembic/env.py` | Loads env, injects `DATABASE_URL`, imports models for autogenerate | `app.database`, `app.models` |
| `backend/alembic/versions/*` | The authoritative schema history (11 revisions) | Every table |
| `backend/app/config.py` | Fail-fast configuration binding | Everything |
| `backend/app/database.py` | Engine, session factory, declarative base, request-scoped session | All CRUD |
| `backend/app/main.py` | Application assembly, CORS, seeding, OpenAPI, health | All routers |
| `backend/app/dependencies/auth.py` | AuthN/AuthZ dependencies | All routers |
| `backend/app/models/*` | Persistence shape | CRUD, Alembic |
| `backend/app/schemas/*` | Wire shape and validation | Routers, services |
| `backend/app/crud/*` | Data access without HTTP or business rules | Routers, services |
| `backend/app/routers/*` | HTTP surface | Services, CRUD, schemas |
| `backend/app/services/*` | Business logic and algorithms | CRUD, models |
| `backend/scripts/*` | Standalone developer utilities | Not imported by the app |
| `frontend/index.html` | SPA shell | `main.tsx` |
| `frontend/vite.config.ts` | Dev server, alias, proxy, build | `tsconfig`, `src/` |
| `frontend/tailwind.config.js` | Design tokens consumed by every component | `index.css`, all components |
| `frontend/nginx.conf` | Production SPA serving with history fallback | `Dockerfile` preview stage |
| `frontend/src/main.tsx` | React root, Query client, Router | `App.tsx`, `index.css` |
| `frontend/src/App.tsx` | Provider stack and route table | Contexts, pages, guards |
| `frontend/src/index.css` | Tokens, base styles, 100+ component classes, keyframes | Every component |
| `frontend/src/api/*` | The only network boundary | Pages, hooks |
| `frontend/src/contexts/*` | Cross-cutting client state | App-wide |
| `frontend/src/hooks/*` | Query composition and view models | Analysis and settings components |
| `frontend/src/lib/*` | Pure maths, chart options, formatters, tokens | Components and hooks |
| `frontend/src/types/*` | Interfaces and driving constants | App-wide |
| `frontend/src/components/*` | Feature and shared UI | Pages |
| `frontend/src/images/*` | Brand and illustration assets with a typed barrel | Sidebar, empty states |

## 16.8 Dependency reference

### 16.8.1 Backend

| Dependency | Version | Purpose | Where used |
|------------|---------|---------|-----------|
| fastapi | 0.115.0 | HTTP framework, DI, OpenAPI | `main.py`, all routers |
| uvicorn[standard] | 0.30.6 | ASGI server | Dockerfile CMD, dev command |
| sqlalchemy | 2.0.35 | ORM and query building | `database.py`, all models and CRUD |
| alembic | 1.13.3 | Schema migrations | `alembic/` |
| psycopg2-binary | 2.9.9 | PostgreSQL driver | Engine URL |
| python-multipart | 0.0.12 | multipart parsing | `upload_image`, `upload_sensor_data`, `upload_baseline` |
| python-dotenv | 1.0.1 | `.env` loading | `alembic/env.py` |
| pillow | 10.4.0 | Image handling | Declared; **not imported** in `app/` |
| pydantic | 2.9.2 | Schemas and validators | All `schemas/` |
| pydantic-settings | 2.5.2 | Env-bound settings | `config.py` |
| aiofiles | 24.1.0 | Async file I/O | Declared; **not imported** |
| python-jose[cryptography] | 3.3.0 | JWT encode/decode | `auth_service.py`, `dependencies/auth.py` |
| passlib[bcrypt] | 1.7.4 | Password hashing context | `auth_service.py` |
| bcrypt | 4.0.1 | bcrypt backend | via passlib |
| email-validator | 2.2.0 | `EmailStr` support | `schemas/auth.py` |
| numpy | 1.26.4 | Array maths | `signal_processing.py`, `feature_extraction.py` |
| scipy | 1.13.1 | `fft`, `fftfreq`, `hilbert` | Same two modules |
| pdfplumber | 0.11.4 | PDF table/text extraction | `pdf_parser.py` |
| reportlab | — | Sample-PDF generation | `scripts/create_sample_sensor_pdf.py`; **not in requirements.txt** |

### 16.8.2 Frontend — runtime

| Dependency | Version | Purpose | Where used |
|------------|---------|---------|-----------|
| react / react-dom | ^18.3.1 | UI runtime | Everywhere |
| react-router-dom | ^6.27.0 | Routing and guards | `App.tsx`, `ProtectedRoute`, `Sidebar`, page navigation |
| @tanstack/react-query | ^5.59.20 | Server-state cache | `main.tsx`, all hooks and data pages |
| axios | ^1.7.7 | HTTP client + interceptors | `api/*`, `Login.tsx` (`isAxiosError`) |
| echarts | ^6.1.0 | Charting engine | `lib/*-option.ts`, chart components |
| echarts-for-react | ^3.0.6 | React binding | `EchartsGraphViewport`, `HealthMetricCard` |
| react-hook-form | ^7.53.2 | Form state, `useFieldArray` | Equipment wizard |
| @hookform/resolvers | ^3.9.0 | Zod ↔ RHF bridge | `EquipmentForm` |
| zod | ^3.23.8 | Schema validation | `types/equipment.ts` |
| framer-motion | ^12.40.0 | Animation | Cards, sidebar, toasts, table rows, login |
| lucide-react | ^0.454.0 | Icons | Every screen |
| tailwindcss | ^3.4.14 | Styling | All components |
| tailwindcss-animate | ^1.0.7 | Tailwind animation plugin | `tailwind.config.js` |
| clsx | ^2.1.1 | Conditional classes | `lib/utils.ts` |
| tailwind-merge | ^2.5.4 | Class conflict resolution | `lib/utils.ts` |
| date-fns | ^4.1.0 | Date formatting/arithmetic | `upload-format.ts`, timeline, trend hook |
| class-variance-authority | ^0.7.0 | Variant helper | Declared; **no import found** |
| @radix-ui/react-dialog, -dropdown-menu, -label, -popover, -select, -separator, -slot, -toast | ^1.x–^2.x | Headless primitives | Declared; **no import found** — modals and menus are hand-rolled |

### 16.8.3 Frontend — development

| Dependency | Version | Purpose |
|------------|---------|---------|
| vite | ^5.4.10 | Dev server and bundler |
| @vitejs/plugin-react | ^4.3.3 | React transform and fast refresh |
| typescript | ^5.6.3 | Type checking (the build gate) |
| postcss | ^8.4.47 | CSS transform pipeline |
| autoprefixer | ^10.4.20 | Vendor prefixes |
| @types/node | ^22.9.0 | Node types for `vite.config.ts` |
| @types/react, @types/react-dom | ^18.3.x | React type definitions |

### 16.8.4 Infrastructure images

| Image | Tag | Role |
|-------|-----|------|
| postgres | 16 | Database |
| dpage/pgadmin4 | latest | Database administration UI |
| python | 3.11-slim | Backend base |
| node | 20-alpine | Frontend build base |
| nginx | alpine | Frontend production server |

## 16.9 Constants quick reference

| Constant | Value | Location |
|----------|-------|----------|
| Access-token lifetime | 30 minutes | `config.py` |
| Refresh-token lifetime | 7 days | `config.py` |
| Refresh-token entropy | 48 bytes URL-safe | `auth_service.py` |
| Default sampling rate | 25600 Hz | `crud/measurement.py`, `schemas/measurement.py`, `lib/waveform-time-axis.ts` |
| Default FFT lines | 1600 | Same |
| Max image size | 10 MB | `config.py` |
| Max measurement file size | 50 MB | `config.py` |
| Channel range | 1–32 (`channel` 0–31) | Schemas and query params |
| FFT lines range | 64–65536 | `schemas/measurement.py` |
| Trend segments | 32 | `signal_processing.py`, `feature_extraction.py`, `lib/health-metrics.ts` |
| Shaft-frequency search band | 5–120 Hz | `feature_extraction.py` |
| FFT band-energy band | 0–500 Hz | `feature_extraction.py` |
| Circular waveform max points (backend) | 2048 | `signal_processing.py` |
| Waveform/orbit max points (frontend) | 8192 | `chart-data.ts` |
| Spectrum max points (frontend) | 2000 | `chart-data.ts` |
| Primary chart height | 580 px | `chart-constants.ts` |
| Compact chart height | 220 px | `chart-constants.ts` |
| Fullscreen ratio / chrome | 0.92 / 132 px, floor 360 px | `chart-layout.ts` |
| Threshold crossings per level | 24 | `threshold-overlay.ts` |
| React Query `staleTime` | 30 000 ms (60 000 ms for trend plots) | `main.tsx`, hooks |
| Factor-trend poll interval | 3000 ms | `useUploadFactorTrends.ts` |
| Long-request timeout | 120 000 ms | `api/measurements.ts` |
| Toast lifetime | 4000 ms | `Toast.tsx` |
| Sidebar widths | 320 / 80 px | `Sidebar.tsx` |
| Equipment page size | 20 | `EquipmentMasterList.tsx` |
| Upload page size (client default) | 200 | `api/measurements.ts` |
| Health/vibration channel count | 8 | `types/health-status.ts`, `types/vibration-settings.ts` |
| Algorithm version (fingerprint) | `v1` | `plot_storage.py` |

## 16.10 Diagram index

Every diagram is numbered sequentially and listed with its figure number in the **List of Figures** in the front matter. This index groups the same diagrams by subject and gives the section in which each appears.

| Subject | Section |
|---------|---------|
| Software architecture (4 tiers) | §1.7 |
| High-level workflow | §1.8 |
| Upload pipeline sequence | §1.8.1 |
| Deployment topology | §2.1, §12.1 |
| Dev API paths | §2.2.3 |
| Frontend provider and route tree | §2.3 |
| Backend request routing | §2.4 |
| Application startup sequence | §2.4.1 |
| Database cluster overview | §2.5 |
| Login sequence | §2.6 |
| Silent refresh with queueing | §2.6.1 |
| API communication flow | §2.7 |
| Data flow (ingestion → visualisation) | §2.8 |
| Response lifecycle | §2.10 |
| `ProtectedRoute` decision tree | §3.3.1 |
| Chart architecture | §3.9.1 |
| `custom_openapi` flow | §4.2.1 |
| Backend startup sequence | §4.2.1, §10.11.1 |
| Timestamp resolution heuristic | §4.9.4 |
| Plot cache-or-compute flow | §4.9.6 |
| Dependency injection graph | §4.15 |
| Refresh rotation sequence | §5.4.3 |
| Equipment create sequence | §5.5.1 |
| Feature computation sequence | §5.7.11 |
| Baseline promotion sequence | §5.8.6 |
| Entity relationship diagram | §6.2 |
| End-to-end database flow | §6.14 |
| Plot read sequence | §6.14 |
| Authorisation enforcement | §7.2.2 |
| User seeding flow | §7.6 |
| Parsing decision flow | §8.4 |
| Feature evaluation flow | §8.6 |
| User flow map | §9.1 |
| Upload-and-analyse sequence | §9.4 |
| Backend entry-to-shutdown | §10.11.1 |
| Frontend entry-to-teardown | §10.11.2 |
| Configuration precedence | §11.12 |
| Frontend build pipeline | §12.4 |
| CI/CD reference pipeline | §12.8 |
| Error-handling architecture | §15.1 |

---

# 17.0 References

## 17.1 Domain and standards references cited in the code

| Reference | Cited in | Used for |
|-----------|----------|----------|
| *Condition Monitoring with Vibration Signals* (Randall / Antoni) | `lib/industrial-viz-standards.ts`, `lib/chart-bounds.ts`, `lib/chart-reference-lines.ts`, `ThresholdZoneLegend.tsx` | Alarm-zone colour coding, harmonic/order markers, symmetric waveform display, crest-factor and kurtosis interpretation |
| *The Scientist and Engineer's Guide to Digital Signal Processing* (Steven W. Smith) | `lib/industrial-viz-standards.ts`, `lib/chart-reference-lines.ts` | FFT frequency axis, Nyquist limit `fs/2`, frequency resolution `Δf = fs/N` |
| **ISO 10816-3** — Mechanical vibration: evaluation of machine vibration by measurements on non-rotating parts | `ISO_10816_VELOCITY_ZONES_REFERENCE` in `lib/industrial-viz-standards.ts` | Velocity-severity zones, documented but deliberately **not** auto-applied because limits depend on machine class and mounting |

The code's own note on ISO 10816 is reproduced here because it is a design decision, not an omission:

> *"Zone limits depend on machine class and mounting. Configure per asset in Vibration Settings."*

## 17.2 Technology documentation

| Technology | Reference |
|------------|-----------|
| FastAPI | https://fastapi.tiangolo.com |
| SQLAlchemy 2.0 | https://docs.sqlalchemy.org/en/20/ |
| Alembic | https://alembic.sqlalchemy.org |
| Pydantic v2 | https://docs.pydantic.dev |
| PostgreSQL 16 | https://www.postgresql.org/docs/16/ |
| NumPy | https://numpy.org/doc/ |
| SciPy signal / fft | https://docs.scipy.org/doc/scipy/reference/ |
| pdfplumber | https://github.com/jsvine/pdfplumber |
| passlib | https://passlib.readthedocs.io |
| python-jose | https://python-jose.readthedocs.io |
| React 18 | https://react.dev |
| React Router 6 | https://reactrouter.com |
| TanStack Query 5 | https://tanstack.com/query/latest |
| Apache ECharts | https://echarts.apache.org |
| Tailwind CSS | https://tailwindcss.com |
| Vite | https://vite.dev |
| Zod | https://zod.dev |
| React Hook Form | https://react-hook-form.com |
| Framer Motion | https://www.framer.com/motion/ |
| Docker Compose | https://docs.docker.com/compose/ |

## 17.3 Internal source references

| Artefact | Path |
|----------|------|
| Local runbook | `START.md` |
| Card sizing contract | `frontend/src/components/ui/CARD_SIZING.md` |
| Card hover contract | `frontend/src/components/ui/CARD_HOVER.md` |
| Swagger login instructions and dev accounts | `backend/app/main.py` (FastAPI `description`) |
| Interactive API documentation | `http://localhost:8000/docs`, `/redoc`, `/openapi.json` |
| Migration history | `backend/alembic/versions/001…011` |
| Auth smoke test | `backend/scripts/test_auth_phase1.py` |
| Sample data generator | `backend/scripts/create_sample_sensor_pdf.py` |
| Edge acquisition reference | `scripts/vibration.py` |

---

*End of document.*
