"""Stage 5b logic — claim-extraction audit (TECH_SPEC §5.2).

Closes the blacklist gap: a separate LLM pass EXTRACTS every claim the prose makes
into a closed taxonomy; deterministic code then verifies each claim against facts.py.
Claims that don't fit any class fail the build (`unclassified_claim`) and force a
taxonomy decision — new claim types become build-time failures, not shipped content.

Importable + unit-tested without a key (same pattern as annotate.py); the actual
Anthropic call lives in 5b_audit.py.
"""

from __future__ import annotations

from typing import Literal

import chess
from pydantic import BaseModel, Field

import facts
from store import MoveRecord
from validate import ValidationError, _normalize_san

AUDIT_MODEL = "claude-fable-5"   # tiny volume (~1 call/guess point); favor accuracy over cost

# The closed taxonomy (TECH_SPEC §5.2). kind: F = fact-backed deterministic check,
# I = interpretive (eval-direction only), B = banned outright.
CLAIM_CLASSES: dict[str, str] = {
    "mate_now":            "F",  # this move delivers mate on the board
    "mate_forced":         "F",  # a forced mate exists after this move (not yet played)
    "mate_by_piece_later": "F",  # a NAMED piece delivers/joins a mate later in the line
    "material":            "F",  # wins/loses/drops pawn|piece|exchange
    "castling_inability":  "F",  # enemy king stuck in center / can no longer castle
    "named_move":          "F",  # a concrete move in algebraic notation
    "tactic_motif":        "F",  # fork / pin / discovered check / skewer
    "eval_verdict":        "I",  # winning / better / equal / losing (direction-checked)
    "positional_color":    "I",  # development, activity, pressure, initiative, plans
    "future_identifying":  "B",  # identifies a still-unguessed master move (piece/square/effect)
}

CLAIM_CLASS_NAMES = tuple(CLAIM_CLASSES)


class ExtractedClaim(BaseModel):
    claim_class: Literal[
        "mate_now", "mate_forced", "mate_by_piece_later", "material",
        "castling_inability", "named_move", "tactic_motif", "eval_verdict",
        "positional_color", "future_identifying", "other",
    ] = Field(description="Taxonomy class; 'other' if no class fits.")
    quote: str = Field(description="Verbatim span of prose making the claim.")
    piece: str | None = Field(
        default=None,
        description="Piece kind the claim is about (pawn/knight/bishop/rook/queen/king), if any.")


