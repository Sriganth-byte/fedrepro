import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import ai, auth, datasets, studies, variants
from app.core.config import get_settings

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="FedRepro API", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for router in (auth.router, studies.router, datasets.router, ai.router, variants.router):
    app.include_router(router, prefix=settings.api_prefix)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"status": "ok", "service": settings.app_name, "ai_enabled": settings.ai_enabled, "ai_model": settings.ollama_model if settings.ai_enabled else None}

