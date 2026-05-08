from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import locations as locations_api
from .api import metrics as metrics_api
from .api import presets as presets_api
from .api import scoring as scoring_api
from .db import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Home Tradeoff API",
    version="0.1.0",
    description="Local decision-support API for comparing US locations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(metrics_api.router)
app.include_router(locations_api.router)
app.include_router(presets_api.router)
app.include_router(scoring_api.router)
