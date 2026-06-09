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


@dataclass(frozen=True)
class MoveEval:
    """One candidate move's evaluation, from the MOVER's perspective.

    cp: centipawns (positive = good for the side to move), None if forced mate.
    mate: signed mate-in-N from the mover's perspective (e.g. +3 = mover mates in 3),
          None if not a mate line.

    M2 will enrich this into the `legal_evals` shape from TECH_SPEC §4 — adding
    `refutation_pv: list[str]` (engine's short reply line) and `motif: str`
    ("hangs_piece" | "drops_exchange" | "allows_fork" | "ok" | "best"). M0 only
    needs the raw eval to prove the venv + Stockfish loop works.
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


def sort_best_first(evals: list[MoveEval], n: int | None = None) -> list[MoveEval]:
    """Sort candidate moves best-first (for the mover). Keep the top `n`, or all if None.

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

    ordered = sorted(evals, key=sort_key, reverse=True)
    return ordered if n is None else ordered[:n]


def analyze_position(
    fen: str,
    *,
    depth: int = DEFAULT_DEPTH,
    multipv: int | None = None,
    engine_path: str = "stockfish",
) -> list[MoveEval]:
    """Analyze a FEN with Stockfish, returning candidate moves best-first (mover-relative).

    `multipv=None` evaluates EVERY legal move — the canonical mode per TECH_SPEC §5
    (`legal_evals` covers all legal moves so the app never needs an on-device engine).
    Pass an int to cap the count (handy for a quick smoke test).

    Requires the `stockfish` binary on PATH (or pass `engine_path`).
    """
    board = chess.Board(fen)
    legal_count = board.legal_moves.count()
    if legal_count == 0:
        return []  # checkmate / stalemate — no moves to analyze

    requested = legal_count if multipv is None else min(multipv, legal_count)

    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        infos = engine.analyse(
            board,
            chess.engine.Limit(depth=depth),
            multipv=requested,
        )

    results: list[MoveEval] = []
    for info in infos:
        pv = info.get("pv")
        if not pv:
            continue
        ev = normalize_cp_to_mover(info["score"], board.turn)
        results.append(MoveEval(uci=pv[0].uci(), cp=ev.cp, mate=ev.mate))

    return sort_best_first(results, n=multipv)
