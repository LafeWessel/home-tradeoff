"""HTTP fetching with persistent SQLite-backed caching.

Every successful response is stored in `api_cache` keyed by a hash of the
request. On subsequent calls within `ttl_seconds` we return the cached body
without hitting the network. Failed responses (>=400) are *not* cached so a
transient outage doesn't poison future runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.api_cache import ApiCache
from ..settings import settings

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _cache_key(method: str, url: str, params: dict | None, body: bytes | None) -> str:
    h = hashlib.sha256()
    h.update(method.upper().encode())
    h.update(b"|")
    h.update(url.encode())
    h.update(b"|")
    if params:
        h.update(json.dumps(params, sort_keys=True, separators=(",", ":")).encode())
    h.update(b"|")
    if body:
        h.update(body)
    return h.hexdigest()


def cached_get_json(
    db: Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    ttl_seconds: int | None = None,
) -> Any:
    """GET `url`, returning parsed JSON. Cache by request hash."""
    return _cached_request(db, "GET", url, params=params, headers=headers, ttl_seconds=ttl_seconds)


def cached_post_json(
    db: Session,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    ttl_seconds: int | None = None,
) -> Any:
    body = json.dumps(json_body, sort_keys=True).encode() if json_body is not None else None
    return _cached_request(
        db, "POST", url, body=body, headers=headers, ttl_seconds=ttl_seconds, content_type="application/json"
    )


def _cached_request(
    db: Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    ttl_seconds: int | None = None,
    content_type: str | None = None,
) -> Any:
    ttl = ttl_seconds or settings.http_cache_ttl
    key = _cache_key(method, url, params, body)
    now = datetime.now(timezone.utc)

    row = db.get(ApiCache, key)
    if row is not None:
        # Some DB drivers return naive datetimes; normalize.
        fetched_at = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
        if fetched_at + timedelta(seconds=row.ttl_seconds) > now:
            log.debug("cache hit %s %s", method, url)
            return json.loads(row.body.decode())
        # expired — fall through to refresh

    log.info("cache miss %s %s", method, url)
    headers = dict(headers or {})
    if content_type and "Content-Type" not in headers:
        headers["Content-Type"] = content_type

    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        resp = client.request(method, url, params=params, content=body, headers=headers)

    if resp.status_code >= 400:
        # Don't cache errors — re-raise with context.
        raise httpx.HTTPStatusError(
            f"{method} {url} -> {resp.status_code}: {resp.text[:300]}",
            request=resp.request,
            response=resp,
        )

    payload = resp.json()
    raw = json.dumps(payload).encode()

    if row is None:
        row = ApiCache(
            key=key,
            method=method.upper(),
            url=url,
            status=resp.status_code,
            body=raw,
            content_type=resp.headers.get("Content-Type"),
            ttl_seconds=ttl,
            fetched_at=now,
        )
        db.add(row)
    else:
        row.status = resp.status_code
        row.body = raw
        row.content_type = resp.headers.get("Content-Type")
        row.ttl_seconds = ttl
        row.fetched_at = now
    db.commit()
    return payload
