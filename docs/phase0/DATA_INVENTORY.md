# Phase 0 report: data inventory

Written 2026-09-26, the Saturday before Week 3 of the 2026 season. This phase has no modeling. It covers what data exists, what it costs, what's missing, how players get matched across sources, and which parts of the brief won't work as written.

## The short version

- **Free NFL data is in good shape.** nflverse (through nflreadpy) has the complete 2023, 2024 and 2025 seasons and the 2026 season through Thursday night of Week 3. It has every stat DraftKings scores, for both players and DSTs. It also has snap counts, injury reports, depth charts and detailed play charting.
- **Its biggest gaps:**
  - It has no DraftKings player IDs.
  - It doesn't track routes run by every receiver. It only records the route of the receiver who was targeted.
  - Its "who was on the field" data (participation) is only released after a season ends, so it can't feed live 2026 projections.
- **The Odds API has the props we want back to May 2023, but history is expensive.** One pre-kickoff snapshot of 10 prop markets for every main-slate game in one season costs about **20,600 credits**. That's more than a whole month on a 20K plan. All three seasons (2023–2025) cost about **62,000 credits**. Weekly live use is cheap: about 2,000 credits a month.
- **DraftKings' salary file format is known and confirmed from real 2025 exports.** DK player IDs change every slate, so matching has to be done fresh each week by name, team and position.
- **No free, legitimate source of 2025 DK salaries exists.** That blocks the Phase 4 backtest as written. Options are listed below.
- **The DK scoring list in the brief is right except for one missing DST item.** That item is a 2-point conversion or extra-point return, worth +2. There's also one detail that matters for points allowed: DK doesn't count points the DST's own offense gives up, such as pick-sixes.
- **This GitHub repo is public.** The brief says private. Please switch it to private before any real data or logs land in it.

## 1. nflreadpy (nflverse): what's there

I probed seasons 2023–2026 with `scripts/phase0_nflreadpy_inventory.py`. Full results are in `docs/phase0/nflreadpy_inventory.json`. From a cold start the run takes 31 seconds and downloads 63 MB. With the cache it takes 7 seconds.

| Dataset | What it gives us | First season | 2025 | 2026 so far | Player key | Timestamped? |
|---|---|---|---|---|---|---|
| Play-by-play | Every play: EPA, success, air yards, field position, TD scorer, timing for pace | 1999 | Complete (weeks 1–22) | Weeks 1–3 | gsis_id | No |
| Weekly player stats | Every DK-scored stat, including 2-pt conversions, fumbles lost and return TDs; targets, carries, target share | 1999 | Complete | Weeks 1–3 | gsis_id | No |
| Weekly team stats | DST stats: sacks, INTs, fumble recoveries, defensive and special-teams TDs, safeties, blocked punts, FGs and PATs | 1999 | Complete | Weeks 1–3 | team | No |
| Snap counts (PFR) | Offensive snaps and snap share | 2012 | Complete | Weeks 1–3 | pfr_id (99.7% link to gsis_id) | No |
| Participation | Who was on the field each play, pressure, coverage type, the targeted receiver's route | 2016 | Complete: 45,184 plays, route present on 99.4% of targeted passes | **Not until after the season** | gsis_id lists per play | No |
| FTN charting | Play-action, screens, RPOs, drops, catchable balls, blitzers | 2022 | Complete | Weeks 1–3 | play | Yes (`date_pulled`) |
| Depth charts | Depth order by position | 2001 | Daily snapshots | Daily snapshots | gsis_id + espn_id | Yes (`dt`), 2025 onward only |
| Injury reports | Practice status and final game status (Out, Doubtful, Questionable) | 2009 | Complete | Weeks 1–3 | gsis_id | No |
| Next Gen Stats (receiving) | Separation, cushion, YAC over expected | 2016 | Complete | Weeks 1–3 | gsis_id | No |
| PFR advanced receiving | Drops, broken tackles | 2018 | Complete | Weeks 1–2 (lags a week) | pfr_id | No |
| Expected fantasy points (ffopportunity) | Expected vs actual PPR points | 2006 | Complete | Weeks 1–3 | gsis_id | No |
| Weekly rosters | Team, position, roster status (active, inactive, reserve) | 2002 | Complete | Weeks 1–3 | gsis_id plus pfr/espn/sleeper/etc. | No |
| Schedules | Kickoff day and time (ET), roof, stadium, one spread and total per game, observed temperature and wind | 1999 | 272 games | 272 scheduled, 33 played | game_id | No |
| Player ID crosswalks | gsis_id to pfr, espn, sleeper, fantasypros, sportradar and more | n/a | n/a | n/a | n/a | n/a |

