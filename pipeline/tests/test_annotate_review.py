"""Engine-free / API-free tests for stage 4 (annotate) and stage 6 (review) logic.

The Anthropic call in 4_annotate.py is gated on ANTHROPIC_API_KEY and not exercised here;
these cover prompt construction, schema strictness, result application, and HTML rendering.
"""

import annotate
import review
from annotate import (
    AltAnnotation,
    GameIntroResult,
    MoveAnnotationResult,
    apply_move_annotation,
)
from store import GameRecord, MoveRecord

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _move(**kw):
    base = dict(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True,
        legal_evals={
            "e2e4": {"cp": 30, "mate": None, "refutation_pv": ["e7e5"], "motif": "best"},
            "d2d4": {"cp": 20, "mate": None, "refutation_pv": [], "motif": "ok"},
            "g1f3": {"cp": 10, "mate": None, "refutation_pv": [], "motif": "ok"},
            "b1c3": {"cp": -40, "mate": None, "refutation_pv": [], "motif": "inaccuracy"},
        },
    )
    base.update(kw)
    return MoveRecord(**base)


def _game(moves):
    return GameRecord(
        id="g1", white="A. Player", black="B. Player", event="Test", site="S",
        date="2026.06.09", year=2026, result="1-0", eco="C00", hero_color="white",
        title="Sample", narrative_intro="An intro.", pack_id=None, ply_count=len(moves),
        source_hash="h", review_status="pending", moves=moves,
    )


# ------------------------------------------------------------------- structured output

def test_strict_schema_is_strict_and_nested():
    schema = annotate.strict_json_schema(MoveAnnotationResult)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"annotation", "alt_annotations"}
    # nested AltAnnotation object in $defs must also be strict
    alt = schema["$defs"]["AltAnnotation"]
    assert alt["additionalProperties"] is False
    assert set(alt["required"]) == {"uci", "prose"}


def test_pydantic_models_validate():
    parsed = MoveAnnotationResult.model_validate_json(
        '{"annotation": "Central control.", '
        '"alt_annotations": [{"uci": "d2d4", "prose": "Also fine but blocks the bishop."}]}'
    )
    assert parsed.annotation == "Central control."
    assert parsed.alt_annotations[0].uci == "d2d4"
    assert GameIntroResult.model_validate_json('{"narrative_intro": "x"}').narrative_intro == "x"


# ------------------------------------------------------------------- interesting moves

def test_interesting_moves_master_first_then_top_by_cp():
    move = _move(uci="d2d4", san="d4")  # pretend the master move is d4
    picks = annotate.interesting_moves(move, top_n=2)
    assert picks[0] == "d2d4"                  # master always first
    assert picks[1:] == ["e2e4", "g1f3"]       # top engine moves by cp, excluding master
    assert len(picks) == 3


# ------------------------------------------------------------------- prompt building

def test_build_move_prompt_grounded_and_mentions_sans():
    prompt = annotate.build_move_prompt(_game([_move()]), _move())
    assert START_FEN in prompt
    assert "ONLY moves" in prompt
    assert "e4" in prompt and "d4" in prompt          # master + an alternative, in SAN
    assert "master played: e4" in prompt


def test_build_intro_prompt_avoids_spoilers():
    prompt = annotate.build_intro_prompt(_game([_move()]))
    assert "narrative intro" in prompt.lower()
    assert "result" in prompt.lower()                 # instructs not to reveal it


# --------------------------------------------------------------------- apply results

def test_apply_move_annotation_sets_fields():
    move = _move()
    result = MoveAnnotationResult(
        annotation="Grabs the center.",
        alt_annotations=[AltAnnotation(uci="d2d4", prose="Solid alternative.")],
    )
    apply_move_annotation(move, result)
    assert move.annotation == "Grabs the center."
    assert move.alt_annotations == {"d2d4": "Solid alternative."}


# ---------------------------------------------------------------------- review HTML

def test_render_game_html_has_board_and_annotation():
    move = _move(annotation="e4 stakes a claim in the center.",
                 alt_annotations={"d2d4": "Also central, but slower."})
    out = review.render_game_html(_game([move]))
    assert "<svg" in out                              # python-chess board diagram
    assert "e4 stakes a claim" in out                 # annotation text
    assert "Sample" in out                            # game title
    assert "Also central" in out                      # alt annotation
