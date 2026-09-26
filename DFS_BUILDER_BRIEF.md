# DFS Lineup Builder — Build Brief for Claude Code

How to start: save this file as C:\Users\nscri\dfs-builder\DFS_BUILDER_BRIEF.md, open Claude Code in that folder, and send:
"Read DFS_BUILDER_BRIEF.md in full, then do Phase 0 only. Stop and show me the results before starting Phase 1."

---

## 1. What we're building

A DraftKings NFL Classic lineup builder for the Sunday main slate (1:00, 4:05 and 4:25 PM ET games). It takes the week's DK salaries, sportsbook market data, matchup data and injury/weather news, and produces:

1. Player projections as distributions (median, 10th percentile, 90th percentile, and TD probabilities), not just a single number.
2. Optimal lineups under DK rules for three modes: Cash (highest floor/median), GPP (ceiling and correlation), and Custom objective (for example, "maximize the chance the lineup scores 8+ rushing/receiving TDs" for promos).
3. A lineup grader: I enter 9 players and it returns a 1–10 score, the weak spots, injury flags, stack/correlation notes, a late-swap tip, and the best single swap under the cap.
4. A DK-upload-ready CSV plus a plain readable table.

This is a research tool. It is not a promise of profit. DFS is negative expected value for most players, and the honest claim is calibration: projections that are right on average and well calibrated. Agreeing with the betting market counts as validation.

## 2. Context about me and my setup