**Main slate.** A main-slate game here means a Sunday regular-season game at 1:00, 4:05 or 4:25 PM ET. That gives 200 games in 2023, 199 in 2024 and 198 in 2025, about 11 a week. Week-by-week counts are in `docs/phase0/main_slate_games.csv`.

**ID coverage.** Of the 610 QBs, RBs, WRs and TEs with a 2025 stat line:

| Linked to | Share |
|---|---|
| PFR ID | 99.7% |
| ESPN ID | 100% |
| Sleeper ID | 100% |
| DraftKings ID | 0% (no DK ID exists in any nflverse or dynastyprocess table) |

**Things to watch in this data:**
- **Spread and total in the schedule.** Each game has one number, roughly the closing line, with no timestamp. That's fine as a free cross-check. It can't replace timestamped odds for anything that needs to know *when* a line was available.
- **Temperature and wind in the schedule.** These are what actually happened at the game, not forecasts. Using them in a backtest would leak information, so backtests need archived forecasts (see Weather below).
- **ffopportunity.** Its "expected" columns come from a model fit on past seasons, so using them for a 2025 test could leak 2025 information. Its raw counts are safe. The expected columns are not safe unless we refit the model ourselves.
- **Injury reports.** They have no timestamps. The Friday final status is known before Sunday. Later changes, such as a Saturday downgrade, can't be dated.
- **nfl-model's data layer.** Your `C:\Users\nscri\nfl-model` project isn't reachable from this cloud session because it lives only on your PC. Until it's on GitHub and added here, I'll use nflreadpy directly with the same gsis_id keys, so it can be swapped in later.

## 2. The Odds API: coverage and credit costs

These come from the official v4 docs. I read copies of them because this cloud session's network can't reach the-odds-api.com. The cost rules are in `scripts/phase0_credit_estimate.py` with the source URL.

**Cost rules:**
- The sports list and events list are free.
- A live prop call for one game costs 1 credit per market that actually comes back.
- A call to list which markets a game has costs 1 credit.
- A historical prop call costs **10 credits per market per game**. A historical events list costs 1.
- Up to 10 bookmakers count as one "region." That means your 5 books (DraftKings, FanDuel, Caesars `williamhill_us`, BetMGM, Fanatics) cost the same as one book. All five are in the `us` region. The docs say Caesars and Fanatics need a paid plan.

**History:**
- Game lines go back to June 2020.
- Player props go back to **2023-05-03**, with a snapshot every 5 minutes.
- A historical request returns the latest snapshot at or before the time you ask for.

**Markets.** All 10 markets in the brief exist: `player_pass_yds`, `player_pass_tds`, `player_pass_attempts`, `player_pass_completions`, `player_pass_interceptions`, `player_rush_yds`, `player_rush_attempts`, `player_receptions`, `player_reception_yds`, `player_anytime_td`. Every yardage and count market also has an `_alternate` version, and those help pin down the shape of a player's distribution.

**Credit estimate.** This uses one snapshot about 30 minutes before each game's kickoff. It's an upper bound: markets a book doesn't post cost nothing. The full breakdown is in `docs/phase0/odds_api_credit_estimate.md`.

| Pull | Credits |
|---|---|
| 2025 main slate, 10 prop markets, plus game lines | 20,556 |
| 2024 main slate, same | 20,656 |
| 2023 main slate, same | 20,756 |
| **2023–2025 total** | **61,968** |
| Add 4 alternate-line markets (2025) | +7,920 |
| Live 2026: 4 pulls a week, about 11 games | about 450 a week, about 1,950 a month |

