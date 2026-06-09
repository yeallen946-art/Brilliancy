"""Pipeline stage 7 — build content.sqlite + daily JSON from approved games (TECH_SPEC §4).

Only games with review_status == approved are included (unless --all). Runs 5_validate
first as a safety gate. Usage:
    python 7_build.py
    python 7_build.py --all          # ignore review status (dev convenience)
"""

from __future__ import annotations

import argparse
import os

import store
from build import build_sqlite, write_daily
from validate import validate_game


def main() -> int:
    parser = argparse.ArgumentParser(description="Build content.sqlite + daily JSON.")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    parser.add_argument("--db", default=os.path.join(store.CONTENT_DIR, "content.sqlite"))
    parser.add_argument("--daily-dir", default=os.path.join(store.CONTENT_DIR, "daily"))
    parser.add_argument("--all", action="store_true", help="include non-approved games")
    args = parser.parse_args()

    games = store.load_all_games(args.work_dir)
    if not args.all:
        games = [g for g in games if g.review_status == store.REVIEW_APPROVED]

    if not games:
        print("No games to build (need approved games, or pass --all).")
        return 1

    # Safety gate: validation must pass before shipping content (hard rule).
    errors = [e for g in games for e in validate_game(g)]
    if errors:
        print(f"Refusing to build: {len(errors)} validation error(s). Run 5_validate.py.")
        return 1

    build_sqlite(games, args.db)
    print(f"Built {args.db} from {len(games)} game(s).")

    # Daily archive: emit each game keyed by its date if present (skip if no date).
    written = 0
    for g in games:
        date = (g.date or "").replace(".", "-")
        if len(date) == 10 and date[4] == "-" and date[7] == "-":
            write_daily(g, date, args.daily_dir)
            written += 1
    print(f"Wrote {written} daily JSON file(s) to {args.daily_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
