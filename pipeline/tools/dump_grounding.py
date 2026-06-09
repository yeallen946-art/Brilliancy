"""Print the grounded engine data per guess point (the data annotations must cite).

Usage: python tools/dump_grounding.py [game_id]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store
from annotate import candidate_rows


def main(game_id: str | None) -> int:
    games = [store.load_game(game_id)] if game_id else store.load_all_games()
    for game in games:
        print("#" * 72)
        print(f"GAME {game.id} | {game.white} vs {game.black} {game.year} | "
              f"hero={game.hero_color} result={game.result}")
        for move in game.guess_points:
            if not move.legal_evals:
                continue
            print(f"\n--- ply {move.ply} | {move.mover} to move | master {move.san} ({move.uci})")
            print(f"    FEN {move.fen_before}")
            for row in candidate_rows(move):
                entry = move.legal_evals.get(row["uci"], {})
                ref = " ".join(entry.get("refutation_pv") or [])
                tag = " [MASTER]" if row["is_master"] else ""
                print(f"    {row['san']:8s} {row['uci']:6s} {row['eval']:>6s} "
                      f"({row['motif']}){tag}  reply: {ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
