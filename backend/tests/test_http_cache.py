"""HTTP cache tests — make sure repeated calls don't go to the network."""

import httpx


def test_cached_get_round_trips_payload(tmp_db, monkeypatch):
    from app.sources import http_cache

    calls = {"n": 0}

    class FakeResp:
        status_code = 200
        text = ""
        request = None
        headers: dict = {"Content-Type": "application/json"}

        def json(self):
            return {"hello": "world"}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, method, url, **kw):
            calls["n"] += 1
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)

    with tmp_db.SessionLocal() as db:
        out1 = http_cache.cached_get_json(db, "https://example.com/x")
        out2 = http_cache.cached_get_json(db, "https://example.com/x")

    assert out1 == out2 == {"hello": "world"}
    # Second call should be served from cache, not network.
    assert calls["n"] == 1
