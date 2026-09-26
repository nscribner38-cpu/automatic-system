"""Phase 0: small, capped probe of The Odds API to see real prop coverage before any backfill.

Default is a DRY RUN: prints the planned calls and worst-case credits, spends nothing.
  python scripts/phase0_odds_api_probe.py            # show the plan
  python scripts/phase0_odds_api_probe.py --run      # spend up to ~112 credits
  python scripts/phase0_odds_api_probe.py --run --check-2023   # plus one 2023 game (~+101)

Needs the ODDS_API_KEY environment variable. Every response is cached under data/cache/odds_api/
(re-running costs 0 for anything already fetched) and credits are printed after each call.

What it answers:
  1. Which of the 10 prop markets each of the 5 books posts for an upcoming main-slate game.
  2. Whether Over and Under (and anytime-TD Yes and No) are both posted, which de-vigging needs.
  3. Whether the same holds in a historical 2025 snapshot (and 2023 with --check-2023).
  4. Whether Odds API team names map cleanly to nflverse team abbreviations and game_ids.
Writes docs/phase0/odds_api_probe_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

os.environ.setdefault("NFLREADPY_CACHE", "filesystem")

from dfs_builder.odds_api import SPORT, OddsApiClient  # noqa: E402
from dfs_builder.paths import NFLREADPY_CACHE, PHASE0_DOCS  # noqa: E402
from dfs_builder.safe_io import write_verified  # noqa: E402

os.environ.setdefault("NFLREADPY_CACHE_DIR", str(NFLREADPY_CACHE))
import nflreadpy as nfl  # noqa: E402
import polars as pl  # noqa: E402

ET = ZoneInfo("America/New_York")
PROP_MARKETS = ["player_pass_yds", "player_pass_tds", "player_pass_attempts", "player_pass_completions",
                "player_pass_interceptions", "player_rush_yds", "player_rush_attempts", "player_receptions",
                "player_reception_yds", "player_anytime_td"]
BOOKS = ["draftkings", "fanduel", "williamhill_us", "betmgm", "fanatics"]
MAIN_SLATE_TIMES = {"13:00", "16:05", "16:25"}
HIST_MULT = 10


def team_name_map() -> dict[str, str]:
    teams = nfl.load_teams()
    current = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND",
               "JAX", "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF",
               "TB", "TEN", "WAS"}
    return {r["team_name"]: r["team_abbr"] for r in teams.to_dicts() if r["team_abbr"] in current}


def pick_historical_game(season: int, week: int) -> dict:
    s = nfl.load_schedules([season]).filter(
        (pl.col("game_type") == "REG") & (pl.col("week") == week) & (pl.col("weekday") == "Sunday")
        & (pl.col("gametime") == "13:00")).sort("game_id")
    g = s.row(0, named=True)
    kickoff = datetime.strptime(f"{g['gameday']} {g['gametime']}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    snap = (kickoff - timedelta(minutes=30)).astimezone(timezone.utc)
    return {"game_id": g["game_id"], "home": g["home_team"], "away": g["away_team"],
            "kickoff_et": kickoff.isoformat(), "snapshot_utc": snap.strftime("%Y-%m-%dT%H:%M:%SZ")}


def summarize_event_odds(body: dict) -> dict:
    """Per book and market: players quoted and whether both sides are posted."""
    out: dict = {}
    for bk in body.get("bookmakers", []):
        mk_out = {}
        for mk in bk.get("markets", []):
            sides = defaultdict(set)
            for o in mk.get("outcomes", []):
                sides[o.get("description") or "?"].add(o.get("name"))
            n_players = len(sides)
            mk_out[mk["key"]] = {
                "players": n_players,
                "both_sides_share": round(sum(1 for s in sides.values() if len(s) >= 2) / n_players, 3) if n_players else 0,
                "sides_seen": sorted({n for s in sides.values() for n in s if n}),
                "example_players": sorted(sides)[:5],
            }
        out[bk["key"]] = {"markets": mk_out, "missing_markets": [m for m in PROP_MARKETS if m not in mk_out]}
    out["books_missing_entirely"] = [b for b in BOOKS if b not in out]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="actually call the API (default is a dry run)")
    ap.add_argument("--check-2023", action="store_true", help="also probe one 2023 game (about +101 credits)")
    args = ap.parse_args()

    live_cost = 0 + 0 + 1 + len(PROP_MARKETS)
    hist_cost = 1 + HIST_MULT * len(PROP_MARKETS)
    total = live_cost + hist_cost * (2 if args.check_2023 else 1)
    hist_games = [pick_historical_game(2025, 3)] + ([pick_historical_game(2023, 3)] if args.check_2023 else [])
    print("Plan (worst-case credits):")
    print("  /v4/sports                                   0")
    print(f"  /v4/sports/{SPORT}/events                0")
    print(f"  one upcoming main-slate game: markets list   1")
    print(f"  one upcoming main-slate game: 10 props x 5 books   {len(PROP_MARKETS)}")
    for g in hist_games:
        print(f"  historical events list at {g['snapshot_utc']}   1")
        print(f"  historical props {g['away']}@{g['home']} ({g['game_id']}) at {g['snapshot_utc']}   "
              f"{HIST_MULT * len(PROP_MARKETS)}")
    print(f"  TOTAL worst case: {total} credits (cached calls cost 0)")
    if not args.run:
        print("\nDry run only. Re-run with --run to spend credits.")
        return 0

    client = OddsApiClient(max_credits_this_run=total)
    books = ",".join(BOOKS)
    markets = ",".join(PROP_MARKETS)
    names = team_name_map()
    summary: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "books": BOOKS,
                     "markets": PROP_MARKETS}

    sports = client.get("/v4/sports", {}, max_cost=0).body
    summary["nfl_sport_listed"] = any(s.get("key") == SPORT for s in sports)
    events = client.get(f"/v4/sports/{SPORT}/events", {}, max_cost=0).body
    unmapped = sorted({t for e in events for t in (e["home_team"], e["away_team"]) if t not in names})
    summary["upcoming_events"] = len(events)
    summary["team_names_unmapped_to_nflverse"] = unmapped

    def is_main(e: dict) -> bool:
        k = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")).astimezone(ET)
        return k.strftime("%A") == "Sunday" and k.strftime("%H:%M") in MAIN_SLATE_TIMES

    main_events = [e for e in events if is_main(e)]
    summary["upcoming_main_slate_events"] = len(main_events)
    if main_events:
        ev = main_events[0]
        summary["live_event"] = {k: ev[k] for k in ("id", "home_team", "away_team", "commence_time")}
        mk = client.get(f"/v4/sports/{SPORT}/events/{ev['id']}/markets", {"bookmakers": books}, max_cost=1).body
        summary["live_markets_listed_by_book"] = {b["key"]: sorted(m["key"] for m in b.get("markets", []))
                                                  for b in mk.get("bookmakers", [])}
        odds = client.get(f"/v4/sports/{SPORT}/events/{ev['id']}/odds",
                          {"bookmakers": books, "markets": markets, "oddsFormat": "american"},
                          max_cost=len(PROP_MARKETS))
        summary["live_props"] = summarize_event_odds(odds.body)
        summary["live_props_credits_charged"] = odds.credits_last

    summary["historical"] = []
    for g in hist_games:
        hev = client.get(f"/v4/historical/sports/{SPORT}/events", {"date": g["snapshot_utc"]}, max_cost=1).body
        match = [e for e in hev.get("data", [])
                 if names.get(e["home_team"]) == g["home"] and names.get(e["away_team"]) == g["away"]]
        entry = {"nflverse_game": g, "snapshot_returned": hev.get("timestamp"), "event_matched": bool(match)}
        if match:
            hodds = client.get(f"/v4/historical/sports/{SPORT}/events/{match[0]['id']}/odds",
                               {"date": g["snapshot_utc"], "bookmakers": books, "markets": markets,
                                "oddsFormat": "american"}, max_cost=HIST_MULT * len(PROP_MARKETS))
            entry["snapshot_returned_odds"] = hodds.body.get("timestamp")
            entry["props"] = summarize_event_odds(hodds.body.get("data", {}))
            entry["credits_charged"] = hodds.credits_last
        summary["historical"].append(entry)

    summary["credits_spent_this_run"] = client.spent_this_run
    digest = write_verified(PHASE0_DOCS / "odds_api_probe_summary.json", json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("live_props", "historical")}, indent=2))
    print(f"wrote docs/phase0/odds_api_probe_summary.json sha256={digest[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
