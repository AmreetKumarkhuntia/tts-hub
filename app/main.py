"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app import registry
from app.api.routes import router
from app.bootstrap import register_default_engines
from app.config import settings

logger = logging.getLogger("tts_hub")

REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_HTML = REPO_ROOT / "test.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the default engine so the first request isn't slowed by model load.
    try:
        registry.get(settings.default_model)
        logger.info("Warmed default engine '%s'.", settings.default_model)
    except Exception as exc:  # don't block startup if weights aren't available yet
        logger.warning("Could not warm '%s': %s", settings.default_model, exc)
    yield


register_default_engines()

app = FastAPI(title="tts-hub", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", include_in_schema=False)
@app.get("/test.html", include_in_schema=False)
def tester():
    if TEST_HTML.exists():
        return FileResponse(TEST_HTML)
    return {"detail": "test.html not found; open it directly from the repo root."}


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    run()
