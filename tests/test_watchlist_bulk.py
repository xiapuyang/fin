def _wl(symbol="AAPL", **kw):
    base = {"symbol": symbol, "name": symbol}
    base.update(kw)
    return base


def test_bulk_create_watchlist_success(client):
    r = client.post(
        "/api/watchlist/bulk",
        json=[_wl("AAPL"), _wl("TSLA")],
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": 2, "skipped": 0, "errors": []}
    assert {w["symbol"] for w in client.get("/api/watchlist").json()} == {
        "AAPL",
        "TSLA",
    }


def test_bulk_create_watchlist_dedups(client):
    client.post("/api/watchlist", json=_wl("AAPL"))
    r = client.post(
        "/api/watchlist/bulk",
        json=[_wl("AAPL"), _wl("TSLA")],
    )
    assert r.json() == {"created": 1, "skipped": 1, "errors": []}


def test_bulk_create_watchlist_validation_aborts(client):
    r = client.post("/api/watchlist/bulk", json=[_wl("AAPL"), {}])
    assert r.status_code == 422
    assert client.get("/api/watchlist").json() == []


def test_bulk_create_watchlist_empty(client):
    r = client.post("/api/watchlist/bulk", json=[])
    assert r.json() == {"created": 0, "skipped": 0, "errors": []}


def test_bulk_create_skips_duplicates_within_input(client):
    payload = [_wl("AAPL"), _wl("AAPL")]
    r = client.post("/api/watchlist/bulk", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 1
    assert body["skipped"] == 1
