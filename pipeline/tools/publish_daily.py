"""Publish work-store games as dated daily challenges (TECH_SPEC §4 CDN JSON).

Daily challenges are keyed by the CHALLENGE date (when users play it), not the game's
historical date — this maps approved games onto a schedule and writes the JSON files
into the content-CDN repo working copy (default: ../../../brilliancy-content/daily).

Only approved, fully-annotated games may ship (same guards as 7_build).

Usage:
    python tools/publish_daily.py 2026-06-10=morphy-isouard-1858-f7f676 2026-06-11=reti-...
    python tools/publish_daily.py --rotate 2026-06-10 14   # rotate approved games over N days
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store
from build import unshippable_reasons, write_daily

DEFAULT_OUT = os.path.normpath(os.path.join(
    store.REPO_ROOT, "..", "brilliancy-content", "daily"))


def shippable(game) -> bool:
    if game.review_status != store.REVIEW_APPROVED:
        print(f"  ! {game.id}: not approved — skipped", file=sys.stderr)
        return False
    reasons = unshippable_reasons(game)
    if reasons:
        print(f"  ! {game.id}: {'; '.join(reasons)} — skipped", file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish dated daily-challenge JSON.")
    parser.add_argument("pairs", nargs="*", metavar="DATE=GAME_ID",
                        help="explicit schedule entries, e.g. 2026-06-10=morphy-...")
    parser.add_argument("--rotate", nargs=2, metavar=("START", "DAYS"),
                        help="rotate all approved games starting at START for DAYS days")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    args = parser.parse_args()

    schedule: list[tuple[str, object]] = []

    if args.rotate:
        start = dt.date.fromisoformat(args.rotate[0])
        days = int(args.rotate[1])
        games = [g for g in store.load_all_games(args.work_dir) if shippable(g)]
        if not games:
            print("No shippable games.", file=sys.stderr)
            return 1
        for i in range(days):
            date = (start + dt.timedelta(days=i)).isoformat()
            schedule.append((date, games[i % len(games)]))

    for pair in args.pairs:
        date, _, game_id = pair.partition("=")
        dt.date.fromisoformat(date)  # validate format
        game = store.load_game(game_id, args.work_dir)
        if not shippable(game):
            return 1
        schedule.append((date, game))

    if not schedule:
        parser.error("nothing to publish — give DATE=GAME_ID pairs or --rotate")

    for date, game in schedule:
        path = write_daily(game, date, args.out)
        print(f"{date} -> {game.id}  ({os.path.basename(path)})")
    print(f"\nPublished {len(schedule)} file(s) to {args.out}. Commit+push that repo to go live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
