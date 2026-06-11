"""Pipeline stage 7 — build content.sqlite + daily JSON from approved games (TECH_SPEC §4).

Only games with review_status == approved are included (unless --all). Runs 5_validate
first as a safety gate. Usage:
    python 7_build.py
    python 7_build.py --all          # ignore review status (dev convenience)
"""

from __future__ import annotations

import argparse
import os
import shutil

import store
from build import build_sqlite, daily_date_or_none, unshippable_reasons, write_daily
from guesspoints import apply_refinement
from validate import validate_game


def main() -> int:
    parser = argparse.ArgumentParser(description="Build content.sqlite + daily JSON.")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    parser.add_argument("--db", default=os.path.join(store.CONTENT_DIR, "content.sqlite"))
    parser.add_argument("--daily-dir", default=os.path.join(store.CONTENT_DIR, "daily"))
    parser.add_argument("--all", action="store_true", help="include non-approved games")
    args = parser.parse_args()

    games = store.load_all_games(args.work_dir)

    # Honor the human's curation pick (content/curation/selected.txt) if present.
    selected = store.load_selected()
    if selected is not None:
        games = [g for g in games if g.id in selected]
        print(f"Selection list active: {len(games)} of {len(selected)} selected id(s) present.")

    if not args.all:
        games = [g for g in games if g.review_status == store.REVIEW_APPROVED]

    if not games:
        print("No games to build (need approved + selected games, or pass --all).")
        return 1

    # School-2 pacing (PRD §5): drop only-move guess points; tracked overrides win.
    for g in games:
        changes = apply_refinement(g)
        if changes["dropped"] or changes["added"]:
            print(f"{g.id}: guess points refined — dropped plies {changes['dropped']}, "
                  f"added {changes['added']}")

    # Safety gate 1: no empty / partly-annotated games may ship (reviewer guard, A/D).
    blockers = [(g.id, r) for g in games for r in [unshippable_reasons(g)] if r]
    if blockers:
        for gid, reasons in blockers:
            print(f"Refusing to build {gid}: {'; '.join(reasons)}")
        return 1

    # Safety gate 2: annotation validation must pass before shipping (hard rule #1).
    errors = [e for g in games for e in validate_game(g)]
    if errors:
        print(f"Refusing to build: {len(errors)} validation error(s). Run 5_validate.py.")
        return 1

    build_sqlite(games, args.db)
    print(f"Built {args.db} from {len(games)} game(s).")

    # Copy into the app bundle location (App/Resources/) — the app reads this via
    # ContentStore/GRDB (TECH_SPEC §3). Committed as a built artifact so the Mac can
    # build the app without running the pipeline.
    app_db = os.path.join(store.REPO_ROOT, "App", "Resources", "content.sqlite")
    os.makedirs(os.path.dirname(app_db), exist_ok=True)
    shutil.copyfile(args.db, app_db)
    print(f"Copied to {app_db} (bundle it by rebuilding the app).")

    # Daily archive: clear stale files first, then emit each game keyed by a full numeric
    # date (skip partial dates like "1910.??.??" — many classic PGNs lack a month/day).
    if os.path.isdir(args.daily_dir):
        for name in os.listdir(args.daily_dir):
            if name.endswith(".json"):
                os.remove(os.path.join(args.daily_dir, name))
    written = 0
    for g in games:
        date = daily_date_or_none(g.date)
        if date:
            write_daily(g, date, args.daily_dir)
            written += 1
    print(f"Wrote {written} daily JSON file(s) to {args.daily_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
