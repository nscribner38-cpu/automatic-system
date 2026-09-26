"""Phase 0: inspect a DraftKings salary export (DKSalaries.csv) without modeling anything.

Usage:
  python scripts/phase0_inspect_dk_csv.py                 # newest *.csv in data/raw/dk/
  python scripts/phase0_inspect_dk_csv.py path/to/file.csv

Reports: header check, slate type (Classic vs Showdown), games and kickoff times, player counts and
salary ranges by position, DST rows, blank/duplicate IDs, and whether the slate matches the Sunday
1:00/4:05/4:25 PM ET main slate. Also handles the DK upload-template variant, where the player table
starts further down and to the right (found by locating the row containing "TeamAbbrev").
Writes docs/phase0/dk_csv_inspection.json
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dfs_builder.paths import PHASE0_DOCS, RAW_DK
from dfs_builder.safe_io import sha256_file, write_verified

EXPECTED_HEADER = ["Position", "Name + ID", "Name", "ID", "Roster Position", "Salary", "Game Info",
                   "TeamAbbrev", "AvgPointsPerGame"]
GAME_INFO_RE = re.compile(r"^(?P<away>[A-Z]{2,3})@(?P<home>[A-Z]{2,3}) (?P<date>\d{2}/\d{2}/\d{4}) (?P<time>\d{2}:\d{2}[AP]M) ET$")
ET = ZoneInfo("America/New_York")
MAIN_SLATE_TIMES = {"01:00PM", "04:05PM", "04:25PM"}


def read_player_table(path: Path) -> tuple[list[str], list[dict[str, str]], int]:
    """Return (header, rows, header_row_index). Finds the header row by the 'TeamAbbrev' cell."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        grid = list(csv.reader(f))
    for i, row in enumerate(grid):
        if "TeamAbbrev" in row:
            start = row.index("Position") if "Position" in row else 0
            header = [c.strip() for c in row[start:]]
            rows = []
            for raw in grid[i + 1:]:
                cells = raw[start:start + len(header)]
                if any(c.strip() for c in cells):
                    rows.append(dict(zip(header, cells)))
            return header, rows, i
    raise ValueError(f"{path}: no row containing 'TeamAbbrev' - not a DK salary export?")


def inspect(path: Path) -> dict:
    header, rows, header_row = read_player_table(path)
    report: dict = {"file": str(path), "sha256": sha256_file(path), "header_row_index": header_row,
                    "header": header, "header_matches_expected": header[:len(EXPECTED_HEADER)] == EXPECTED_HEADER,
                    "missing_expected_columns": [c for c in EXPECTED_HEADER if c not in header],
                    "extra_columns": [c for c in header if c not in EXPECTED_HEADER], "n_rows": len(rows)}
    roster_positions = Counter(r.get("Roster Position", "").strip() for r in rows)
    report["roster_position_counts"] = dict(roster_positions)
    report["slate_type"] = "showdown" if "CPT" in roster_positions else "classic"

    by_pos: dict[str, list[int]] = defaultdict(list)
    bad_salary, bad_game_info, blank_ids = [], [], []
    games: dict[str, dict] = {}
    for r in rows:
        name, pid = r.get("Name", "").strip(), r.get("ID", "").strip()
        if not pid:
            blank_ids.append(name)
        try:
            by_pos[r.get("Position", "").strip()].append(int(r.get("Salary", "").strip()))
        except ValueError:
            bad_salary.append(name)
        gi = r.get("Game Info", "").strip()
        m = GAME_INFO_RE.match(gi)
        if not m:
            bad_game_info.append({"name": name, "game_info": gi})
            continue
        key = f"{m['away']}@{m['home']}"
        kickoff = datetime.strptime(f"{m['date']} {m['time']}", "%m/%d/%Y %I:%M%p").replace(tzinfo=ET)
        games[key] = {"kickoff_et": kickoff.isoformat(), "weekday": kickoff.strftime("%A"), "time_et": m["time"]}

    ids = [r.get("ID", "").strip() for r in rows]
    report["positions"] = {p: {"n": len(s), "min_salary": min(s), "max_salary": max(s)} for p, s in sorted(by_pos.items())}
    report["dst_rows"] = [{"name_raw": r.get("Name", ""), "team": r.get("TeamAbbrev", ""), "id": r.get("ID", "")}
                          for r in rows if r.get("Position", "").strip() == "DST"]
    report["dst_names_with_trailing_space"] = sum(1 for d in report["dst_rows"] if d["name_raw"] != d["name_raw"].strip())
    report["duplicate_ids"] = [i for i, n in Counter(ids).items() if n > 1 and i]
    report["blank_ids"] = blank_ids
    report["bad_salary_rows"] = bad_salary
    report["unparsed_game_info"] = bad_game_info[:25]
    report["n_unparsed_game_info"] = len(bad_game_info)
    report["games"] = dict(sorted(games.items(), key=lambda kv: kv[1]["kickoff_et"]))
    report["n_games"] = len(games)
    report["teams"] = sorted({r.get("TeamAbbrev", "").strip() for r in rows})
    report["looks_like_sunday_main_slate"] = bool(games) and all(
        g["weekday"] == "Sunday" and g["time_et"] in MAIN_SLATE_TIMES for g in games.values())
    report["name_suffixes_seen"] = sorted({n.split()[-1] for n in (r.get("Name", "").strip() for r in rows)
                                           if n and n.split()[-1].rstrip(".") in {"Jr", "Sr", "II", "III", "IV", "V"}})
    return report


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        path = Path(argv[1])
    else:
        candidates = sorted(RAW_DK.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            print(f"No CSV found in {RAW_DK}. Download DKSalaries.csv from a DK NFL Classic contest page "
                  f"(Export to CSV) and save it there.")
            return 1
        path = candidates[-1]
    report = inspect(path)
    digest = write_verified(PHASE0_DOCS / "dk_csv_inspection.json", json.dumps(report, indent=2) + "\n")
    print(f"file: {path}\nslate: {report['slate_type']}, {report['n_rows']} players, {report['n_games']} games, "
          f"main slate: {report['looks_like_sunday_main_slate']}")
    print(f"header matches expected: {report['header_matches_expected']}  missing: {report['missing_expected_columns']}"
          f"  extra: {report['extra_columns']}")
    for pos, s in report["positions"].items():
        print(f"  {pos:4s} n={s['n']:4d}  salary ${s['min_salary']:,}-${s['max_salary']:,}")
    for g, info in report["games"].items():
        print(f"  {g:9s} {info['weekday']} {info['time_et']} ET")
    problems = {k: report[k] for k in ("duplicate_ids", "blank_ids", "bad_salary_rows") if report[k]}
    if report["n_unparsed_game_info"]:
        problems["unparsed_game_info"] = report["n_unparsed_game_info"]
    print(f"problems: {problems or 'none'}")
    print(f"wrote docs/phase0/dk_csv_inspection.json sha256={digest[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
