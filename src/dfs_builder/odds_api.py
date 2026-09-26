"""Credit-safe, cache-first client for The Odds API (v4).

Rules from the brief this module enforces:
  * every successful response is saved to disk with a UTC timestamp (data/cache/odds_api/),
  * a request already in the cache is never re-fetched (same path + params = same fingerprint;
    historical snapshots differ by their `date` param, so each snapshot is its own entry),
  * credit usage is printed after every network call, read from the x-requests-* headers,
  * a per-run credit ceiling blocks any call whose worst-case cost would exceed it.

The API key is read from the ODDS_API_KEY environment variable and is never written to disk.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from dfs_builder.paths import ODDS_API_CACHE
from dfs_builder.safe_io import write_verified

BASE_URL = "https://api.the-odds-api.com"
SPORT = "americanfootball_nfl"
CREDIT_HEADERS = ("x-requests-last", "x-requests-used", "x-requests-remaining")


class CreditBudgetExceeded(RuntimeError):
    pass


def fingerprint(path: str, params: dict[str, Any]) -> str:
    clean = {k: params[k] for k in sorted(params) if k.lower() != "apikey"}
    blob = json.dumps({"path": path, "params": clean}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


@dataclass
class ApiResult:
    body: Any
    from_cache: bool
    cache_file: Path
    credits_last: int | None
    credits_used: int | None
    credits_remaining: int | None
    fetched_at_utc: str


class OddsApiClient:
    def __init__(self, api_key: str | None = None, *, cache_dir: Path = ODDS_API_CACHE,
                 max_credits_this_run: int = 0, session: requests.Session | None = None,
                 printer: Callable[[str], None] = print):
        self.api_key = api_key if api_key is not None else os.environ.get("ODDS_API_KEY", "")
        self.cache_dir = Path(cache_dir)
        self.max_credits_this_run = max_credits_this_run
        self.spent_this_run = 0
        self.session = session or requests.Session()
        self.print = printer

    # ---- cache -------------------------------------------------------------------------------
    @property
    def index_path(self) -> Path:
        return self.cache_dir / "index.jsonl"

    def _lookup(self, fp: str) -> Path | None:
        if not self.index_path.exists():
            return None
        hit = None
        with open(self.index_path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row["fingerprint"] == fp:
                    hit = self.cache_dir / row["file"]
        return hit if hit is not None and hit.exists() else None

    def _append_index(self, row: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "a", encoding="utf-8", newline="\n") as f:  # append-only
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    # ---- requests ----------------------------------------------------------------------------
    def get(self, path: str, params: dict[str, Any] | None = None, *, max_cost: int) -> ApiResult:
        """GET path with params. max_cost is the worst-case credit cost, used by the budget guard."""
        params = dict(params or {})
        fp = fingerprint(path, params)
        cached = self._lookup(fp)
        if cached is not None:
            rec = json.loads(cached.read_text(encoding="utf-8"))
            self.print(f"[cache] {path}  (0 credits, saved {rec['fetched_at_utc']})")
            h = rec.get("credit_headers", {})
            return ApiResult(rec["body"], True, cached, _int(h.get("x-requests-last")),
                             _int(h.get("x-requests-used")), _int(h.get("x-requests-remaining")),
                             rec["fetched_at_utc"])
        if self.spent_this_run + max_cost > self.max_credits_this_run:
            raise CreditBudgetExceeded(
                f"{path}: worst-case {max_cost} credits would exceed this run's ceiling "
                f"({self.spent_this_run} spent of {self.max_credits_this_run})")
        if not self.api_key:
            raise RuntimeError("ODDS_API_KEY is not set")

        resp = self.session.get(BASE_URL + path, params={**params, "apiKey": self.api_key}, timeout=60)
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        headers = {k: resp.headers.get(k) for k in CREDIT_HEADERS}
        last = _int(headers["x-requests-last"])
        self.spent_this_run += last if last is not None else max_cost
        self.print(f"[api]   {path}  status={resp.status_code}  credits: this call={headers['x-requests-last']}"
                   f"  used={headers['x-requests-used']}  remaining={headers['x-requests-remaining']}"
                   f"  (this run {self.spent_this_run})")
        if resp.status_code != 200:
            raise requests.HTTPError(f"{resp.status_code} for {path}: {resp.text[:300]}")

        stamp = fetched_at.replace(":", "").replace("-", "")
        rel = Path(fetched_at[:10]) / f"{fp}__{stamp}.json"
        record = {"fetched_at_utc": fetched_at, "path": path,
                  "params": {k: v for k, v in params.items() if k.lower() != "apikey"},
                  "fingerprint": fp, "status": resp.status_code, "credit_headers": headers, "body": resp.json()}
        digest = write_verified(self.cache_dir / rel, json.dumps(record, indent=1) + "\n")
        self._append_index({"fingerprint": fp, "file": rel.as_posix(), "sha256": digest,
                            "fetched_at_utc": fetched_at, "path": path, "credits_last": last})
        return ApiResult(record["body"], False, self.cache_dir / rel, last,
                         _int(headers["x-requests-used"]), _int(headers["x-requests-remaining"]), fetched_at)


def _int(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
