from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import anyio
import httpx

router = APIRouter()

_CACHE_DIR = Path(__file__).parent.parent / "geo_cache"

_STATE_URL = "https://eric.clst.org/assets/wiki/uploads/Stuff/gz_2010_us_040_00_500k.json"
_COUNTY_URL = "https://eric.clst.org/assets/wiki/uploads/Stuff/gz_2010_us_050_00_500k.json"


async def _cached_geo(filename: str, url: str) -> Path:
    await anyio.to_thread.run_sync(lambda: _CACHE_DIR.mkdir(exist_ok=True))
    path = _CACHE_DIR / filename
    if not path.exists():
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
        await anyio.to_thread.run_sync(lambda: path.write_bytes(content))
    return path


@router.get("/api/geo/states")
async def get_states_geo() -> FileResponse:
    try:
        path = await _cached_geo("states.json", _STATE_URL)
        return FileResponse(path, media_type="application/json")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/api/geo/counties")
async def get_counties_geo() -> FileResponse:
    try:
        path = await _cached_geo("counties.json", _COUNTY_URL)
        return FileResponse(path, media_type="application/json")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
