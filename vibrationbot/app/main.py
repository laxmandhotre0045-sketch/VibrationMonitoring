from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_chat import router as chat_router
from app.api.routes_documents import router as documents_router
from app.config import BASE_DIR
from app.retrieval.index_service import index_service
from app.retrieval.embeddings import preload_embedding_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    preload_embedding_model()
    loaded = index_service.preload_ready_documents()
    logger.info("Preloaded %d document index(es): %s", len(loaded), loaded)

    # Compile the graph and open the checkpointer connection at startup, so the
    # first chat request does not pay for it and a misconfigured checkpointer
    # surfaces in the logs rather than mid-conversation.
    try:
        from app.chat.graph.build import get_graph

        get_graph()
    except Exception as exc:  # noqa: BLE001 — legacy modes must still start
        logger.warning("LangGraph unavailable at startup (mode=graph will fail): %s", exc)

    yield


app = FastAPI(
    title="Vibration Analysis Assistant API",
    version="3.0.0",
    lifespan=lifespan,
)

app.include_router(documents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/api/v1/health")
def health():
    from app.domain.machine import machine_store
    from app.chat.graph.build import is_ready as graph_ready
    from app.llm.provider import provider_name
    from app.retrieval.embeddings import is_ready

    try:
        machines = len(machine_store.list_ids())
    except Exception:  # noqa: BLE001 — health must not fail on a storage hiccup
        machines = 0

    return {
        "status": "ok",
        "embedding_model_ready": is_ready(),
        "ready_documents": len(index_service.list_ready_doc_ids()),
        "graph_ready": graph_ready(),
        "llm_provider": provider_name(),
        "registered_machines": machines,
    }


@app.get("/")
def ui():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Vibration Analysis Assistant API", "docs": "/docs"}