**Recommendation.** Buy one month of the 100K plan (listed at $59 a month; please confirm the price on their site) and pull 2023–2025 in that month. Then drop back to 20K for the season. You need 2023–2024 to fit how prop lines turn into full distributions without touching 2025. On the 20K plan the same pull would take about 3 months.

**Not yet checked.** I haven't checked which books actually post which props, how many players each covers, or whether anytime-TD has a "No" side. The docs don't say. `scripts/phase0_odds_api_probe.py` finds out for a worst case of **112 credits** (one upcoming game and one 2025 game). Run it with the dry run first; the dry run is free and shows the plan. The probe also checks that Odds API team names match nflverse teams.

## 3. DraftKings files

I couldn't open draftkings.com from this session because the network blocks it. The format below is confirmed from real 2025 DK exports that people posted publicly, plus DK's own instructions embedded in its template files.

**DKSalaries.csv:**
- Header row: `Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame`.
- Game Info looks like `CLE@BAL 09/14/2025 01:00PM ET`.
- Roster Position is `QB`, `RB/FLEX`, `WR/FLEX`, `TE/FLEX` or `DST`.
- DST names are the team nickname with a trailing space, for example `Browns `.
- **Player IDs change every slate.** For example, the same player had three different IDs in Weeks 1, 2 and 12 of 2025. So a DK ID is only good for one slate.
- `AvgPointsPerGame` is DK's own season-to-date average. That makes it a free check on our scoring function.

**Upload file:**
- Header: `QB,RB,RB,WR,WR,WR,TE,FLEX,DST`.
- Each cell holds the player's DK ID (or "Name (ID)"). Names alone are rejected.
- Up to 500 lineups per file.
- The late-swap edit file (DKEntries.csv) has `Entry ID,Contest Name,Contest ID,Entry Fee` in front of the nine slots.

**Inspector.** `scripts/phase0_inspect_dk_csv.py` reads either layout and reports:
- slate type
- games and kickoff times
- counts and salary ranges by position
- blank or duplicate IDs
- whether it's the Sunday main slate

It's tested on made-up rows only, because **I don't have a real DKSalaries.csv yet**. Please download tomorrow's Week 3 Classic main-slate file and run it (commands below).

## 4. What's missing, and what to do about it

| Missing | Why it matters | Proposed fix |
|---|---|---|
| 2025 DK salaries | The Phase 4 backtest needs each week's real salaries. RotoGuru's DK data stops after 2021, and I found no free, legitimate 2025 source. | (a) Use any 2025 DK files you saved. (b) Buy one month of a paid historical-salary service. (c) Run the Phase 4 backtest on 2026 weeks as you collect files; a full season is then only ready in January. |
| DK scores to test scoring against | The brief asks for 10 or more real box scores with known DK points. | Use DK's own `AvgPointsPerGame` from each week's salary file; that's hundreds of checks a week, free. Also copy about 10 single-game scores from DK player cards in the app. |
| Routes run by every receiver | Model C wants routes and targets per route run. | Only the targeted receiver's route is free. Use "on the field for a dropback" from participation (2016–2025), plus snap counts for 2026. Per-player routes are sold by PFF. |
| Participation for 2026 | Nothing built on it can run live this season. | Use it only for features we can also compute live, or accept that Model C runs without those features live. |
| Stadium coordinates | Needed to pull weather. | Build a small table of the 41 stadiums used in 2023–2026 (one-time job). |
| Time-correct weather for backtests | The schedule's weather is what was observed. | Open-Meteo archives past forecasts (Historical Forecast and Previous Runs APIs). I couldn't reach it from here, so it needs checking from your PC. |
| Live inactives (90 minutes before kickoff) | Needed for "all players active". | Use `data\overrides.csv` plus a free, documented injury-status feed (the Sleeper API is a candidate; not yet checked). |
| Ownership | GPP leverage | Manual CSV import, as the brief already says. |

## 5. ID-mapping plan (built in Phase 1)

- **Anchors:**
  - **Players:** nflverse `gsis_id` (for example `00-0033873`).
  - **Teams:** the nflverse abbreviation (note it uses `LA` for the Rams).
  - **Games:** nflverse `game_id`.
