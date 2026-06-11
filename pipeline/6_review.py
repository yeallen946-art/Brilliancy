"""Pipeline stage 6 — emit review HTML and record human approve/reject (TECH_SPEC §5).

Emit HTML for the seed reviewer, then record the decision back into the work store so
7_build only ships approved games. Review state lives under content/review/.

Usage:
    python 6_review.py --game-id <id>        # emit content/review/<id>.html
    python 6_review.py --all                 # emit HTML for every game
    python 6_review.py --approve <id>        # mark approved
    python 6_review.py --reject <id>         # mark rejected
"""

from __future__ import annotations

import argparse
import os

import store
from guesspoints import apply_refinement
from review import render_game_html

REVIEW_DIR = os.path.join(store.CONTENT_DIR, "review")


def _emit(game, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{game.id}.html")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_game_html(game))
    return path


def _set_status(game_id: str, status: str, work_dir: str) -> None:
    game = store.load_game(game_id, work_dir)
    game.review_status = status
    store.save_game(game, work_dir)
    # Also persist to the tracked decisions file — survives a work-store wipe.
    store.record_decision(game_id, status)
    print(f"{game_id}: review_status = {status} (recorded in {store.DECISIONS_FILE})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit review HTML / record decisions (stage 6).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--game-id", help="emit review HTML for one game")
    group.add_argument("--all", action="store_true", help="emit review HTML for all games")
    group.add_argument("--approve", metavar="ID", help="mark a game approved")
    group.add_argument("--reject", metavar="ID", help="mark a game rejected")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    parser.add_argument("--out-dir", default=REVIEW_DIR)
    args = parser.parse_args()

    if args.approve:
        _set_status(args.approve, store.REVIEW_APPROVED, args.work_dir)
        return 0
    if args.reject:
        _set_status(args.reject, store.REVIEW_REJECTED, args.work_dir)
        return 0

    games = (
        store.load_all_games(args.work_dir)
        if args.all else [store.load_game(args.game_id, args.work_dir)]
    )
    for game in games:
        # Reviewer sees exactly what ships: same school-2 refinement as 7_build.
        apply_refinement(game)
        print(f"wrote {_emit(game, args.out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
