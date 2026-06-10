"""Deterministic chess-fact extractor (TECH_SPEC §5.1) — the single source of truth.

Computes the verifiable facts the LLM is allowed to narrate and the validator checks
against: mating pattern (which pieces check / support the net at a mate), material
changes along a line, and simple move character (check/capture/mate). One extractor,
two consumers — 4_annotate's prompt and 5_validate's ground truth.

Motif detection (fork/pin/skewer) is incremental per the spec; start with the facts
that caused real errors (mating pieces, material claims).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import chess

PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}


@dataclass
class MatePattern:
    is_mate: bool
    checkers: list[str] = field(default_factory=list)    # e.g. ["bishop@d8"]
    supporters: list[str] = field(default_factory=list)  # pieces covering escape squares

    @property
    def participant_kinds(self) -> set[str]:
        return {p.split("@")[0] for p in self.checkers + self.supporters}

    def kind_count(self, kind: str) -> int:
        return sum(1 for p in self.checkers + self.supporters if p.startswith(kind + "@"))


def mate_pattern(fen_before: str, uci: str) -> MatePattern:
    """If `uci` delivers mate, compute exactly which pieces check and which cover the
    king's escape squares — from the board, never from memory (the 'two bishops' fix)."""
    board = chess.Board(fen_before)
    try:
        board.push(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return MatePattern(is_mate=False)
    if not board.is_checkmate():
        return MatePattern(is_mate=False)

    winner = not board.turn  # side that just moved
    king = board.king(board.turn)

    def describe(sq: int) -> str:
        return f"{PIECE_NAMES[board.piece_at(sq).piece_type]}@{chess.square_name(sq)}"

    checkers = sorted(describe(s) for s in board.attackers(winner, king))

    supporters: set[str] = set()
    for sq in chess.SQUARES:
        if chess.square_distance(sq, king) == 1:
            occupant = board.piece_at(sq)
            if occupant is not None and occupant.color == board.turn:
                continue  # blocked by the defender's own piece, not our cover
            for attacker_sq in board.attackers(winner, sq):
                desc = describe(attacker_sq)
                if desc not in checkers:
                    supporters.add(desc)

    return MatePattern(is_mate=True, checkers=checkers, supporters=sorted(supporters))


@dataclass
class LineMaterial:
    captures: list[str] = field(default_factory=list)  # e.g. ["pawn@d5", "knight@e4"]
    net_pawns: int = 0   # material swing from the MOVER's perspective, pawn units


def line_material(fen_before: str, uci: str, continuation: list[str]) -> LineMaterial:
    """Material changes along move + continuation, from the mover's perspective.
    Backs every 'wins/loses a pawn/piece' claim with computed captures."""
    board = chess.Board(fen_before)
    mover = board.turn
    result = LineMaterial()
    for raw in [uci, *(continuation or [])]:
        try:
            move = chess.Move.from_uci(raw)
        except ValueError:
            break
        if not board.is_legal(move):
            break
        if board.is_capture(move):
            victim_sq = move.to_square
            victim = board.piece_at(victim_sq)
            if victim is None and board.is_en_passant(move):
                victim_sq = move.to_square + (-8 if board.turn == chess.WHITE else 8)
                victim = board.piece_at(victim_sq)
            if victim is not None:
                result.captures.append(
                    f"{PIECE_NAMES[victim.piece_type]}@{chess.square_name(victim_sq)}")
                value = PIECE_VALUES[victim.piece_type]
                result.net_pawns += value if board.turn == mover else -value
        board.push(move)
    return result


def move_character(fen_before: str, uci: str) -> list[str]:
    """Simple computed character tags for one move: check / capture / mate / promotion."""
    board = chess.Board(fen_before)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return []
    tags: list[str] = []
    if board.is_capture(move):
        tags.append("capture")
    if move.promotion:
        tags.append("promotion")
    if board.is_legal(move):
        board.push(move)
        if board.is_checkmate():
            tags.append("mate")
        elif board.is_check():
            tags.append("check")
    return tags
