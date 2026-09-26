"""Canonical project paths. Everything is relative to the repo root so it works on Windows and Linux."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW_DK = DATA / "raw" / "dk"
CACHE = DATA / "cache"
NFLREADPY_CACHE = CACHE / "nflreadpy"
ODDS_API_CACHE = CACHE / "odds_api"
FREE_API_CACHE = CACHE / "free_apis"
DOCS = ROOT / "docs"
PHASE0_DOCS = DOCS / "phase0"
BACKUPS = ROOT / ".backups"