class AuditResult(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


AUDIT_SYSTEM_PROMPT = """\
You are a claim extractor for chess-annotation QA. You will be given annotation prose
for one position. List EVERY claim the prose makes, each as one of these classes:

- mate_now: this move delivers checkmate on the spot.
- mate_forced: a forced mate exists after this move (engine verdict, not yet delivered).
- mate_by_piece_later: a SPECIFIC piece kind is said to deliver or support a mate/attack
  later in the line ("the bishop delivers mate next", "the rook guards the file").
- material: winning/losing/dropping a pawn, piece, exchange, or queen.
- castling_inability: the enemy king is stuck in the center / can no longer castle.
- named_move: a concrete move in algebraic notation (e.g. Nf3, O-O-O, Qxd8+).
- tactic_motif: a fork, pin, skewer, or discovered check.
- eval_verdict: who stands better/winning/equal, without concrete means.
- positional_color: development, activity, pressure, initiative, plan talk — no
  concrete checkable fact.
- future_identifying: identifies WHAT happens on a later move the trainee must still
  guess — the piece that will move, its destination, or its concrete effect.
- other: a checkable-sounding claim that fits none of the above.

Extract exhaustively: one prose sentence can yield several claims. Copy the exact
quote. Set `piece` when the claim is about a specific piece kind. Do not judge
whether claims are TRUE — only classify them.\
"""


def build_audit_prompt(move: MoveRecord, upcoming_sans: list[str]) -> str:
    """User message: the prose to audit + the still-to-guess context the extractor
    needs to spot future_identifying claims."""
    parts = [
        f"Master move played here: {move.san}.",
        ("Master moves the trainee must STILL guess after this one: "
         + (", ".join(upcoming_sans) if upcoming_sans else "(none — this is the last)")),
        "",
        f"ANNOTATION PROSE:\n{move.annotation or ''}",
    ]
    for uci, prose in (move.alt_annotations or {}).items():
        parts.append(f"\nALT NOTE ({uci}):\n{prose}")
    return "\n".join(parts)


# ------------------------------------------------------------------ deterministic checks

def _master_line(move: MoveRecord) -> list[str]:
    return (move.legal_evals.get(move.uci) or {}).get("refutation_pv") or []


def _line_end_mate_pattern(move: MoveRecord) -> facts.MatePattern:
    """Mate pattern at the END of the master move's PV (for 'X mates later' claims)."""
    board = chess.Board(move.fen_before)
    try:
        board.push(chess.Move.from_uci(move.uci))
        for raw in _master_line(move):
            board.push(chess.Move.from_uci(raw))
    except (ValueError, AssertionError):
        return facts.MatePattern(is_mate=False)
    if not board.is_checkmate():
        return facts.MatePattern(is_mate=False)
    # Recompute via facts on the last position: rebuild from one move back is complex;
    # reuse mate_pattern by replaying all but the last move.
    moves = [move.uci, *_master_line(move)]
    board = chess.Board(move.fen_before)
    for raw in moves[:-1]:
        board.push(chess.Move.from_uci(raw))
    return facts.mate_pattern(board.fen(), moves[-1])


def check_claims(
    game_id: str,
    move: MoveRecord,
    claims: list[ExtractedClaim],
    upcoming_sans: list[str],
) -> list[ValidationError]:
    """Verify every extracted claim against facts.py. Unknown class -> hard error."""
    errors: list[ValidationError] = []
    master_entry = move.legal_evals.get(move.uci) or {}
    upcoming = {_normalize_san(s) for s in upcoming_sans}

    for claim in claims:
        kind = claim.claim_class
        where = f"claim '{claim.quote[:60]}'"

        if kind == "other":
            errors.append(ValidationError(
                game_id, move.ply, "unclassified_claim",
                f"{where} fits no taxonomy class — extend TECH_SPEC §5.2 or fix the prose"))

        elif kind == "future_identifying":
            if upcoming:
                errors.append(ValidationError(
                    game_id, move.ply, "spoils_future_guess",
                    f"{where} identifies a still-unguessed master move"))

        elif kind == "mate_now":
            pattern = facts.mate_pattern(move.fen_before, move.uci)
            if not pattern.is_mate:
                errors.append(ValidationError(
                    game_id, move.ply, "unsupported_mate_claim",
                    f"{where}: move does not deliver mate"))
            elif claim.piece and claim.piece.lower() not in pattern.participant_kinds:
                errors.append(ValidationError(
                    game_id, move.ply, "wrong_mating_pieces",
                    f"{where}: {claim.piece} does not participate ({pattern.checkers + pattern.supporters})"))

        elif kind == "mate_forced":
            mate = master_entry.get("mate")
            if mate is None or mate <= 0:
                errors.append(ValidationError(
                    game_id, move.ply, "unsupported_mate_claim",
                    f"{where}: engine shows no forced mate for the mover"))

        elif kind == "mate_by_piece_later":
            if upcoming:
                # Naming the piece that mates later IS the spoiler class.
                errors.append(ValidationError(
                    game_id, move.ply, "spoils_future_guess",
                    f"{where} names the piece that acts on a still-unguessed move"))
            else:
                pattern = _line_end_mate_pattern(move)
                if not pattern.is_mate:
                    errors.append(ValidationError(
                        game_id, move.ply, "unsupported_mate_claim",
                        f"{where}: master line does not end in mate"))
                elif claim.piece and claim.piece.lower() not in pattern.participant_kinds:
                    errors.append(ValidationError(
                        game_id, move.ply, "wrong_mating_pieces",
                        f"{where}: {claim.piece} does not participate in the line-end mate"))

        elif kind == "material":
            mat = facts.line_material(move.fen_before, move.uci, _master_line(move))
            if not mat.captures:
                errors.append(ValidationError(
                    game_id, move.ply, "unsupported_material_claim",
                    f"{where}: master line shows no capture"))

        elif kind == "castling_inability":
            rights = facts.opponent_castling_rights(move.fen_before, move.uci)
            if rights is not None and (rights["kingside"] or rights["queenside"]):
                errors.append(ValidationError(
                    game_id, move.ply, "unsupported_stuck_king_claim",
                    f"{where}: opponent still has castling rights ({rights})"))

        elif kind == "named_move":
            token = _normalize_san(claim.quote.strip())
            if token in upcoming:
                errors.append(ValidationError(
                    game_id, move.ply, "spoils_future_guess",
                    f"{where} names a still-unguessed master move"))

        elif kind == "tactic_motif":
            motifs = set(facts.tactical_motifs(move.fen_before, move.uci))
            quote = claim.quote.lower()
            claimed = {m for m in ("fork", "pin", "skewer") if m in quote}
            if "discovered" in quote:
                claimed.add("discovered_check")
            unsupported = claimed - motifs
            if unsupported:
                errors.append(ValidationError(
                    game_id, move.ply, "unsupported_motif_claim",
                    f"{where}: claims {sorted(unsupported)} but computed motifs are {sorted(motifs)}"))

        # eval_verdict / positional_color: interpretive — direction is already covered
        # by validate.py's eval-adjective checks; nothing further here.

    return errors
