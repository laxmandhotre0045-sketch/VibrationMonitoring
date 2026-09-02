from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config import settings
from app.database import SessionLocal
from app.routers.acquisition import router as acquisition_router
from app.routers.auth import router as auth_router
from app.routers.baselines import router as baselines_router
from app.routers.dashboard import router as dashboard_router
from app.routers.equipment import router as equipment_router
from app.routers.ingest import router as ingest_router
from app.routers.integrations import router as integrations_router
from app.routers.lookups import router as lookups_router
from app.routers.measurements import router as measurements_router
from app.routers.plants import router as plants_router
from app.routers.thresholds import router as thresholds_router
from app.routers.users import router as users_router
from app.services.seed import seed_role_users, seed_super_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_super_admin(db)
        seed_role_users(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="AI Vibration Intelligence Platform",
    description="""
Stage 1 — Equipment Master Data API with Authentication

## How to log in (Swagger)

1. Expand **Authentication** → **POST /api/v1/auth/login**
2. Click **Try it out**
3. Use one of the test accounts below
4. Click **Execute** and copy `access_token` from the response
5. Click the green **Authorize** button (top right)
6. Paste: `Bearer <access_token>` or only the token (Swagger adds Bearer)

Alternative: use **POST /api/v1/auth/token** with `username` = email and `password`.

## Test accounts (dev)

| Role | Email | Password | Access |
|------|-------|----------|--------|
| super_admin | admin@vibration.com | Admin@2024 | Full read + write |
| admin | plantadmin@vibration.com | PlantAdmin@2024 | Read + write |
| user | viewer@vibration.com | Viewer@2024 | Read only (GET) |

Protected APIs return **401** without a token and **403** for write actions when logged in as `user`.
""",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Keep configured origins and support common Vite development ports.
    allow_origins=list(dict.fromkeys([
        *settings.allowed_origins,
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:4173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:3000",
    ])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(acquisition_router)
app.include_router(auth_router)
app.include_router(baselines_router)
app.include_router(dashboard_router)
app.include_router(equipment_router)
app.include_router(ingest_router)
app.include_router(integrations_router)
app.include_router(lookups_router)
app.include_router(measurements_router)
app.include_router(plants_router)
app.include_router(thresholds_router)
app.include_router(users_router)

os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.measurement_upload_dir, exist_ok=True)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})

    openapi_schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Paste access_token from POST /api/v1/auth/login or /api/v1/auth/token",
    }

    openapi_schema["components"]["securitySchemes"]["OAuth2Password"] = {
        "type": "oauth2",
        "flows": {
            "password": {
                "tokenUrl": "/api/v1/auth/token",
                "scopes": {},
            }
        },
        "description": "Swagger Authorize: username = email, password = your password",
    }

    def _norm(path: str) -> str:
        return path.rstrip("/") or "/"

    # Endpoints that do not require a Bearer token in Swagger
    public_post_paths = {
        _norm("/api/v1/auth/login"),
        _norm("/api/v1/auth/token"),
        _norm("/api/v1/auth/refresh"),
        _norm("/api/v1/auth/logout"),
    }

    for path, methods in openapi_schema.get("paths", {}).items():
        if _norm(path) == "/health":
            continue

        if not path.startswith("/api/v1/"):
            continue

        for method_name, operation in methods.items():
            if not isinstance(operation, dict):
                continue

            if method_name.lower() == "post" and _norm(path) in public_post_paths:
                continue

            operation["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI Vibration Intelligence Platform"}