- **Team map:** one tested 32-row table covering DK `TeamAbbrev`, Odds API full names ("Los Angeles Rams") and the nflverse abbreviation. The probe already flags any Odds API team name it can't map.
- **DK players.** DK IDs change every slate, so each salary file is matched fresh against that week's nflverse roster, in this order:
  1. Your manual override file (`data/id_overrides.csv`) wins.
  2. Exact normalized name + team + position. Normalizing means lowercase, punctuation stripped, Jr./Sr./II/III removed and accents folded, so "D.J. Moore" matches "DJ Moore".
  3. Same name + position on any team (catches trades).
  4. nflverse `football_name` + last name (catches "Hollywood" Brown-type cases).
  5. Close fuzzy match, same team and position only. These are marked "needs review", never silently accepted.
  6. Anything left goes in an unmatched report with the top 3 suggestions. Nothing is dropped silently.
  7. DSTs match on team.
- **Odds API players.** Prop names carry no team, but each game gives home and away teams. So each name is matched only against the about 100 players on those two rosters, with the same steps and the same unmatched report.
- **Output.** A crosswalk per slate: DK draft group, DK ID, gsis_id, match method, confidence and timestamp. It's saved and checksummed like everything else.
- **Tests.** A golden list of hard cases:
  - suffixes, initials, hyphens and apostrophes
  - two players with the same name (for example Josh Allen QB vs Josh Allen LB, which position filtering separates)
  - traded players and rookies

## 6. What in the brief won't work as written

1. **The repo is public, not private.** The GitHub repo is `nscribner38-cpu/automatic-system`, so you do have a GitHub account now. Make it private: on GitHub go to Settings, then General, then Danger Zone, then Change visibility. Until then I've kept raw DK files, API caches and keys out of git (`.gitignore`).
2. **This session isn't your Windows PC.** It runs in a cloud container. It can't see `C:\Users\nscri\nfl-model`, it has no Odds API key, and its network blocks The Odds API, Open-Meteo, Sleeper and DraftKings. So anything touching those runs on your PC, using the commands below. If you'd rather I run it here, allow those hosts in this environment's network settings and store the key as an environment variable named `ODDS_API_KEY`. Never paste the key into chat or the repo.
3. **History costs more than the 20K plan allows.** See section 2. One season is about 20,600 credits, and fitting on 2023–2024 while testing on 2025 needs about 62,000.
4. **The Phase 4 backtest has no 2025 salary source.** See section 4. Pick (a), (b) or (c).
5. **The scoring tests need a source of known DK scores.** See section 4. The fix is DK's own AvgPointsPerGame plus about 10 scores copied from the DK app.
6. **DK scoring differences (I couldn't open DK's live page, so please check it yourself):**
   - The brief's DST list is missing **"2-pt conversion / extra point return: +2"**.
   - **DST points allowed only counts points given up while the defense is on the field.** Pick-sixes and fumble-return TDs against the DST team's own offense don't count. Safeties probably don't count either, but I couldn't confirm that.
   - The offensive "return TD" is DK's "punt/kickoff/FG return for TD +6". A 2-point conversion pays +2 to both the passer and the receiver.
   - Please open https://www.draftkings.com/help/rules/nfl and confirm the DST section. This also matters for the "RB with his DST" correlation, because a pick-six thrown by the RB's own QB doesn't hurt that DST's points allowed.
7. **DK has no max-players-per-team rule in NFL Classic.** The only game rule is "at least 2 games". The brief's "max players per team" is fine as our own optional constraint.
8. **Baseline A can't cover everyone.** There are no props for DSTs, and backups often have none. Baseline A needs a fallback for those players, and the A-vs-B comparison should be scored on players both cover, with coverage reported. Also, anytime-TD markets often only show "Yes", so de-vigging them needs an assumed margin. That assumption will be checked on 2023–2024.
9. **Bootstrap by week (or game), not by player row.** Players in the same game move together. Resampling rows would make the confidence intervals look tighter than they are. This refines the brief's "paired bootstrap" rule rather than replacing it.
10. **"Main slate" can only be approximated for backtests.** Schedules give Sunday 1:00, 4:05 and 4:25 PM ET games. DK's real slate occasionally differs, for example in Week 18 and holiday weeks. Going forward the DK file is the source of truth.
11. **Timing.** Week 3 kicks off tomorrow, and the builder won't be usable for it. Downloading tomorrow's DKSalaries.csv is still valuable, because it becomes the Phase 1 test file.

