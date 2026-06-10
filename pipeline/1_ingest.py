"""Pipeline stage 1 — ingest PGN sources into the work store (TECH_SPEC §5).

Usage:
    python 1_ingest.py                       # read content/pgn/, write content/work/
    python 1_ingest.py --source path/to/pgn  # a file or directory
"""

from __future__ import annotations

import argparse
import os

import store
from ingest import parse_pgn_text


def _pgn_files(source: str) -> list[str]:
    if os.path.isfile(source):
        return [source]
    return [
        os.path.join(source, n)
        for n in sorted(os.listdir(source))
        if n.lower().endswith(".pgn")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest PGN into the work store.")
    parser.add_argument("--source", default=store.PGN_DIR, help="PGN file or directory.")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"Source not found: {args.source}")
        return 1

    seen = store.existing_source_hashes(args.work_dir)
    decisions = store.load_decisions()  # restore human approvals after a work-store wipe
    added = skipped = 0

    for path in _pgn_files(args.source):
        with open(path, encoding="utf-8") as fh:
            for game in parse_pgn_text(fh.read()):
                if game.source_hash in seen:
                    skipped += 1
                    continue
                seen.add(game.source_hash)
                if game.id in decisions:
                    game.review_status = decisions[game.id]
                store.save_game(game, args.work_dir)
                added += 1
                restored = " (review restored)" if game.id in decisions else ""
                print(f"+ {game.id}  ({game.white} vs {game.black}, {game.year}){restored}")

    print(f"\nIngested {added} game(s), skipped {skipped} duplicate(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
