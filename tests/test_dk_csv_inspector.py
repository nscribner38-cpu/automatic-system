"""The inspector must read both DK layouts. Rows here are synthetic (made-up names and IDs)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inspector", ROOT / "scripts" / "phase0_inspect_dk_csv.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)

HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"
ROWS = [
    "QB,Test Passer (1001),Test Passer,1001,QB,7000,AAA@BBB 09/27/2026 01:00PM ET,AAA,20.1",
    "RB,Test Runner Jr. (1002),Test Runner Jr.,1002,RB/FLEX,6500,AAA@BBB 09/27/2026 01:00PM ET,BBB,15.0",
    "WR,Test Catcher (1003),Test Catcher,1003,WR/FLEX,5000,CCC@DDD 09/27/2026 04:25PM ET,CCC,12.3",
    "TE,Test Tight (1004),Test Tight,1004,TE/FLEX,3000,CCC@DDD 09/27/2026 04:25PM ET,DDD,6.0",
    "DST,Testers  (1005),Testers ,1005,DST,3200,CCC@DDD 09/27/2026 04:25PM ET,DDD,7.0",
]


def test_plain_export(tmp_path):
    f = tmp_path / "DKSalaries.csv"
    f.write_text("\r\n".join([HEADER, *ROWS]) + "\r\n", encoding="utf-8")
    r = inspector.inspect(f)
    assert r["header_matches_expected"] and r["n_rows"] == 5 and r["slate_type"] == "classic"
    assert r["n_games"] == 2 and r["looks_like_sunday_main_slate"]
    assert r["dst_names_with_trailing_space"] == 1
    assert r["name_suffixes_seen"] == ["Jr."]
    assert not r["duplicate_ids"] and not r["bad_salary_rows"] and r["n_unparsed_game_info"] == 0


def test_upload_template_layout_with_offset_table(tmp_path):
    pad = "," * 10
    lines = ["QB,RB,RB,WR,WR,WR,TE,FLEX,DST,,Instructions", "", pad + HEADER] + [pad + r for r in ROWS]
    f = tmp_path / "DKSalaries_template.csv"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    r = inspector.inspect(f)
    assert r["header_matches_expected"] and r["n_rows"] == 5 and r["header_row_index"] == 2
