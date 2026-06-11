"""Stage 5 logic — automated annotation validation (TECH_SPEC §5, PRD §6).

Enforces the annotation grounding contract: every move mentioned in prose must be legal
and present in the engine's `legal_evals`; eval adjectives must match the numbers; the
master move may not be claimed "best/winning" if the evals say otherwise (the §3.2 honesty
rule); length limits apply. Importable + unit-tested with known-bad annotations; CLI in
5_validate.py. Uses python-chess to parse SAN against the real position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import chess

import facts
from store import GameRecord, MoveRecord

MAX_ANNOTATION_CHARS = 400
# Reading level for 800-2000 improvers (TECH_SPEC §5, PRD): keep sentences digestible.
MAX_SENTENCE_WORDS = 35

WINNING_WORDS = ("winning", "crushing", "decisive", "completely won", "totally winning")
EQUAL_WORDS = ("equal", "balanced", "level", "roughly equal")
BEST_WORDS = ("the best move", "best move", "only move", "objectively best")
# Material claims must be backed by a capture in the engine line (TECH_SPEC §5 honesty rule).
# Phrases, not bare "drops" (avoids false positives like "drops the advantage").
MATERIAL_WORDS = (
    "drops material", "drops a piece", "drops a pawn", "drops the exchange",
    "loses material", "loses a piece", "loses a pawn", "loses the exchange",
    "wins a pawn", "win a pawn", "wins material", "win material", "wins a piece",
    "wins the exchange", "grabs a pawn", "snaps off a pawn", "and a pawn",
    "extra pawn", "up a pawn", "hangs a",
)

WINNING_THRESHOLD_CP = 200   # "winning" needs >= +2.0 for the mover
EQUAL_BAND_CP = 50           # "equal" needs |eval| <= 0.5

# A SAN-ish token: castling or a destination-square move (must carry file+rank), so plain
# English words don't match. May over/under-match in rare prose; good enough + tested.
SAN_TOKEN_RE = re.compile(
    r"\b(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)\b"
)

# Mate-claim patterns checked against facts.mate_pattern (the "two bishops" class).
# "double-bishop mate", "two rooks", "both knights", "pair of bishops":
DOUBLE_KIND_RE = re.compile(
    r"\b(?:two|both|double|pair of)[\s-]+(pawns?|knights?|bishops?|rooks?|queens?)\b", re.I
)
# "rook mate", "queen mates", "bishop-mate": the credited kind must participate.
MATE_CREDIT_RE = re.compile(
    r"\b(pawn|knight|bishop|rook|queen)[\s-]+mates?\b", re.I
)


@dataclass
class ValidationError:
    game_id: str
    ply: int
    code: str
    message: str


def extract_san_tokens(text: str) -> list[str]:
    return SAN_TOKEN_RE.findall(text or "")


def longest_sentence_words(text: str) -> int:
    """Word count of the longest sentence (rough readability proxy)."""
    sentences = re.split(r"[.!?]+", text or "")
    return max((len(s.split()) for s in sentences), default=0)


def _master_cp(move: MoveRecord) -> int | None:
    entry = move.legal_evals.get(move.uci)
    if entry is not None and entry.get("cp") is not None:
        return entry["cp"]
    return move.eval_cp


def _master_is_mate_for_mover(move: MoveRecord) -> bool:
    entry = move.legal_evals.get(move.uci) or {}
    mate = entry.get("mate")
    return mate is not None and mate > 0


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(p in low for p in phrases)


def _check_mentioned_moves(text: str, fen_before: str, legal_ucis: set,
                           game_id: str, ply: int) -> list[ValidationError]:
    """Every move named in prose must be legal at this position and in engine output."""
    errors: list[ValidationError] = []
    board = chess.Board(fen_before)
    for token in extract_san_tokens(text):
        try:
            parsed = board.parse_san(token)
        except ValueError:
            errors.append(ValidationError(
                game_id, ply, "illegal_move_mentioned",
                f"references illegal move '{token}'"))
            continue
        if legal_ucis and parsed.uci() not in legal_ucis:
            errors.append(ValidationError(
                game_id, ply, "move_outside_engine_output",
                f"move '{token}' is not in legal_evals"))
    return errors


def line_has_capture(fen_before: str, move_uci: str, refutation_pv: list) -> bool:
    """True if move + line contains a capture (backs material claims). Delegates to
    facts.line_material — one extractor, two consumers (TECH_SPEC §5.1)."""
    return bool(facts.line_material(fen_before, move_uci, refutation_pv).captures)


def check_mate_claims(text: str, pattern: facts.MatePattern,
                      game_id: str, ply: int) -> list[ValidationError]:
    """Verify piece-credit claims about a mate against the computed mate pattern
    (the 'double-bishop' class of error). Board-aware, not vibes."""
    errors: list[ValidationError] = []
    if not pattern.is_mate or not text:
        return errors
    for m in DOUBLE_KIND_RE.finditer(text):
        kind = m.group(1).rstrip("s").lower()
        if pattern.kind_count(kind) < 2:
            errors.append(ValidationError(
                game_id, ply, "wrong_mating_pieces",
                f"claims '{m.group(0)}' but only {pattern.kind_count(kind)} {kind}(s) "
                f"participate in the mate ({pattern.checkers + pattern.supporters})"))
    for m in MATE_CREDIT_RE.finditer(text):
        kind = m.group(1).lower()
        if kind not in pattern.participant_kinds:
            errors.append(ValidationError(
                game_id, ply, "wrong_mating_pieces",
                f"credits the {kind} with the mate, but participants are "
                f"{pattern.checkers + pattern.supporters}"))
    return errors


def _normalize_san(san: str) -> str:
    return san.rstrip("+#")


def check_future_guess_spoilers(text: str, upcoming_sans: list[str],
                                game_id: str, ply: int, where: str) -> list[ValidationError]:
    """Prose at one guess point must not NAME a master move the trainee still has to
    guess (Jerry 2026-06-11). Deterministic half of the spoiler guard: literal SAN
    mentions. Semantic spoilers ('the rook mates next') are the annotate-prompt's and
    the human reviewer's job — strings can't judge those."""
    if not text or not upcoming_sans:
        return []
    upcoming = {_normalize_san(s) for s in upcoming_sans}
    return [
        ValidationError(
            game_id, ply, "spoils_future_guess",
            f"{where} names '{token}', a master move the trainee still has to guess")
        for token in extract_san_tokens(text)
        if _normalize_san(token) in upcoming
    ]


def validate_move(game_id: str, move: MoveRecord,
                  upcoming_sans: list[str] | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    text = move.annotation
    if not text:
        return errors

    # 1) length + reading level
    if len(text) > MAX_ANNOTATION_CHARS:
        errors.append(ValidationError(
            game_id, move.ply, "too_long",
            f"annotation {len(text)} chars > {MAX_ANNOTATION_CHARS}",
        ))
    longest = longest_sentence_words(text)
    if longest > MAX_SENTENCE_WORDS:
        errors.append(ValidationError(
            game_id, move.ply, "hard_to_read",
            f"longest sentence is {longest} words > {MAX_SENTENCE_WORDS}",
        ))

    # 2) every mentioned move is legal AND in engine output (legal_evals)
    legal_ucis = set(move.legal_evals.keys())
    errors.extend(_check_mentioned_moves(text, move.fen_before, legal_ucis, game_id, move.ply))

    # 3) eval adjectives must match numbers; honesty rule for "best/winning"
    cp = _master_cp(move)
    is_mate = _master_is_mate_for_mover(move)
    if _contains_any(text, WINNING_WORDS) and not is_mate:
        if cp is None or cp < WINNING_THRESHOLD_CP:
            errors.append(ValidationError(
                game_id, move.ply, "eval_adjective_mismatch",
                f"'winning' claim but eval is {cp}cp (< {WINNING_THRESHOLD_CP})",
            ))
    if _contains_any(text, EQUAL_WORDS):
        if cp is None or abs(cp) > EQUAL_BAND_CP:
            errors.append(ValidationError(
                game_id, move.ply, "eval_adjective_mismatch",
                f"'equal' claim but eval is {cp}cp",
            ))
    if _contains_any(text, BEST_WORDS) and not is_mate:
        best = max((e["cp"] for e in move.legal_evals.values() if e.get("cp") is not None), default=None)
        if best is not None and cp is not None and best - cp > 10:
            errors.append(ValidationError(
                game_id, move.ply, "false_best_claim",
                f"claims 'best' but master move is {best - cp}cp below the engine best",
            ))

    # 4) mate piece-credit claims, checked against the computed mate pattern (§5.1).
    pattern = facts.mate_pattern(move.fen_before, move.uci)
    errors.extend(check_mate_claims(text, pattern, game_id, move.ply))

    # 4b) spoiler guard: must not name a master move the trainee still has to guess.
    errors.extend(check_future_guess_spoilers(
        text, upcoming_sans or [], game_id, move.ply, "annotation"))

    # 5) alternative-move notes: same move-mention rule, plus material claims must be
    #    backed by a capture in THAT move's refutation line (TECH_SPEC §5 honesty rule).
    for alt_uci, prose in (move.alt_annotations or {}).items():
        if not prose:
            continue
        errors.extend(_check_mentioned_moves(prose, move.fen_before, legal_ucis, game_id, move.ply))
        errors.extend(check_future_guess_spoilers(
            prose, upcoming_sans or [], game_id, move.ply, f"alt note for '{alt_uci}'"))
        if _contains_any(prose, MATERIAL_WORDS):
            refutation = (move.legal_evals.get(alt_uci) or {}).get("refutation_pv", [])
            if not line_has_capture(move.fen_before, alt_uci, refutation):
                errors.append(ValidationError(
                    game_id, move.ply, "unsupported_material_claim",
                    f"alt note for '{alt_uci}' claims material change, but its line has no capture",
                ))

    return errors


def _move_san(move: MoveRecord) -> str:
    try:
        return chess.Board(move.fen_before).san(chess.Move.from_uci(move.uci))
    except (ValueError, AssertionError):
        return move.san or move.uci


def validate_game(game: GameRecord) -> list[ValidationError]:
    errors: list[ValidationError] = []
    final_mate: tuple[int, facts.MatePattern] | None = None
    guess_points = [m for m in game.moves if m.is_guess_point]
    for move in game.moves:
        if move.is_guess_point:
            upcoming = [_move_san(m) for m in guess_points if m.ply > move.ply]
            errors.extend(validate_move(game.id, move, upcoming_sans=upcoming))
            pattern = facts.mate_pattern(move.fen_before, move.uci)
            if pattern.is_mate:
                final_mate = (move.ply, pattern)
    # The game TITLE often describes the finish ("...Mate") — hold it to the same
    # mate-pattern truth (the original C2 error was in the title).
    if game.title and final_mate:
        ply, pattern = final_mate
        errors.extend(check_mate_claims(game.title, pattern, game.id, ply))
    return errors
