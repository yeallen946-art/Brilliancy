"""Pipeline stage 3 — Stockfish analysis (TECH_SPEC §5).

M0 scope: analyze a single position so we can confirm the venv + Stockfish loop works
end to end on Windows. Full per-game analysis (eval + top5 per ply, guess-point marking,
difficulty + tags, writing to the work DB) lands in M2.

Usage:
    python 3_analyze.py --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    python 3_analyze.py --game-id <id>     # M2 — not yet implemented
"""

from __future__ import annotations

import argparse
import sys

import chess

from analysis import DEFAULT_DEPTH, analyze_position


def _format(move_evals, fen: str) -> str:
    board = chess.Board(fen)
    lines = [f"FEN: {fen}", f"Side to move: {'White' if board.turn else 'Black'}", ""]
    for i, m in enumerate(move_evals, start=1):
        san = board.san(chess.Move.from_uci(m.uci)) if m.uci else "?"
        if m.mate is not None:
            score = f"#{m.mate:+d}"
        else:
            score = f"{(m.cp or 0) / 100:+.2f}"
        lines.append(f"  {i}. {san:7s} {m.uci:6s} {score}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stockfish position analysis (pipeline stage 3).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fen", help="Analyze a single FEN position (M0).")
    group.add_argument("--game-id", help="Analyze a full game from the work DB (M2).")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument(
        "--multipv",
        type=int,
        default=None,
        help="Cap candidate moves (default: all legal moves, per TECH_SPEC §5).",
    )
    parser.add_argument("--engine", default="stockfish", help="Path to the Stockfish binary.")
    args = parser.parse_args()

    if args.game_id is not None:
        print("Per-game analysis is not implemented until M2.", file=sys.stderr)
        return 2

    try:
        evals = analyze_position(
            args.fen, depth=args.depth, multipv=args.multipv, engine_path=args.engine
        )
    except FileNotFoundError:
        print(
            f"Stockfish binary not found (looked for '{args.engine}'). "
            "Install it and ensure it's on PATH.",
            file=sys.stderr,
        )
        return 1

    print(_format(evals, args.fen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
