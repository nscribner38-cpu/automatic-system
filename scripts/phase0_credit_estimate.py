"""Phase 0: estimate The Odds API credits for historical backfill and weekly live use. Spends nothing.

Game counts come from the real schedule (docs/phase0/main_slate_games.csv, written by
phase0_nflreadpy_inventory.py). Cost rules are in COST_RULES below with their source; if the
Odds API changes pricing, change them there. Estimates are upper bounds: event-odds calls are
billed per market actually returned, so markets a book doesn't post cost less.

Writes docs/phase0/odds_api_credit_estimate.md
"""

from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict

from dfs_builder.paths import PHASE0_DOCS
from dfs_builder.safe_io import write_verified

# Source: https://the-odds-api.com/liveapi/guides/v4/ (usage quota costs), checked 2026-09-26.
COST_RULES = {
    "live_event_odds_per_market_per_region": 1,
    "live_odds_per_market_per_region": 1,
    "historical_multiplier": 10,
    "historical_events_list": 1,
    "bookmakers_per_region_equivalent": 10,
}
PROP_MARKETS = [
    "player_pass_yds", "player_pass_tds", "player_pass_attempts", "player_pass_completions",
    "player_pass_interceptions", "player_rush_yds", "player_rush_attempts", "player_receptions",
    "player_reception_yds", "player_anytime_td",
]
ALT_MARKETS = ["player_pass_yds_alternate", "player_rush_yds_alternate", "player_reception_yds_alternate",
               "player_receptions_alternate"]
BOOKS = ["draftkings", "fanduel", "williamhill_us", "betmgm", "fanatics"]
GAME_LINE_MARKETS = ["spreads", "totals"]
KICKOFF_WINDOWS_PER_WEEK = 2  # one snapshot before 1:00 PM ET, one before the 4:05/4:25 PM ET games


def region_equiv(n_books: int) -> int:
    return math.ceil(n_books / COST_RULES["bookmakers_per_region_equivalent"])


def load_counts() -> dict[int, dict[str, int]]:
    by_season: dict[int, dict[str, int]] = defaultdict(lambda: {"weeks": 0, "main": 0, "reg": 0})
    with open(PHASE0_DOCS / "main_slate_games.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = by_season[int(row["season"])]
            s["weeks"] += 1
            s["main"] += int(row["main_slate_games"])
            s["reg"] += int(row["reg_games"])
    return dict(by_season)


def historical_season_cost(n_games: int, n_weeks: int, n_markets: int, snapshots_per_game: int = 1) -> dict[str, int]:
    r = region_equiv(len(BOOKS))
    mult = COST_RULES["historical_multiplier"]
    props = n_games * snapshots_per_game * n_markets * r * mult
    lines = n_weeks * KICKOFF_WINDOWS_PER_WEEK * len(GAME_LINE_MARKETS) * r * mult
    events = n_weeks * KICKOFF_WINDOWS_PER_WEEK * COST_RULES["historical_events_list"]
    return {"props": props, "game_lines": lines, "event_lists": events, "total": props + lines + events}


def main() -> int:
    counts = load_counts()
    r = region_equiv(len(BOOKS))
    per_game_hist = len(PROP_MARKETS) * r * COST_RULES["historical_multiplier"]
    lines: list[str] = []
    add = lines.append
    add("# The Odds API credit estimate (Phase 0)")
    add("")
    add("Nothing was spent to make this. Game counts come from the nflverse schedule; costs use the rules in")
    add("`scripts/phase0_credit_estimate.py` (COST_RULES). All figures are upper bounds.")
    add("")
    add(f"- Books: {', '.join(BOOKS)} = {len(BOOKS)} bookmakers = {r} region-equivalent")
    add(f"- Prop markets ({len(PROP_MARKETS)}): {', '.join(PROP_MARKETS)}")
    add(f"- One historical prop snapshot for one game = {len(PROP_MARKETS)} markets x {r} x "
        f"{COST_RULES['historical_multiplier']} = **{per_game_hist} credits**")
    add("")
    add("## Historical backfill, one pre-kickoff snapshot per game")
    add("")
    add("| Season | Weeks | Main-slate games | Props | Game lines | Event lists | **Total** | All 272 reg-season games |")
    add("|---|---|---|---|---|---|---|---|")
    grand = 0
    for season in (2023, 2024, 2025):
        c = counts[season]
        est = historical_season_cost(c["main"], c["weeks"], len(PROP_MARKETS))
        full = historical_season_cost(c["reg"], c["weeks"], len(PROP_MARKETS))
        grand += est["total"]
        add(f"| {season} | {c['weeks']} | {c['main']} | {est['props']:,} | {est['game_lines']:,} | "
            f"{est['event_lists']:,} | **{est['total']:,}** | {full['total']:,} |")
    add(f"| 2023-2025 | | | | | | **{grand:,}** | |")
    add("")
    c25 = counts[2025]
    alt = historical_season_cost(c25["main"], c25["weeks"], len(ALT_MARKETS))["props"]
    two_snap = historical_season_cost(c25["main"], c25["weeks"], len(PROP_MARKETS), snapshots_per_game=2)["props"]
    add("Options (2025 main slate):")
    add(f"- Add alternate-line markets ({', '.join(ALT_MARKETS)}) for distribution shape: +{alt:,} credits")
    add(f"- Two snapshots per game (e.g. Saturday night and just before kickoff) instead of one: "
        f"props become {two_snap:,} credits")
    add("")
    add("## Weekly live use (2026 season)")
    live_games = round(c25["main"] / c25["weeks"])
    per_pull = live_games * len(PROP_MARKETS) * r * COST_RULES["live_event_odds_per_market_per_region"]
    lines_pull = len(GAME_LINE_MARKETS) * r * COST_RULES["live_odds_per_market_per_region"]
    pulls = 4
    weekly = pulls * (per_pull + lines_pull)
    add("")
    add(f"- About {live_games} main-slate games a week. One full prop pull = {per_pull} credits; game lines for all")
    add(f"  games = {lines_pull} credits; events list = 0 credits.")
    add(f"- {pulls} pulls a week (Thursday night, Saturday night, Sunday ~11:45 ET, Sunday ~3:45 ET) = "
        f"**~{weekly:,} credits/week, ~{weekly * 4.35:,.0f}/month** (the Sunday 3:45 pull only needs the late games,")
    add("  so this is an upper bound).")
    add("")
    out = "\n".join(lines) + "\n"
    digest = write_verified(PHASE0_DOCS / "odds_api_credit_estimate.md", out)
    print(out)
    print(f"wrote docs/phase0/odds_api_credit_estimate.md sha256={digest[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
