"""The Odds API client must never re-fetch cached requests, never store the key, and respect the credit ceiling."""

import json

import pytest

from dfs_builder.odds_api import CreditBudgetExceeded, OddsApiClient, fingerprint


class FakeResponse:
    def __init__(self, body, cost):
        self.status_code = 200
        self._body = body
        self.text = json.dumps(body)
        self.headers = {"x-requests-last": str(cost), "x-requests-used": "100", "x-requests-remaining": "19900"}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, cost=10):
        self.calls = []
        self.cost = cost

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params)))
        return FakeResponse({"echo": params.get("markets")}, self.cost)


def make_client(tmp_path, session, ceiling=1000):
    return OddsApiClient("SECRET-KEY", cache_dir=tmp_path, max_credits_this_run=ceiling,
                         session=session, printer=lambda _msg: None)


def test_second_identical_request_is_served_from_cache(tmp_path):
    session = FakeSession()
    client = make_client(tmp_path, session)
    first = client.get("/v4/x", {"markets": "a,b"}, max_cost=20)
    second = client.get("/v4/x", {"markets": "a,b"}, max_cost=20)
    assert len(session.calls) == 1
    assert not first.from_cache and second.from_cache
    assert second.body == first.body


def test_new_client_reuses_cache_on_disk(tmp_path):
    make_client(tmp_path, FakeSession()).get("/v4/x", {"date": "2025-09-14T16:30:00Z"}, max_cost=10)
    session = FakeSession()
    make_client(tmp_path, session).get("/v4/x", {"date": "2025-09-14T16:30:00Z"}, max_cost=10)
    assert session.calls == []


def test_different_snapshot_date_is_a_different_request(tmp_path):
    session = FakeSession()
    client = make_client(tmp_path, session)
    client.get("/v4/x", {"date": "2025-09-14T16:30:00Z"}, max_cost=10)
    client.get("/v4/x", {"date": "2025-09-14T19:30:00Z"}, max_cost=10)
    assert len(session.calls) == 2


def test_api_key_never_written_to_disk(tmp_path):
    make_client(tmp_path, FakeSession()).get("/v4/x", {"markets": "a"}, max_cost=10)
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert "SECRET-KEY" not in f.read_text(encoding="utf-8")


def test_fingerprint_ignores_api_key():
    assert fingerprint("/p", {"a": 1, "apiKey": "k1"}) == fingerprint("/p", {"a": 1, "apiKey": "k2"})


def test_credit_ceiling_blocks_call_before_network(tmp_path):
    session = FakeSession(cost=100)
    client = make_client(tmp_path, session, ceiling=150)
    client.get("/v4/x", {"n": 1}, max_cost=100)
    with pytest.raises(CreditBudgetExceeded):
        client.get("/v4/x", {"n": 2}, max_cost=100)
    assert len(session.calls) == 1
