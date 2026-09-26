# DFS lineup builder (DraftKings NFL Classic)

A research tool that builds and grades DraftKings NFL Classic lineups for the Sunday main slate from
DK salaries, sportsbook markets, matchup data and injury/weather news. It is not a promise of profit;
the goal is well-calibrated projections. The full spec is in [DFS_BUILDER_BRIEF.md](DFS_BUILDER_BRIEF.md).

## Status

- Phase 0 (data inventory): done. Read [docs/phase0/DATA_INVENTORY.md](docs/phase0/DATA_INVENTORY.md),
  which also has the Windows setup commands and the open decisions.
- Phase 1 (DK scoring, DK CSV parser, name-to-ID mapping): waiting for go-ahead.

## Layout

- `src/dfs_builder/`: library code (paths, checksum-verified writes, cache-first Odds API client)
- `scripts/`: runnable steps, one file per task
- `tests/`: `python -m pytest -q`
- `docs/`: phase reports and generated inventories
- `data/`: local only (raw DK files, caches); not committed
