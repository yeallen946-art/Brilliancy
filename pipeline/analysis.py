"""Stockfish position analysis for the content pipeline (TECH_SPEC §3.2, §5 stage 3).

The engine-free helpers (`normalize_cp_to_mover`, `pick_top_n`) are pure and unit-tested
without Stockfish; `analyze_position` drives the engine and needs `stockfish` on PATH.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess
import chess.engine

# Depth target per TECH_SPEC §5 (depth ~22, or ~200ms/pos). Tunable.
DEFAULT_DEPTH = 22
DEFAULT_MULTIPV = 5


@dataclass(frozen=True)
class MoveEval:
    """One candidate move's evaluation, from the MOVER's perspective.

    cp: centipawns (positive = good for the side to move), None if forced mate.
    mate: signed mate-in-N from the mover's perspective (e.g. +3 = mover mates in 3),
          None if not a mate line.
    """

    uci: str
    cp: int | None
    mate: int | None


def normalize_cp_to_mover(score: chess.engine.PovScore, mover: chess.Color) -> MoveEval:
    """Convert an engine PovScore into a MoveEval from the mover's point of view.

    The content DB stores evals normalized to the side to move so scoring math
    (eval_delta) is perspective-agnostic at runtime.
    """
    pov = score.pov(mover)
    mate = pov.mate()
    if mate is not None:
        return MoveEval(uci="", cp=None, mate=mate)
    return MoveEval(uci="", cp=pov.score(), mate=None)


def pick_top_n(evals: list[MoveEval], n: int = DEFAULT_MULTIPV) -> list[MoveEval]:
    """Sort candidate moves best-first (for the mover) and keep the top n.

    Mate-for-mover beats any cp; mate-against-mover loses to any cp. Among cp lines,
    higher is better; among mate lines, mate-in-fewer is better.
    """

    def sort_key(m: MoveEval) -> tuple[int, float]:
        if m.mate is not None:
            if m.mate > 0:
                # Faster mate ranks higher: large base minus distance.
                return (2, 1_000_000 - m.mate)
            else:
                # Being mated: slower (more negative N) is "less bad".
                return (0, m.mate)
        return (1, float(m.cp if m.cp is not None else 0))

    return sorted(evals, key=sort_key, reverse=True)[:n]


def analyze_position(
    fen: str,
    *,
    depth: int = DEFAULT_DEPTH,
    multipv: int = DEFAULT_MULTIPV,
    engine_path: str = "stockfish",
) -> list[MoveEval]:
    """Analyze a FEN with Stockfish and return the top `multipv` moves, mover-relative.

    Requires the `stockfish` binary on PATH (or pass `engine_path`).
    """
    board = chess.Board(fen)
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        infos = engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            multipv=multipv,
        )

    results: list[MoveEval] = []
    for info in infos:
        pv = info.get("pv")
        if not pv:
            continue
        ev = normalize_cp_to_mover(info["score"], board.turn)
        results.append(MoveEval(uci=pv[0].uci(), cp=ev.cp, mate=ev.mate))

    return pick_top_n(results, n=multipv)