- Windows PC. Python 3.12 venv, run scripts as .\.venv\Scripts\python.exe
- Git plus a private GitHub repo (I don't have a GitHub account yet; set up local git now and remind me when the repo is ready to push).
- I have a paid The Odds API plan (20K+ credits/month), usable for live and historical game lines and player props. Budget credits: cache every response to disk with a timestamp, never refetch what's cached, and print credit usage after every pull.
- Related projects: C:\Users\nscri\nfl-model (NFL projection engine rebuild, which has an nflreadpy data layer) and an anytime-TD model. This builder is a separate project, but it should reuse nfl-model's data layer where one exists and later accept projections from nfl-model or the TD model as optional inputs. Don't import anything that hasn't passed its own checks.
- Budget for running costs is about $100–200/month, but prefer free sources.
- The long-term aim is one combined system for all my betting and DFS data, so keep data formats clean and documented so this can plug in later.

## 3. Working rules (non-negotiable)

- Key everything on player/team IDs, never names. Build and test a name-to-ID mapping between DK salary names, Odds API names and nflreadpy IDs. Log every unmatched name; never silently drop a player.
- Everything must be time-correct. Any feature used for a game must be knowable before that game's kickoff. Include a lookahead test that deliberately leaks future data and confirms the harness catches it.
- One seeded RNG per game, passed explicitly. Simulations must be reproducible.
- Every component must beat a baseline on held-out data before it's adopted. Fit on seasons up to 2024; test on untouched 2025. Decide on full held-out seasons with paired bootstrap confidence intervals, not a few weeks.
- Report negative results plainly and immediately. If a component doesn't beat its baseline, say so and don't use it. Prefer building the check that could prove the work wrong over adding the next feature.
- Time every new piece at production scale (full slate, full player pool).
- Save every projection and lineup before kickoff in a timestamped, append-only log with a checksummed ledger.
- File safety: before editing an existing file, back it up. When editing, match each anchor exactly once; if any anchor fails, write nothing. For Python files, ast.parse the result before saving. Preserve the file's original line endings (CRLF/LF). After writing any file, verify it landed by checksum, because commits sometimes report success without writing.
- When you give me commands to run, give the exact PowerShell commands in code blocks for copy-paste. Code blocks are only for runnable commands; put diagrams, folder trees and examples in plain text.
- Do not scrape DraftKings or automate contest entry. Use DK's own salary CSV export and bulk-upload CSV format.

## 4. Data inputs

1. DK salaries: the DKSalaries.csv I download from the contest page each week and drop into data\raw\dk\. Parse position, salary, game info, team, and DK player ID.
2. Market data (The Odds API):
   - Game lines: spread and total, converted to implied team totals.
   - Player props: pass yards, pass TDs, pass attempts, completions, interceptions, rush yards, rush attempts, receptions, receiving yards, anytime TD. Pull from multiple books (DraftKings, FanDuel, Caesars, BetMGM, Fanatics) and use a de-vigged consensus.
   - Check which historical prop markets the plan covers and what they cost before pulling any history. Show me the credit estimate first.
3. Game and player data (nflreadpy, via nfl-model's layer where possible): play-by-play, snap counts, participation/route data where available, target and carry shares, red-zone/goal-line usage, schedules, rosters, injury reports.
4. Matchup data derived from play-by-play: defense vs position (EPA/play and fantasy points allowed by position, adjusted for opponent strength), pace (seconds per play, neutral-situation pass rate), pressure rate vs pass-block, and run-defense vs rush-offense success rates.
5. Weather: a free forecast API (e.g. Open-Meteo) for outdoor stadiums; wind speed and precipitation at kickoff. Mark domes and retractable roofs.
6. Injuries and inactives: official reports plus a manual override file (data\overrides.csv) where I can mark a player OUT, a role change, or a salary pivot.
7. Ownership (later phase, optional): no free source exists. Start with a manual import of projected ownership CSVs; a simple ownership model can come later.

## 5. DraftKings scoring and roster rules

Implement DK NFL Classic scoring as one tested function. Verify the numbers against DK's current official rules page before coding and tell me if anything differs from this list:

- Passing: 0.04 per yard, 4 per TD, -1 per INT, +3 bonus at 300+ yards
- Rushing: 0.1 per yard, 6 per TD, +3 bonus at 100+ yards
- Receiving: 1 per reception, 0.1 per yard, 6 per TD, +3 bonus at 100+ yards
- Misc: 2-pt conversion +2, fumble lost -1, return TD +6, offensive fumble recovery TD +6
- DST: sack +1, INT +2, fumble recovery +2, return/defensive TD +6, safety +2, blocked kick +2, points allowed tiers (0: +10, 1–6: +7, 7–13: +4, 14–20: +1, 21–27: 0, 28–34: -1, 35+: -4)

Unit-test the scoring function against at least 10 real historical box scores where the DK score is known.

Roster: QB, RB, RB, WR, WR, WR, TE, FLEX (RB/WR/TE), DST. $50,000 salary cap. At least 2 different NFL games represented.

## 6. Projection layer

Build these in order. Each one is scored before the next begins.

- Baseline A, market-implied: convert de-vigged prop lines into full stat distributions, then into DK-point distributions via the scoring function. Anytime-TD odds become TD probabilities. Team totals from spread/total cap the team's total TD budget, so player TD probabilities on one team must be consistent with the implied team total.
- Baseline B, recent form: a weighted recent average with a fitted half-life.
- Model C, usage × efficiency × matchup: project opportunities (snaps, routes, targets, carries, red-zone share) and per-opportunity efficiency, adjusted for opponent, pace, game script (from the spread) and weather. Adopt it only if it beats both baselines on the held-out 2025 season.
- Blend: if C beats the baselines, test a blend with A. Keep whichever is best on held-out data.

Score projections with MAE and CRPS on DK points, calibration of the 10th/90th percentiles (does the actual land below p10 about 10% of the time?), and Brier score/log loss on TD probabilities.

## 7. Game simulator (for GPP and custom objectives)

Simulate each game jointly so correlations are real: QB with his pass catchers, a RB with his team's DST, both sides of a shootout, and a team's TDs sharing one TD budget. Calibrate the correlations from historical data, not guesses, and show me the fitted correlation table. Run at least 10,000 sims per slate with the seeded RNG. Time it.

Before the simulator is adopted, show that its player-level outputs are as well calibrated as the direct projections, and that its correlations match what's observed in 2025.

## 8. Optimizer

Use integer linear programming (PuLP with CBC, or OR-Tools).

Constraints: salary cap, positions and FLEX eligibility, lock/exclude lists, max players per team, stacking rules (QB plus N pass catchers, optional bring-back from the opponent), no offensive player facing my own DST unless I allow it, exposure limits across multiple lineups, and a minimum number of unique players between lineups.

Late swap: when a lineup has players in later games, put the latest-kickoff eligible player in FLEX, and warn me when every player in the lineup kicks off at 1:00.

Objectives:
- Cash: maximize median projected points.
- GPP: maximize simulated ceiling (e.g. 90th–95th percentile of lineup score) with correlation from the simulator; add ownership leverage once ownership data exists.
- Custom: maximize the simulated probability of a stated condition, e.g. P(total rushing + receiving TDs in lineup ≥ 8). QB passing TDs and DST scores don't count toward that condition unless I say so.

Every generated lineup must pass a validity check (cap, positions, 2+ games, no duplicates, all players active) before output.

## 9. Lineup grader

Input: 9 players (typed names or a DK lineup export). Output:
- A 1–10 score with the scale explained (where it ranks against the optimizer's top lineups for that mode)
- Projected median, 10th percentile and 90th percentile
- Weakest slot and best single swap that stays under the cap
- Injury/inactive flags, stack and correlation notes, weather flags, late-swap tip
- Probability of hitting a stated condition (e.g. 8+ rush/rec TDs) if I ask

## 10. Outputs

- Readable table: slot, player, team, opponent, kickoff time, salary, projection (median / p10 / p90), anytime-TD %.
- DK bulk-upload CSV in DK's exact template format.
- Everything logged with a timestamp before kickoff.
- Presentation comes last. It should stay dead simple for me and a friend; plain language first, numbers in small print. A simple local web page (Streamlit or similar) is fine later.

## 11. Order of work

Each phase ends with a report to me: what was built, how it was checked, what failed. Don't start the next phase until I say go.

- Phase 0: Data inventory. What's available from nflreadpy, The Odds API (with credit costs) and a sample DKSalaries.csv; what's missing; the ID-mapping plan. No modeling.
- Phase 1: DK scoring function plus unit tests against real box scores. DK CSV parser. Name-to-ID mapping with an unmatched-names report.
- Phase 2: Walk-forward backtest harness (weekly, time-correct) with the lookahead leak test. Baseline B scored on 2025.
- Phase 3: Baseline A (market-implied projections) scored on whatever 2025 history the Odds API plan allows. Compare A vs B.
- Phase 4: Single-lineup optimizer for Cash mode, plus the validity checker. Backtest: how did the optimal Cash lineup built from pre-game projections score each 2025 week, versus the hindsight-optimal lineup?
- Phase 5: Lineup grader.
- Phase 6: Model C (usage × efficiency × matchup); adopt only if it beats the baselines.
- Phase 7: Correlated game simulator, calibrated and timed.
- Phase 8: GPP mode, multi-lineup generation, exposure controls, custom objectives (TD-count promo).
- Phase 9: Weekly live pipeline: pull salaries/odds/injuries/weather, project, optimize, log, export. One command to run it.
- Phase 10: Presentation.

## 12. First deliverable

Phase 0 only: a data inventory report in plain language, plus the exact PowerShell commands I need to run (venv creation, installs, git init). Tell me anything in this brief that won't work as written.
