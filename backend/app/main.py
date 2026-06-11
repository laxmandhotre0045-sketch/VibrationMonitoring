from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.database import SessionLocal
from app.routers.auth import router as auth_router
from app.routers.equipment import router as equipment_router
from app.routers.lookups import router as lookups_router
from app.routers.measurements import router as measurements_router
from app.services.seed import seed_super_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_super_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="AI Vibration Intelligence Platform",
    description="Stage 1 — Equipment Master Data API with Authentication",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(equipment_router)
app.include_router(lookups_router)
app.include_router(measurements_router)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    for path, methods in openapi_schema.get("paths", {}).items():
        if path.endswith("/me"):
            for method in methods.values():
                if isinstance(method, dict):
                    method["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI Vibration Intelligence Platform"}
