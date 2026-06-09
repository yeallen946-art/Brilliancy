"""Pipeline stage 3 — Stockfish analysis (TECH_SPEC §5).

Two modes:
  --fen <FEN>      single-position smoke test (top candidate moves)
  --game-id <id>   full game: mark guess points, fill legal_evals (every legal move),
                   set eval_cp / difficulty / tags, write back to the work store

Guess-point SELECTION (which plies) is engine-independent (guesspoints.py, unit-tested);
the eval fill needs Stockfish on PATH.

Usage:
    python 3_analyze.py --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    python 3_analyze.py --game-id byrne-fischer-1956
"""

from __future__ import annotations

import argparse
import sys

import chess

import guesspoints
import store
from analysis import DEFAULT_DEPTH, analyze_legal_evals, analyze_position


def _format(move_evals, fen: str) -> str:
    board = chess.Board(fen)
    lines = [f"FEN: {fen}", f"Side to move: {'White' if board.turn else 'Black'}", ""]
    for i, m in enumerate(move_evals, start=1):
        san = board.san(chess.Move.from_uci(m.uci)) if m.uci else "?"
        score = f"#{m.mate:+d}" if m.mate is not None else f"{(m.cp or 0) / 100:+.2f}"
        lines.append(f"  {i}. {san:7s} {m.uci:6s} {score}")
    return "\n".join(lines)


def analyze_fen(args) -> int:
    evals = analyze_position(
        args.fen, depth=args.depth, multipv=args.multipv, engine_path=args.engine
    )
    print(_format(evals, args.fen))
    return 0


def analyze_game(args) -> int:
    game = store.load_game(args.game_id, args.work_dir)
    target_plies = set(guesspoints.candidate_guess_plies(game))

    marked = 0
    for move in game.moves:
        move.is_guess_point = move.ply in target_plies
        if not move.is_guess_point:
            continue
        evals = analyze_legal_evals(move.fen_before, depth=args.depth, engine_path=args.engine)
        move.legal_evals = evals
        move.eval_cp = max((e["cp"] for e in evals.values() if e["cp"] is not None), default=None)
        move.difficulty = guesspoints.difficulty_from_evals(evals)
        move.tags = guesspoints.tag_for_move(move)
        marked += 1

    store.save_game(game, args.work_dir)
    print(f"Analyzed {game.id}: marked {marked} guess point(s).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stockfish position/game analysis (stage 3).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fen", help="Analyze a single FEN position.")
    group.add_argument("--game-id", help="Analyze a full game in the work store.")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument(
        "--multipv", type=int, default=None,
        help="(--fen only) cap candidate moves; default all legal moves.",
    )
    parser.add_argument("--engine", default="stockfish", help="Path to the Stockfish binary.")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    args = parser.parse_args()

    try:
        return analyze_fen(args) if args.fen is not None else analyze_game(args)
    except FileNotFoundError as exc:
        # Either the Stockfish binary or the game file is missing.
        if args.game_id is not None and "stockfish" not in str(exc).lower():
            print(f"Game not found in work store: {args.game_id}", file=sys.stderr)
        else:
            print(
                f"Stockfish binary not found (looked for '{args.engine}'). "
                "Install it and ensure it's on PATH.",
                file=sys.stderr,
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
