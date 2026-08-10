import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ai, auth, datasets, studies, variants
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.evidence_warmup_service import EvidenceWarmupService

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _run_startup_evidence_warmup() -> None:
    db = SessionLocal()
    try:
        EvidenceWarmupService(db).warm_all()
    except Exception:
        logging.getLogger(__name__).exception("Startup evidence warmup failed")
    finally:
        db.close()


def start_evidence_warmup():
    if not settings.evidence_warmup_on_startup:
        return
    threading.Thread(target=_run_startup_evidence_warmup, name="evidence-warmup", daemon=True).start()


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_evidence_warmup()
    yield


app = FastAPI(title="FedRepro API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for router in (auth.router, studies.router, datasets.router, ai.router, variants.router):
    app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok", "service": settings.app_name, "ai_enabled": settings.ai_enabled, "ai_model": settings.ollama_model if settings.ai_enabled else None}


@app.get("/api/version")
def version():
    return {"service": settings.app_name, "version": app.version, "api_prefix": settings.api_prefix}


def ollama_model_listing():
    return {"object": "list", "data": [{"id": settings.ollama_model, "object": "model", "owned_by": "ollama"}]}


@app.get("/models")
def models():
    return ollama_model_listing()


@app.get("/v1/models")
def openai_compatible_models():
    return ollama_model_listing()
