"""Phase 0: inventory of what nflreadpy (nflverse) provides for the DFS builder.

No modeling. Loads each dataset for the probe seasons, records coverage (rows, weeks,
ID columns, as-of timestamps), checks the columns later phases depend on, and measures
how well the ID systems link to each other. Writes:

  docs/phase0/nflreadpy_inventory.json   machine-readable results
  docs/phase0/main_slate_games.csv       Sunday 1:00/4:05/4:25 ET game counts per week

Downloads are cached under data/cache/nflreadpy (nflreadpy filesystem cache).
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import datetime, timezone

from dfs_builder.paths import NFLREADPY_CACHE, PHASE0_DOCS
from dfs_builder.safe_io import write_verified

os.environ.setdefault("NFLREADPY_CACHE", "filesystem")
os.environ.setdefault("NFLREADPY_CACHE_DIR", str(NFLREADPY_CACHE))
os.environ.setdefault("NFLREADPY_CACHE_DURATION", str(7 * 86400))

import nflreadpy as nfl  # noqa: E402  (must import after cache env vars are set)
import polars as pl  # noqa: E402
import requests  # noqa: E402

PROBE_SEASONS = [2023, 2024, 2025, 2026]
MAIN_SLATE_TIMES = {"13:00", "16:05", "16:25"}
ID_COLUMN_HINTS = ("gsis", "player_id", "pfr", "espn", "sleeper", "nfl_id", "game_id", "play_id", "pff", "sportradar")
TIMESTAMP_HINTS = ("dt", "date_pulled", "date_modified", "last_updated", "timestamp")

# Documented first season for each loader (from nflreadpy's own argument validation).
FIRST_SEASON = {
    "pbp": 1999, "player_stats": 1999, "team_stats": 1999, "schedules": 1999,
    "participation": 2016, "snap_counts": 2012, "injuries": 2009, "depth_charts": 2001,
    "ftn_charting": 2022, "nextgen_receiving": 2016, "pfr_advstats_rec": 2018,
    "ff_opportunity": 2006, "rosters_weekly": 2002,
}

LOADERS = {
    "pbp": lambda s: nfl.load_pbp(s),
    "player_stats": lambda s: nfl.load_player_stats(s),
    "team_stats": lambda s: nfl.load_team_stats(s),
    "participation": lambda s: nfl.load_participation(s),
    "snap_counts": lambda s: nfl.load_snap_counts(s),
    "injuries": lambda s: nfl.load_injuries(s),
    "depth_charts": lambda s: nfl.load_depth_charts(s),
    "ftn_charting": lambda s: nfl.load_ftn_charting(s),
    "nextgen_receiving": lambda s: nfl.load_nextgen_stats(s, stat_type="receiving"),
    "pfr_advstats_rec": lambda s: nfl.load_pfr_advstats(s, stat_type="rec"),
    "ff_opportunity": lambda s: nfl.load_ff_opportunity(s),
    "rosters_weekly": lambda s: nfl.load_rosters_weekly(s),
}

# Columns later phases need, grouped by purpose. Missing ones are reported, not assumed.
REQUIRED_COLUMNS = {
    "pbp": {
        "dk_scoring_and_td_budget": ["passer_player_id", "rusher_player_id", "receiver_player_id", "td_player_id",
                                      "pass_touchdown", "rush_touchdown", "return_touchdown", "two_point_conv_result",
                                      "fumble_lost", "interception", "sack", "safety", "punt_blocked"],
        "usage_and_red_zone": ["yardline_100", "goal_to_go", "down", "ydstogo", "air_yards", "complete_pass",
                               "qb_dropback", "qb_scramble", "posteam", "defteam"],
        "matchup_and_pace": ["epa", "success", "xpass", "pass_oe", "wp", "score_differential",
                             "game_seconds_remaining", "half_seconds_remaining", "drive", "qb_hit"],
        "time_keys": ["game_id", "play_id", "season", "week", "game_date", "start_time"],
    },
    "player_stats": {
        "dk_scoring": ["passing_yards", "passing_tds", "passing_interceptions", "passing_2pt_conversions",
                       "rushing_yards", "rushing_tds", "rushing_2pt_conversions", "receptions", "receiving_yards",
                       "receiving_tds", "receiving_2pt_conversions", "sack_fumbles_lost", "rushing_fumbles_lost",
                       "receiving_fumbles_lost", "special_teams_tds", "fumble_recovery_tds"],
        "usage": ["targets", "carries", "attempts", "target_share", "air_yards_share", "wopr"],
    },
    "team_stats": {
        "dk_dst_scoring": ["def_sacks", "def_interceptions", "fumble_recovery_opp", "def_tds", "special_teams_tds",
                           "def_safeties", "def_punt_blocks", "def_fg_blocks", "def_pat_blocks", "def_2pt_made"],
    },
    "participation": {
        "routes_pressure_coverage": ["offense_players", "route", "was_pressure", "time_to_throw",
                                     "defense_coverage_type", "defense_man_zone_type", "number_of_pass_rushers"],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_ff_playerids() -> tuple[pl.DataFrame, str]:
    """dynastyprocess ID crosswalk. Falls back to raw.githubusercontent.com when github.com/raw is blocked."""
    try:
        return nfl.load_ff_playerids(), "nflreadpy.load_ff_playerids()"
    except Exception as exc:  # noqa: BLE001 - report and fall back
        url = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        df = pl.read_csv(io.BytesIO(resp.content), infer_schema_length=0)
        return df, f"fallback {url} (primary failed: {type(exc).__name__})"


def week_summary(df: pl.DataFrame) -> dict | None:
    if "week" not in df.columns:
        return None
    wk = df["week"].drop_nulls()
    return {"min": int(wk.min()), "max": int(wk.max()), "n_distinct": int(wk.n_unique())}


def probe_dataset(name: str) -> tuple[dict, dict[int, pl.DataFrame]]:
    out: dict = {"first_season_documented": FIRST_SEASON.get(name), "seasons": {}}
    frames: dict[int, pl.DataFrame] = {}
    for season in PROBE_SEASONS:
        t0 = time.perf_counter()
        try:
            df = LOADERS[name](season)
        except Exception as exc:  # noqa: BLE001 - coverage gaps are results, not crashes
            out["seasons"][season] = {"available": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            continue
        frames[season] = df
        out["seasons"][season] = {
            "available": True,
            "rows": df.height,
            "weeks": week_summary(df),
            "load_seconds": round(time.perf_counter() - t0, 2),
        }
    if frames:
        cols = frames[max(frames)].columns
        out["n_columns_latest"] = len(cols)
        out["id_columns"] = [c for c in cols if any(h in c for h in ID_COLUMN_HINTS)]
        out["asof_timestamp_columns"] = [c for c in cols if c in TIMESTAMP_HINTS]
        out["columns_latest"] = cols
        if name in REQUIRED_COLUMNS:
            out["required_column_check"] = {
                purpose: {"missing": [c for c in need if c not in cols]}
                for purpose, need in REQUIRED_COLUMNS[name].items()
            }
    return out, frames


def participation_quality(part: pl.DataFrame, pbp: pl.DataFrame) -> dict:
    """How complete is 2025 participation? Personnel on every play; route only on targeted pass plays?"""
    pass_plays = pbp.filter((pl.col("pass_attempt") == 1) & pl.col("receiver_player_id").is_not_null())
    joined = pass_plays.select("game_id", "play_id").join(
        part.rename({"nflverse_game_id": "game_id"}).select("game_id", "play_id", "route", "offense_players", "was_pressure"),
        on=["game_id", "play_id"], how="left",
    )
    def non_empty(s: pl.Series) -> pl.Series:  # empty strings count as missing
        return s.cast(pl.Utf8).fill_null("").str.len_chars() > 0

    return {
        "plays_in_participation": part.height,
        "share_plays_with_offense_players": round(float(non_empty(part["offense_players"]).mean()), 4),
        "targeted_pass_plays": joined.height,
        "share_targeted_pass_plays_with_route": round(float(non_empty(joined["route"]).mean()), 4),
        "share_targeted_pass_plays_with_was_pressure": round(float(non_empty(joined["was_pressure"]).mean()), 4),
        "route_values_top": part["route"].drop_nulls().value_counts().sort("count", descending=True).head(12).to_dicts(),
        "note": "route is the route run by the targeted receiver on that play, not every route runner.",
    }


def id_linkage(ps_2025: pl.DataFrame, snaps_2025: pl.DataFrame, players: pl.DataFrame, ffids: pl.DataFrame) -> dict:
    skill = ps_2025.filter(pl.col("position").is_in(["QB", "RB", "WR", "TE"]) & (pl.col("season_type") == "REG"))
    gsis = skill.select("player_id").unique()
    p = players.select("gsis_id", "pfr_id", "espn_id", "nfl_id")
    f = ffids.select("gsis_id", "sleeper_id", "espn_id", "fantasypros_id").rename({"espn_id": "espn_id_dp"})
    linked = gsis.join(p, left_on="player_id", right_on="gsis_id", how="left").join(
        f, left_on="player_id", right_on="gsis_id", how="left"
    )
    n = linked.height

    def share(col: str) -> float:
        return round(float(linked[col].is_not_null().sum() / n), 4)

    snaps_off = snaps_2025.filter(pl.col("position").is_in(["QB", "RB", "WR", "TE", "FB"]))
    pfr_to_gsis = players.select("pfr_id", "gsis_id").drop_nulls().unique(subset="pfr_id")
    snaps_linked = snaps_off.select("pfr_player_id").unique().join(
        pfr_to_gsis, left_on="pfr_player_id", right_on="pfr_id", how="left"
    )
    return {
        "universe": "QB/RB/WR/TE with a 2025 regular-season stat line (gsis_id)",
        "n_players": n,
        "share_with_pfr_id": share("pfr_id"),
        "share_with_espn_id": share("espn_id"),
        "share_with_sleeper_id_dynastyprocess": share("sleeper_id"),
        "share_with_fantasypros_id_dynastyprocess": share("fantasypros_id"),
        "snap_counts_2025_offense_pfr_ids": snaps_linked.height,
        "snap_counts_2025_share_pfr_to_gsis": round(float(snaps_linked["gsis_id"].is_not_null().mean()), 4),
        "dynastyprocess_has_draftkings_id": any("draftkings" in c.lower() or c.lower().startswith("dk") for c in ffids.columns),
    }


def schedule_facts(sched: pl.DataFrame) -> tuple[dict, pl.DataFrame]:
    reg = sched.filter(pl.col("game_type") == "REG")
    main = reg.filter((pl.col("weekday") == "Sunday") & pl.col("gametime").is_in(sorted(MAIN_SLATE_TIMES)))
    per_week = (
        reg.group_by("season", "week").agg(pl.len().alias("reg_games"))
        .join(
            main.group_by("season", "week").agg(
                pl.len().alias("main_slate_games"),
                (pl.col("gametime") == "13:00").sum().alias("early_1pm"),
                pl.col("gametime").is_in(["16:05", "16:25"]).sum().alias("late_4pm"),
            ),
            on=["season", "week"], how="left",
        )
        .with_columns(pl.col("main_slate_games", "early_1pm", "late_4pm").fill_null(0))
        .sort("season", "week")
    )
    facts: dict = {"by_season": {}}
    for season in sorted(reg["season"].unique().to_list()):
        r = reg.filter(pl.col("season") == season)
        m = main.filter(pl.col("season") == season)
        off = r.filter(~pl.col("game_id").is_in(m["game_id"].implode()))
        facts["by_season"][season] = {
            "reg_games": r.height,
            "reg_games_played": int(r["result"].is_not_null().sum()),
            "main_slate_games": m.height,
            "games_outside_main_slate_by_day_time": off.group_by("weekday", "gametime").len().sort("len", descending=True)
            .to_dicts(),
            "share_spread_line_present": round(float(r["spread_line"].is_not_null().mean()), 4),
            "share_total_line_present": round(float(r["total_line"].is_not_null().mean()), 4),
            "roof_values": r["roof"].value_counts().sort("count", descending=True).to_dicts(),
            "share_wind_present_outdoor_played": round(float(
                r.filter((pl.col("roof").is_in(["outdoors", "open"])) & pl.col("result").is_not_null())["wind"]
                .is_not_null().mean() or 0.0), 4),
        }
    facts["distinct_stadium_ids_2023_2026"] = int(sched["stadium_id"].n_unique())
    facts["has_stadium_lat_lon"] = any(c in sched.columns for c in ("lat", "latitude", "lon", "longitude"))
    facts["note_lines"] = "spread_line/total_line are single closing-type numbers, not timestamped snapshots."
    facts["note_weather"] = "temp/wind are observed game-day values (after the fact), not forecasts."
    return facts, per_week


def main() -> int:
    started = time.perf_counter()
    report: dict = {"generated_utc": utc_now(), "nflreadpy_version": nfl.__version__,
                    "current_season": nfl.get_current_season(), "current_week": nfl.get_current_week(),
                    "probe_seasons": PROBE_SEASONS, "datasets": {}}
    frames: dict[str, dict[int, pl.DataFrame]] = {}
    for name in LOADERS:
        print(f"probing {name} ...", flush=True)
        report["datasets"][name], frames[name] = probe_dataset(name)

    print("probing schedules, players, ff_playerids ...", flush=True)
    sched = nfl.load_schedules(PROBE_SEASONS)
    report["datasets"]["schedules"] = {"first_season_documented": FIRST_SEASON["schedules"], "rows": sched.height,
                                        "columns_latest": sched.columns}
    players = nfl.load_players()
    report["datasets"]["players"] = {"rows": players.height, "columns_latest": players.columns}
    ffids, ffids_source = load_ff_playerids()
    report["datasets"]["ff_playerids"] = {"rows": ffids.height, "source": ffids_source, "columns_latest": ffids.columns}

    facts, per_week = schedule_facts(sched)
    report["schedule_facts"] = facts
    if 2025 in frames["participation"] and 2025 in frames["pbp"]:
        report["participation_quality_2025"] = participation_quality(frames["participation"][2025], frames["pbp"][2025])
    report["id_linkage_2025"] = id_linkage(frames["player_stats"][2025], frames["snap_counts"][2025], players, ffids)
    inj = frames["injuries"].get(2025)
    if inj is not None:
        report["injuries_2025_report_status"] = inj["report_status"].value_counts().sort("count", descending=True).to_dicts()
    report["runtime_seconds"] = round(time.perf_counter() - started, 1)

    PHASE0_DOCS.mkdir(parents=True, exist_ok=True)
    digest_json = write_verified(PHASE0_DOCS / "nflreadpy_inventory.json",
                                 json.dumps(report, indent=2, default=str) + "\n")
    buf = io.StringIO()
    per_week.write_csv(buf)
    digest_csv = write_verified(PHASE0_DOCS / "main_slate_games.csv", buf.getvalue())
    print(f"wrote nflreadpy_inventory.json sha256={digest_json[:16]}  main_slate_games.csv sha256={digest_csv[:16]}")
    print(f"total runtime {report['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
