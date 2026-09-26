# The Odds API credit estimate (Phase 0)

Nothing was spent to make this. Game counts come from the nflverse schedule; costs use the rules in
`scripts/phase0_credit_estimate.py` (COST_RULES). All figures are upper bounds.

- Books: draftkings, fanduel, williamhill_us, betmgm, fanatics = 5 bookmakers = 1 region-equivalent
- Prop markets (10): player_pass_yds, player_pass_tds, player_pass_attempts, player_pass_completions, player_pass_interceptions, player_rush_yds, player_rush_attempts, player_receptions, player_reception_yds, player_anytime_td
- One historical prop snapshot for one game = 10 markets x 1 x 10 = **100 credits**

## Historical backfill, one pre-kickoff snapshot per game

| Season | Weeks | Main-slate games | Props | Game lines | Event lists | **Total** | All 272 reg-season games |
|---|---|---|---|---|---|---|---|
| 2023 | 18 | 200 | 20,000 | 720 | 36 | **20,756** | 27,956 |
| 2024 | 18 | 199 | 19,900 | 720 | 36 | **20,656** | 27,956 |
| 2025 | 18 | 198 | 19,800 | 720 | 36 | **20,556** | 27,956 |
| 2023-2025 | | | | | | **61,968** | |

Options (2025 main slate):
- Add alternate-line markets (player_pass_yds_alternate, player_rush_yds_alternate, player_reception_yds_alternate, player_receptions_alternate) for distribution shape: +7,920 credits
- Two snapshots per game (e.g. Saturday night and just before kickoff) instead of one: props become 39,600 credits

## Weekly live use (2026 season)

- About 11 main-slate games a week. One full prop pull = 110 credits; game lines for all
  games = 2 credits; events list = 0 credits.
- 4 pulls a week (Thursday night, Saturday night, Sunday ~11:45 ET, Sunday ~3:45 ET) = **~448 credits/week, ~1,949/month** (the Sunday 3:45 pull only needs the late games,
  so this is an upper bound).

