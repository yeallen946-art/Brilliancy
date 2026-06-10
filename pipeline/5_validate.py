"""Pipeline stage 5 — validate annotations before build (TECH_SPEC §5, PRD §6).

MUST pass before 7_build.py. Exits non-zero if any game has validation errors so it can
gate a build. Usage:
    python 5_validate.py --all
    python 5_validate.py --game-id <id>
"""

from __future__ import annotations

import argparse

import store
from validate import validate_game


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate annotations in the work store.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--game-id")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    args = parser.parse_args()

    games = (
        store.load_all_games(args.work_dir)
        if args.all else [store.load_game(args.game_id, args.work_dir)]
    )

    total_errors = 0
    for game in games:
        errors = validate_game(game)
        total_errors += len(errors)
        for e in errors:
            print(f"[{e.code}] {e.game_id} ply {e.ply}: {e.message}")

    annotated = sum(1 for g in games for m in g.guess_points if m.annotation)
    if total_errors:
        print(f"\nFAIL: {total_errors} error(s) across {annotated} annotated guess point(s).")
        return 1
    print(f"\nOK: {annotated} annotated guess point(s) passed validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
