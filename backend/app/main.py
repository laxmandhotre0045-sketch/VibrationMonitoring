from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.routers.equipment import router as equipment_router
from app.routers.lookups import router as lookups_router
from app.routers.measurements import router as measurements_router

app = FastAPI(
    title="AI Vibration Intelligence Platform",
    description="Stage 1 — Equipment Master Data API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(equipment_router)
app.include_router(lookups_router)
app.include_router(measurements_router)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.getenv("MEASUREMENT_UPLOAD_DIR", "uploads/measurements"), exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI Vibration Intelligence Platform"}