## 7. Commands to run on your PC (PowerShell)

These steps assume you haven't created `C:\Users\nscri\dfs-builder` yet. If you already did (for example, to save the brief), rename that folder first, because the clone needs an empty destination.

Step 0, only if the folder already exists:

```powershell
Rename-Item C:\Users\nscri\dfs-builder dfs-builder-old
```

Step 1: install Git and Python 3.12. Skip either one if you already have it.

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
```

Step 2: download the project into `C:\Users\nscri\dfs-builder` and switch to the working branch.

```powershell
cd C:\Users\nscri
git clone https://github.com/nscribner38-cpu/automatic-system.git dfs-builder
cd C:\Users\nscri\dfs-builder
git checkout claude/dfs-lineup-builder-brief-w48smm
```

Step 3: create the virtual environment and install the pinned packages.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
```

Step 4: run the tests, the nflverse inventory and the credit estimate. All of these are free.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\phase0_nflreadpy_inventory.py
.\.venv\Scripts\python.exe scripts\phase0_credit_estimate.py
```

Step 5: save your Odds API key as a Windows user environment variable. Replace the placeholder with your key, then close PowerShell and open a new window so it takes effect.

```powershell
[Environment]::SetEnvironmentVariable("ODDS_API_KEY", "PASTE_YOUR_KEY_HERE", "User")
```

Step 6: in the new window, run the probe as a free dry run first, then for real (112 credits at most).

```powershell
cd C:\Users\nscri\dfs-builder
.\.venv\Scripts\python.exe scripts\phase0_odds_api_probe.py
.\.venv\Scripts\python.exe scripts\phase0_odds_api_probe.py --run
```

Step 7: make the DK folder. Save DKSalaries.csv into it from a Week 3 NFL Classic main-slate contest page (the "Export to CSV" link), then inspect it.

```powershell
New-Item -ItemType Directory -Force data\raw\dk
.\.venv\Scripts\python.exe scripts\phase0_inspect_dk_csv.py
```

Step 8: send the results back to me. This commits only the summaries in `docs\phase0`. The raw DK file and API caches stay on your PC. Git will ask you to sign in to GitHub in your browser the first time.

```powershell
git add docs/phase0
git commit -m "Phase 0: Odds API probe and DK file inspection from Windows"
git push
```

## 8. Decisions I need from you before Phase 1

1. Make the repo private.
2. The Odds API history budget. Choose one:
   - one month on the 100K plan to pull 2023–2025 (recommended)
   - pull 2024–2025 on the 20K plan over about 2 months
   - something else
3. The 2025 salary source for Phase 4: option (a), (b) or (c) in section 4.
4. Confirm the two DST rules on DK's rules page (section 6, item 6).
5. Optional: put `nfl-model` in a private GitHub repo if you want me to reuse its data layer.

## Folder layout after Phase 0

    automatic-system/            (clone it as C:\Users\nscri\dfs-builder)
      DFS_BUILDER_BRIEF.md       the brief
      README.md
      requirements.txt           pinned packages
      pyproject.toml
      src/dfs_builder/
        paths.py                 project folders
        safe_io.py               backup, then write, then checksum-verify
        odds_api.py              cache-first Odds API client with a credit ceiling
      scripts/
        phase0_nflreadpy_inventory.py
        phase0_credit_estimate.py
        phase0_odds_api_probe.py
        phase0_inspect_dk_csv.py
      tests/                     12 tests (cache never refetches, key never saved, budget guard,
                                 safe writes, DK file layouts)
      docs/phase0/               this report and the generated inventories
      data/raw/dk/               your DKSalaries.csv files (not committed)
      data/cache/                nflverse and Odds API caches (not committed)
