"""Pipeline stage 2 — score candidates for human curation (TECH_SPEC §5).

Writes content/curation/candidates.csv (ranked). Jerry/son pick the 50 MVP games into
content/curation/selected.txt (one game id per line). Usage:  python 2_curate.py
"""

from __future__ import annotations

import argparse
import csv
import os

import store
from curate import rank


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank ingested games for curation.")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    parser.add_argument("--out", default=os.path.join(store.CURATION_DIR, "candidates.csv"))
    args = parser.parse_args()

    games = store.load_all_games(args.work_dir)
    if not games:
        print("No games in the work store — run 1_ingest.py first.")
        return 1

    scores = rank(games)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["game_id", "score", "decisive", "famous", "tactic_density", "reasonable_length"])
        for c in scores:
            writer.writerow([c.game_id, c.score, c.decisive, c.has_famous, c.tactic_density, c.reasonable_length])

    print(f"Ranked {len(scores)} game(s) -> {args.out}")
    for c in scores[:10]:
        print(f"  {c.score:5.2f}  {c.game_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
