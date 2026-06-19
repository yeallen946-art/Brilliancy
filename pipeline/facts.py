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

# ---- Chinese terminology (PRD §12.1: deterministic tables, never LLM-invented) ----
# Single source of truth for zh chess terms; consumed by the annotate prompt and any
# zh validation patterns. Moves stay in algebraic notation (Bg5+) in zh prose.

PIECE_NAMES_ZH = {
    "pawn": "兵", "knight": "马", "bishop": "象",
    "rook": "车", "queen": "后", "king": "王",
}

MOTIF_ZH = {
    "fork": "双吃",
    "pin": "牵制",
    "discovered_check": "闪将",
    "skewer": "串击",
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


def tactical_motifs(fen_before: str, uci: str) -> list[str]:
    """Detect simple tactical motifs created by `uci` (TECH_SPEC §5.1, incremental).

    Deterministic and conservative — only patterns that are unambiguous from the board:
    - "fork": the moved piece attacks >=2 enemy non-pawn pieces, at least one of them
      king/queen/rook (the classic family fork shape).
    - "pin": an enemy piece is absolutely pinned after the move that wasn't before.
    - "discovered_check": the position is check but the moved piece is not a checker.
    - "skewer": the moved slider hits a high-value piece with a lesser piece behind it.
    Batteries etc. are future increments — better to miss a motif than invent one.
    """
    board = chess.Board(fen_before)
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return []
    if not board.is_legal(move):
        return []
    mover = board.turn
    opponent = not mover

    pinned_before = {
        sq for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.color == opponent and board.is_pinned(opponent, sq)
    }
    board.push(move)

    motifs: list[str] = []

    # fork — from the moved piece's destination square
    big_targets = 0
    any_targets = 0
    for sq in board.attacks(move.to_square):
        victim = board.piece_at(sq)
        if victim and victim.color == opponent and victim.piece_type != chess.PAWN:
            any_targets += 1
            if victim.piece_type in (chess.KING, chess.QUEEN, chess.ROOK):
                big_targets += 1
    if any_targets >= 2 and big_targets >= 1:
        motifs.append("fork")

    # pin — newly pinned enemy piece
    pinned_after = {
        sq for sq in chess.SQUARES
        if (p := board.piece_at(sq)) and p.color == opponent and board.is_pinned(opponent, sq)
    }
    if pinned_after - pinned_before:
        motifs.append("pin")

    # discovered check — it's check, but not (only) from the moved piece
    if board.is_check() and move.to_square not in board.checkers():
        motifs.append("discovered_check")

    # skewer — the moved slider attacks a HIGH-value piece with a lesser piece
    # behind it on the same ray (front K/Q/R, behind Q/R/B/N, front > behind).
    if _is_skewer(board, move.to_square, opponent):
        motifs.append("skewer")

    return motifs


def _is_skewer(board: chess.Board, to_sq: int, opponent: bool) -> bool:
    piece = board.piece_at(to_sq)
    if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return False
    for victim_sq in board.attacks(to_sq):
        victim = board.piece_at(victim_sq)
        if victim is None or victim.color != opponent:
            continue
        if victim.piece_type not in (chess.KING, chess.QUEEN, chess.ROOK):
            continue
        front_value = 99 if victim.piece_type == chess.KING else PIECE_VALUES[victim.piece_type]
        step_f = (chess.square_file(victim_sq) > chess.square_file(to_sq)) \
            - (chess.square_file(victim_sq) < chess.square_file(to_sq))
        step_r = (chess.square_rank(victim_sq) > chess.square_rank(to_sq)) \
            - (chess.square_rank(victim_sq) < chess.square_rank(to_sq))
        f = chess.square_file(victim_sq) + step_f
        r = chess.square_rank(victim_sq) + step_r
        while 0 <= f <= 7 and 0 <= r <= 7:
            behind = board.piece_at(chess.square(f, r))
            if behind is not None:
                if (behind.color == opponent
                        and behind.piece_type in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
                        and front_value > PIECE_VALUES[behind.piece_type]):
                    return True
                break
            f += step_f
            r += step_r
    return False


def mate_in_two_defenses(fen_before: str, uci: str) -> list[dict]:
    """If `uci` forces mate in two (EVERY defense allows an immediate mate),
    enumerate each defense with its mating move and pattern. [] when not a forced
    mate-in-two. Lets the FINAL move's annotation honestly say "every defense
    lost" with the pieces credited per branch (Jerry 2026-06-11: Réti m10 has
    Kc7->Bd8# AND Ke8->Rd8#; the engine PV only ever shows one line).
    """
    board = chess.Board(fen_before)
    try:
        move = chess.Move.from_uci(uci)
        if not board.is_legal(move):
            return []
        board.push(move)
    except (ValueError, AssertionError):
        return []
    defenses: list[dict] = []
    for reply in list(board.legal_moves):
        reply_san = board.san(reply)
        after_reply = board.copy()
        after_reply.push(reply)
        mate = None
        for candidate in after_reply.legal_moves:
            probe = after_reply.copy()
            probe.push(candidate)
            if probe.is_checkmate():
                mate = (after_reply.san(candidate),
                        mate_pattern(after_reply.fen(), candidate.uci()))
                break
        if mate is None:
            return []   # a defense survives -> not forced M2
        defenses.append({
            "reply_san": reply_san,
            "mate_san": mate[0],
            "checkers": mate[1].checkers,
            "supporters": mate[1].supporters,
        })
    return defenses


def opponent_castling_rights(fen_before: str, uci: str) -> dict | None:
    """Castling rights of the side to move AFTER `uci` (i.e. the mover's opponent).

    Bounds 'king stuck in the center' claims (Jerry 2026-06-11: the Opera m9 prose
    overclaimed — Black could still castle either side via ...Nbd7/O-O-O or
    ...Qc7/Bd6/O-O). Such claims are only allowed when NO rights remain; otherwise
    the prose must say 'still in the center' / 'behind in development'.
    Returns {"kingside": bool, "queenside": bool} or None if the move is illegal.
    """
    board = chess.Board(fen_before)
    try:
        move = chess.Move.from_uci(uci)
        if not board.is_legal(move):
            return None
        board.push(move)
    except (ValueError, AssertionError):
        return None
    opponent = board.turn
    return {
        "kingside": board.has_kingside_castling_rights(opponent),
        "queenside": board.has_queenside_castling_rights(opponent),
    }


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


# ---- FactSheet: the deterministic fact layer (ANNOTATION_PIPELINE_V2 §3.1) ----------
# Everything verifiable about a move, composed into one structured object plus a fixed
# `fact_line` (EN/ZH) that the LLM never writes. This removes the fact-layer bug classes
# (wrong mate distance, mate-vs-checkmate, unbacked material) by construction: the line is
# the same engine fact 5_validate checks, so it cannot disagree with the engine.

# Eval buckets in centipawns, from the better side's POV. Kept here (the pipeline's source
# of truth for verdict wording); mirrors the spirit of the app's ScoringConfig buckets.
_VERDICT_BANDS = [            # (min_abs_cp, en, zh)
    (600, "winning", "胜势"),
    (300, "much better", "大幅领先"),
    (150, "clearly better", "明显占优"),
    (50,  "slightly better", "略占上风"),
]

def _eval_verdict(cp: int, mover_is_white: bool) -> tuple[str, str]:
    """Verdict clause from the mover-POV centipawn score (EN, ZH)."""
    if abs(cp) <= 50:
        return ("The position is roughly level.", "局面大致均势。")
    better_white = (cp > 0) == mover_is_white
    side_en = "White" if better_white else "Black"
    side_zh = "白方" if better_white else "黑方"
    deg_en = deg_zh = ""
    for floor, en, zh in _VERDICT_BANDS:
        if abs(cp) >= floor:
            deg_en, deg_zh = en, zh
            break
    pawns = abs(cp) / 100.0
    return (f"{side_en} is {deg_en} (+{pawns:.1f}).", f"{side_zh}{deg_zh}(+{pawns:.1f})。")


@dataclass
class FactSheet:
    is_checkmate: bool
    mate_in: int | None          # forced-mate distance for the mover; None if not a mate
    eval_cp: int | None          # mover POV
    mover_is_white: bool
    fact_line_en: str
    fact_line_zh: str


def build_fact_sheet(fen_before: str, uci: str, *, eval_cp: int | None,
                     eval_mate: int | None) -> FactSheet:
    """Compose the deterministic fact layer for one move. The fact_line is fixed text the
    LLM is forbidden to restate; the rationale (LLM) is appended to it downstream.

    Material is intentionally NOT in the line yet: net material from the 3-ply
    refutation_pv is truncated mid-exchange and would mislabel sacrifices/recaptures. The
    eval verdict already carries the advantage; a SEE-based material clause is future work."""
    board = chess.Board(fen_before)
    mover_is_white = board.turn == chess.WHITE
    is_mate = mate_pattern(fen_before, uci).is_mate

    if is_mate:
        en, zh = "Checkmate.", "将杀。"
    elif eval_mate is not None and eval_mate > 0:
        en, zh = f"Forced mate in {eval_mate}.", f"{eval_mate} 步强制将杀。"
    elif eval_cp is not None:
        en, zh = _eval_verdict(eval_cp, mover_is_white)
    else:
        en, zh = "", ""

    return FactSheet(
        is_checkmate=is_mate,
        mate_in=None if is_mate else (eval_mate if (eval_mate or 0) > 0 else None),
        eval_cp=eval_cp,
        mover_is_white=mover_is_white,
        fact_line_en=en,
        fact_line_zh=zh,
    )
