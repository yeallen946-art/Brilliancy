"""Tests for facts.py (the deterministic extractor) and the §5.1 validate/annotate wiring.

The Réti position is the real-world regression: the M2 review caught annotations
claiming a "double-bishop mate" when the mate is bishop + ROOK.
"""

import annotate
import facts
import validate
from store import GameRecord, MoveRecord

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
# Réti-Tartakower, position before Bd8# (White to move).
RETI_MATE_FEN = "rnb2b1r/ppk2ppp/2p5/4q1B1/4n3/8/PPP2PPP/2KR1BNR w - - 2 11"


# ------------------------------------------------------------------- mate pattern

def test_mate_pattern_reti_is_bishop_and_rook():
    p = facts.mate_pattern(RETI_MATE_FEN, "g5d8")
    assert p.is_mate
    assert p.checkers == ["bishop@d8"]
    assert p.supporters == ["rook@d1"]          # rook covers d6/d7; f1 bishop plays no part
    assert p.participant_kinds == {"bishop", "rook"}
    assert p.kind_count("bishop") == 1


def test_mate_pattern_non_mate():
    assert facts.mate_pattern(START_FEN, "e2e4").is_mate is False


# ---------------------------------------------------------------- line material

def test_line_material_counts_captures_with_sign():
    # e4 d5 exd5: White wins a pawn (+1 for the mover).
    m = facts.line_material(START_FEN, "e2e4", ["d7d5", "e4d5"])
    assert m.captures == ["pawn@d5"]
    assert m.net_pawns == 1


def test_line_material_no_captures():
    m = facts.line_material(START_FEN, "e2e4", ["e7e5", "g1f3"])
    assert m.captures == [] and m.net_pawns == 0


def test_move_character():
    assert facts.move_character(RETI_MATE_FEN, "g5d8") == ["mate"]
    assert facts.move_character(START_FEN, "e2e4") == []


# ----------------------------------------------------- mate-claim validation (C2)

def _reti_move(annotation):
    return MoveRecord(
        ply=21, san="Bd8#", uci="g5d8", fen_before=RETI_MATE_FEN, mover="white",
        is_guess_point=True, annotation=annotation,
        legal_evals={"g5d8": {"cp": None, "mate": 1, "refutation_pv": [], "motif": "best"}},
    )


def test_double_bishop_claim_rejected():
    # The exact real-world error: only ONE bishop participates.
    move = _reti_move("Bd8#!! completes the double-bishop mate.")
    codes = {e.code for e in validate.validate_move("g", move)}
    assert "wrong_mating_pieces" in codes


def test_bishop_and_rook_claim_accepted():
    move = _reti_move("Bd8#!! — the bishop gives check while the rook cuts off the escape.")
    assert validate.validate_move("g", move) == []


def test_wrong_kind_mate_credit_rejected():
    move = _reti_move("A classic queen mate to finish.")
    codes = {e.code for e in validate.validate_move("g", move)}
    assert "wrong_mating_pieces" in codes


def test_title_checked_against_mate_pattern():
    game = GameRecord(
        id="reti", white="A", black="B", event="E", site="S", date="1910.??.??",
        year=1910, result="1-0", eco="B15", hero_color="white",
        title="Reti's Double-Bishop Mate", narrative_intro=None, pack_id=None,
        ply_count=1, source_hash="h", review_status="approved",
        moves=[_reti_move("Bd8#!! mates.")],
    )
    codes = {e.code for e in validate.validate_game(game)}
    assert "wrong_mating_pieces" in codes
    game.title = "Reti's Bishop-and-Rook Mate"
    assert validate.validate_game(game) == []


# ------------------------------------------------- prompt: identity stripped + facts in

def test_move_prompt_strips_identity_and_includes_mate_facts():
    game = GameRecord(
        id="reti", white="Reti, Richard", black="Tartakower, Savielly", event="Vienna",
        site="Vienna", date="1910.??.??", year=1910, result="1-0", eco="B15",
        hero_color="white", title="T", narrative_intro=None, pack_id=None,
        ply_count=1, source_hash="h", review_status="pending",
        moves=[_reti_move(None)],
    )
    prompt = annotate.build_move_prompt(game, game.moves[0])
    assert "Reti" not in prompt and "Tartakower" not in prompt and "Vienna" not in prompt
    assert "MATE FACTS" in prompt
    assert "bishop@d8" in prompt and "rook@d1" in prompt
