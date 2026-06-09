"""Tests for the engine-free analysis helpers — no Stockfish binary required.

Stage 5 (`5_validate.py`) gets its own known-bad-annotation suite in M2 (TECH_SPEC §9).
"""

import chess
import chess.engine

from analysis import MoveEval, normalize_cp_to_mover, sort_best_first


def test_normalize_cp_white_to_move():
    # +50cp from White's POV, White to move -> +50 for the mover.
    score = chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE)
    ev = normalize_cp_to_mover(score, chess.WHITE)
    assert ev.cp == 50 and ev.mate is None


def test_normalize_cp_black_to_move_flips_sign():
    # +50cp stored from White's POV becomes -50 for Black when Black is the mover.
    score = chess.engine.PovScore(chess.engine.Cp(50), chess.WHITE)
    ev = normalize_cp_to_mover(score, chess.BLACK)
    assert ev.cp == -50 and ev.mate is None


def test_normalize_mate_for_mover():
    score = chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE)
    ev = normalize_cp_to_mover(score, chess.WHITE)
    assert ev.mate == 3 and ev.cp is None


def test_sort_best_first_orders_and_truncates():
    evals = [
        MoveEval("a", cp=-20, mate=None),
        MoveEval("b", cp=120, mate=None),
        MoveEval("c", cp=None, mate=2),     # mate for mover — best
        MoveEval("d", cp=None, mate=-1),    # getting mated — worst
        MoveEval("e", cp=35, mate=None),
    ]
    top = sort_best_first(evals, n=3)
    assert [m.uci for m in top] == ["c", "b", "e"]


def test_sort_best_first_returns_all_when_n_none():
    # n=None is the canonical "all legal moves" mode (TECH_SPEC §5).
    evals = [
        MoveEval("a", cp=-20, mate=None),
        MoveEval("b", cp=120, mate=None),
        MoveEval("d", cp=None, mate=-1),
    ]
    ordered = sort_best_first(evals)
    assert [m.uci for m in ordered] == ["b", "a", "d"]


def test_sort_best_first_faster_mate_wins():
    evals = [
        MoveEval("slow", cp=None, mate=5),
        MoveEval("fast", cp=None, mate=1),
    ]
    top = sort_best_first(evals)
    assert [m.uci for m in top] == ["fast", "slow"]
