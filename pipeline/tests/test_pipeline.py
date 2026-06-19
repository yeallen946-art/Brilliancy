"""Engine-free tests for the M2 pipeline backbone (ingest/curate/guesspoints/validate/build).

No Stockfish or API key needed — the engine/LLM stages are exercised elsewhere with their
boundaries. Run from pipeline/: pytest
"""

import json
import os

import analysis
import build
import curate
import guesspoints
import ingest
import store
from store import GameRecord, MoveRecord

SAMPLE_PGN = """[Event "Test"]
[Site "?"]
[Date "1956.10.17"]
[White "Byrne, Donald"]
[Black "Fischer, Robert James"]
[Result "0-1"]
[ECO "D92"]

1. Nf3 Nf6 2. c4 g6 3. Nc3 Bg7 4. d4 O-O 5. Bf4 d5 6. Qb3 dxc4 7. Qxc4 c6
8. e4 Nbd7 9. Rd1 Nb6 10. Qc5 Bg4 11. Bg5 Na4 12. Qa3 Nxc3 13. bxc3 Nxe4
14. Bxe7 Qb6 15. Bc4 Nxc3 16. Bc5 Rfe8+ 17. Kf1 Be6 18. Bxb6 Bxc4+ 19. Kg1 Ne2+
20. Kf1 Nxd4+ 21. Kg1 Ne2+ 22. Kf1 Nc3+ 23. Kg1 axb6 24. Qb4 Ra4 25. Qxb6 Nxd1
26. h3 Rxa2 27. Kh2 Nxf2 28. Re1 Rxe1 29. Qd8+ Bf8 30. Nxe1 Bd5 31. Nf3 Ne4
32. Qb8 b5 33. h4 h5 34. Ne5 Kg7 35. Kg1 Bc5+ 36. Kf1 Ng3+ 37. Ke1 Bb4+
38. Kd1 Bb3+ 39. Kc1 Ne2+ 40. Kb1 Nc3+ 41. Kc1 Rc2# 0-1
"""

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# --------------------------------------------------------------------- ingest

def test_ingest_parses_game():
    games = ingest.parse_pgn_text(SAMPLE_PGN)
    assert len(games) == 1
    g = games[0]
    assert g.ply_count == 82
    assert g.hero_color == "black"            # 0-1 -> Black is the hero
    assert g.moves[0].san == "Nf3"
    assert g.moves[0].fen_before == START_FEN
    assert g.moves[0].mover == "white"
    assert "fischer" in g.id


def test_ingest_dedupe_hash_stable():
    a = ingest.parse_pgn_text(SAMPLE_PGN)[0]
    b = ingest.parse_pgn_text(SAMPLE_PGN)[0]
    assert a.source_hash == b.source_hash


# ----------------------------------------------------------------- guesspoints

def _mv(ply, san, uci, mover):
    return MoveRecord(ply=ply, san=san, uci=uci, fen_before="", mover=mover)


def test_candidate_guess_plies_only_hero_after_book_capped():
    game = ingest.parse_pgn_text(SAMPLE_PGN)[0]
    plies = guesspoints.candidate_guess_plies(game)
    assert plies, "expected some guess points"
    assert all(p % 2 == 0 for p in plies), "hero is Black -> even plies only"
    assert all(p > guesspoints.BOOK_PLIES for p in plies), "book moves skipped"
    assert len(plies) <= guesspoints.TARGET_MAX_POINTS


def test_forced_recapture_detected():
    moves = [
        _mv(1, "exd5", "e4d5", "white"),
        _mv(2, "Nxd5", "c3d5", "black"),   # recapture on d5
        _mv(3, "Nf3", "g1f3", "white"),    # not a recapture
    ]
    assert guesspoints.is_forced_recapture(moves, 1) is True
    assert guesspoints.is_forced_recapture(moves, 2) is False
    assert guesspoints.is_forced_recapture(moves, 0) is False


def test_difficulty_inverse_to_obviousness():
    obvious = {"a": {"cp": 300}, "b": {"cp": -50}}   # big gap -> easy -> lower rating
    murky = {"a": {"cp": 20}, "b": {"cp": 10}}       # small gap -> hard -> higher rating
    assert guesspoints.difficulty_from_evals(obvious) < guesspoints.difficulty_from_evals(murky)


def test_motif_grading():
    assert analysis.motif(cp=0, mate=None, best_cp=0) == "best"
    assert analysis.motif(cp=-60, mate=None, best_cp=0) == "ok"
    assert analysis.motif(cp=-500, mate=None, best_cp=0) == "blunder"
    assert analysis.motif(cp=None, mate=2, best_cp=0) == "best"


def test_best_entry_mate_beats_best_cp():
    # Bug B: a mating move must not be shadowed by the best non-mate cp.
    le = {"a": {"cp": -571, "mate": None}, "b": {"cp": None, "mate": 1}}
    assert analysis.best_entry(le)["mate"] == 1
    le2 = {"a": {"cp": 300, "mate": None}, "b": {"cp": 50, "mate": None}}
    assert analysis.best_entry(le2)["cp"] == 300
    assert analysis.best_entry({}) is None


# ------------------------------------------------------------------- validate

def _guess_move(annotation, legal_evals, master_uci="e2e4"):
    return MoveRecord(
        ply=20, san="e4", uci=master_uci, fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation=annotation, legal_evals=legal_evals,
    )


def test_validate_clean_annotation_passes():
    from validate import validate_move
    move = _guess_move(
        "e4 grabs the center while Nf3 develops a piece.",
        {"e2e4": {"cp": 30}, "g1f3": {"cp": 25}},
    )
    assert validate_move("g", move) == []


def test_validate_flags_illegal_move_mention():
    from validate import validate_move
    move = _guess_move("Qh5 immediately decides.", {"e2e4": {"cp": 30}})
    codes = {e.code for e in validate_move("g", move)}
    assert "illegal_move_mentioned" in codes


def test_validate_flags_move_outside_engine_output():
    from validate import validate_move
    move = _guess_move("a4 is the quiet point.", {"e2e4": {"cp": 30}})  # a4 legal, not in evals
    codes = {e.code for e in validate_move("g", move)}
    assert "move_outside_engine_output" in codes


def test_validate_flags_false_winning_claim():
    from validate import validate_move
    move = _guess_move("White is completely winning here.", {"e2e4": {"cp": 30}})
    codes = {e.code for e in validate_move("g", move)}
    assert "eval_adjective_mismatch" in codes


# Regression: Réti move-10 (engine #2) shipped as "forced mate next move" (=#1),
# off-by-one against move-9's "mate in three" (Jerry 2026-06-17).
RETI_M10_FEN = "rnbk1b1r/pp3ppp/2p5/4q3/4n3/8/PPPB1PPP/2KR1BNR w - - 0 10"


def _mate_move(annotation, mate_n, annotation_zh=None):
    return MoveRecord(
        ply=19, san="Bg5+", uci="d2g5", fen_before=RETI_M10_FEN, mover="white",
        is_guess_point=True, annotation=annotation, annotation_zh=annotation_zh,
        legal_evals={"d2g5": {"cp": None, "mate": mate_n, "refutation_pv": ["d8c7"]}},
    )


def test_validate_flags_wrong_mate_distance():
    from validate import validate_move
    move = _mate_move("Bg5+ is the point: the engine shows forced mate next move.", 2)
    codes = {e.code for e in validate_move("g", move)}
    assert "mate_distance_mismatch" in codes


def test_validate_flags_wrong_mate_distance_zh():
    from validate import validate_move
    move = _mate_move("Bg5+", 2, annotation_zh="Bg5+ 是弃后的全部意义:引擎显示下一步即强制将杀。")
    codes = {e.code for e in validate_move("g", move)}
    assert "mate_distance_mismatch" in codes


def test_validate_accepts_correct_mate_distance():
    from validate import validate_move
    move = _mate_move(
        "Bg5+ is the point of the sacrifice: the engine shows forced mate in two.", 2,
        annotation_zh="Bg5+ 是弃后的全部意义:引擎显示两步内强制将杀。",
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "mate_distance_mismatch" not in codes


# A move that ITSELF delivers checkmate must say "checkmate", not "mate in 1"
# (Jerry 2026-06-18: Opera Rd8# = move 17 read as "mate in 1").
OPERA_MATE_FEN = "1n2kb1r/p4ppp/4q3/4p1B1/4P3/8/PPP2PPP/2KR4 w k - 0 17"


def _mating_move(annotation):
    return MoveRecord(
        ply=33, san="Rd8#", uci="d1d8", fen_before=OPERA_MATE_FEN, mover="white",
        is_guess_point=True, annotation=annotation,
        legal_evals={"d1d8": {"cp": None, "mate": 1}},
    )


def test_validate_flags_mate_in_one_on_mating_move():
    from validate import validate_move
    move = _mating_move("The rook crashes onto the back rank — it's mate in 1.")
    codes = {e.code for e in validate_move("g", move)}
    assert "mate_distance_mismatch" in codes


def test_validate_accepts_checkmate_wording_on_mating_move():
    from validate import validate_move
    move = _mating_move("The rook delivers checkmate on the back rank; the king is trapped.")
    codes = {e.code for e in validate_move("g", move)}
    assert "mate_distance_mismatch" not in codes


def test_move_prompt_says_checkmate_not_distance_on_mating_move():
    from annotate import build_move_prompt
    move = _mating_move("x")
    game = _approved_game()
    game.moves = [move]
    prompt = build_move_prompt(game, move)
    assert "DELIVERS CHECKMATE" in prompt
    assert "FORCED MATE IN" not in prompt   # no distance framing for the mating move


def test_move_prompt_states_exact_mate_distance():
    from annotate import build_move_prompt
    move = _mate_move("x", 2)
    game = _approved_game()
    game.moves = [move]
    prompt = build_move_prompt(game, move)
    assert "FORCED MATE IN 2" in prompt
    # Alternatives that aren't themselves mates must be framed as throwing the mate away
    # (Jerry 2026-06-17: Opera m16 Qb7 read as "keeps a winning position").
    assert "THROWS THE MATE AWAY" in prompt


# Opera move-16 (Qb8+): "the quieter queen moves keep a big advantage" while 12 of 15
# queen moves were blunders (Jerry 2026-06-17).
OPERA_M16_FEN = "4kb1r/p2n1ppp/4q3/4p1B1/4P3/1Q6/PPP2PPP/2KR4 w k - 0 16"


def _queen_class_move(annotation, queen_evals):
    legal = {"b3b8": {"cp": None, "mate": 2}}   # master Qb8+ (forced mate)
    legal.update(queen_evals)
    return MoveRecord(
        ply=31, san="Qb8+", uci="b3b8", fen_before=OPERA_M16_FEN, mover="white",
        is_guess_point=True, annotation=annotation, legal_evals=legal,
    )


def test_validate_flags_overgeneralized_class_claim():
    from validate import validate_move
    # Only b3b7/b3c3/b3b5 stay >= 0; the rest throw the advantage away.
    move = _queen_class_move(
        "The master's move is the point. The quieter queen moves keep a big advantage.",
        {"b3b7": {"cp": 314}, "b3c3": {"cp": 306}, "b3b5": {"cp": 27},
         "b3a4": {"cp": -23}, "b3e6": {"cp": -116}, "b3d3": {"cp": -125}, "b3f3": {"cp": -223}},
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "overgeneralized_class_claim" in codes


def test_validate_accepts_class_claim_when_true():
    from validate import validate_move
    # Here most queen moves really do keep a big advantage -> no false positive.
    move = _queen_class_move(
        "The other queen moves keep a big advantage but lose the forced finish.",
        {"b3b7": {"cp": 314}, "b3c3": {"cp": 306}, "b3d3": {"cp": 150},
         "b3e6": {"cp": 120}, "b3a4": {"cp": -50}},
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "overgeneralized_class_claim" not in codes


def test_system_prompt_forbids_class_generalization():
    from annotate import system_prompt
    assert "generalize about a CATEGORY" in system_prompt("en")
    assert "笼统下结论" in system_prompt("zh")


def test_openrouter_request_body_is_strict_json_schema():
    from annotate import MoveAnnotationResult, openrouter_request_body
    body = openrouter_request_body("anthropic/claude-opus-4-8", "SYS", "USER",
                                   MoveAnnotationResult, max_tokens=1024)
    assert body["model"] == "anthropic/claude-opus-4-8"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["messages"][1] == {"role": "user", "content": "USER"}
    assert body["temperature"] <= 0.3   # grounded narration, kept tight to the rules
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    # strict schema: objects closed to extra keys (mirrors the Anthropic path).
    assert fmt["json_schema"]["schema"]["additionalProperties"] is False


def test_load_dotenv_parses_and_does_not_override_env(tmp_path, monkeypatch):
    from annotate import load_dotenv
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "OPENROUTER_API_KEY=sk-or-test\n"
        'export OPENROUTER_MODEL="anthropic/claude-opus-4-8"\n'
        "\n"
        "ALREADY_SET=from_file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.setenv("ALREADY_SET", "from_env")   # real env must win
    parsed = load_dotenv(str(env))
    assert parsed["OPENROUTER_API_KEY"] == "sk-or-test"
    assert parsed["OPENROUTER_MODEL"] == "anthropic/claude-opus-4-8"   # quotes stripped
    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-test"
    assert os.environ["ALREADY_SET"] == "from_env"                    # not overridden


def test_load_dotenv_missing_file_is_empty():
    from annotate import load_dotenv
    assert load_dotenv("/no/such/.env") == {}


def test_line_has_capture():
    from validate import line_has_capture
    # e4 e5 Nf3 — no capture
    assert line_has_capture(START_FEN, "e2e4", ["e7e5", "g1f3"]) is False
    # e4 d5 exd5 — capture
    assert line_has_capture(START_FEN, "e2e4", ["d7d5", "e4d5"]) is True


def test_validate_alt_material_claim_must_be_backed():
    from validate import validate_move
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation="e4 grabs the center.",
        legal_evals={"e2e4": {"cp": 30},
                     "d2d4": {"cp": 10, "refutation_pv": ["g8f6", "b1c3"]}},  # no capture
        alt_annotations={"d2d4": "This drops a piece."},
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "unsupported_material_claim" in codes


def test_validate_alt_illegal_move_mention():
    from validate import validate_move
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation="e4 is central.",
        legal_evals={"e2e4": {"cp": 30}, "d2d4": {"cp": 10}},
        alt_annotations={"d2d4": "Allows Qh4 immediately."},  # Qh4 illegal at start
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "illegal_move_mentioned" in codes


def _two_point_game(first_annotation: str, alt_annotations: dict | None = None):
    """Two guess points; the second master move is d4 (so 'd4' is a spoiler at the first)."""
    first = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, difficulty=1300.0, tags=["tactical"],
        eval_cp=30, legal_evals={"e2e4": {"cp": 30, "motif": "best"},
                                 "d2d4": {"cp": 20, "motif": "ok"}},
        annotation=first_annotation, alt_annotations=alt_annotations or {},
    )
    second = MoveRecord(
        ply=22, san="d4", uci="d2d4", fen_before=START_FEN, mover="white",
        is_guess_point=True, difficulty=1300.0, tags=["positional"],
        eval_cp=20, legal_evals={"d2d4": {"cp": 20, "motif": "best"}},
        annotation="A fine follow-up.", alt_annotations={},
    )
    return GameRecord(
        id="spoiler-game", white="A", black="B", event="E", site="S", date="2026.06.11",
        year=2026, result="1-0", eco="C00", hero_color="white", title="T",
        narrative_intro="N", pack_id="p1", ply_count=2,
        source_hash="hash", review_status=store.REVIEW_APPROVED, moves=[first, second],
    )


def test_validate_flags_annotation_spoiling_future_guess():
    from validate import validate_game
    game = _two_point_game("e4 is strong, and d4 comes next to seal it.")
    codes = {e.code for e in validate_game(game)}
    assert "spoils_future_guess" in codes
    # The final guess point's own prose may of course discuss d4.
    clean = _two_point_game("e4 stakes the center with a lasting initiative.")
    assert "spoils_future_guess" not in {e.code for e in validate_game(clean)}


def test_validate_flags_alt_note_spoilers_too():
    from validate import validate_game
    game = _two_point_game(
        "e4 stakes the center.",
        alt_annotations={"d2d4": "Premature; d4 works far better one move later."})
    codes = {e.code for e in validate_game(game)}
    assert "spoils_future_guess" in codes


def test_validate_move_without_upcoming_keeps_old_behavior():
    from validate import validate_move
    game = _two_point_game("e4 is strong, and d4 comes next to seal it.")
    # Direct validate_move call (no upcoming list) must not invent spoiler errors.
    assert "spoils_future_guess" not in {e.code for e in validate_move("g", game.moves[0])}


def test_move_prompt_carries_spoiler_guard():
    from annotate import build_move_prompt
    game = _two_point_game("placeholder")
    first_prompt = build_move_prompt(game, game.moves[0])
    assert "SPOILER GUARD" in first_prompt
    assert "d4" in first_prompt.split("SPOILER GUARD")[1][:200]
    # The last guess point has nothing left to spoil.
    last_prompt = build_move_prompt(game, game.moves[1])
    assert "SPOILER GUARD" not in last_prompt


def test_move_prompt_drops_alternatives_colliding_with_future_answers():
    from annotate import build_move_prompt
    game = _two_point_game("placeholder")
    # d2d4 is an engine candidate at the FIRST point, but d4 is the SECOND point's
    # master move — the prompt must not ask for prose about it ("Rd1 leak" class).
    first_prompt = build_move_prompt(game, game.moves[0])
    alt_request = first_prompt.split("Write `alt_annotations`")[1]
    assert "d4" not in alt_request.split("\n")[0]
    # And it disappears from the candidate table too (only the master row remains).
    table = first_prompt.split("Engine evaluations")[1].split("SPOILER GUARD")[0]
    assert "d4" not in table


def test_mate_in_two_defenses_enumerates_both_reti_branches():
    import facts
    # Réti m10: 10.Bg5+ forces mate in two with TWO defenses (the engine PV only
    # ever showed Kc7 -> Bd8#; Ke8 -> Rd8# is just as forced).
    fen = "rnbk1b1r/pp3ppp/2p5/4q3/4n3/8/PPPB1PPP/2KR1BNR w - - 0 10"
    branches = facts.mate_in_two_defenses(fen, "d2g5")
    by_reply = {b["reply_san"]: b["mate_san"] for b in branches}
    assert by_reply == {"Kc7": "Bd8#", "Ke8": "Rd8#"}
    # Non-mating move -> [] (a defense survives).
    assert facts.mate_in_two_defenses(START_FEN, "e2e4") == []


def test_final_mate_prompt_carries_branch_facts():
    from annotate import build_move_prompt
    m10 = MoveRecord(
        ply=19, san="Bg5+", uci="d2g5",
        fen_before="rnbk1b1r/pp3ppp/2p5/4q3/4n3/8/PPPB1PPP/2KR1BNR w - - 0 10",
        mover="white", is_guess_point=True, annotation="x",
        legal_evals={"d2g5": {"cp": None, "mate": 2, "refutation_pv": ["d8c7", "g5d8"]}},
    )
    m10_reply = MoveRecord(
        ply=20, san="Kc7", uci="d8c7",
        fen_before="rnbk1b1r/pp3ppp/2p5/4q1B1/4n3/8/PPP2PPP/2KR1BNR b - - 1 10",
        mover="black", is_guess_point=False,
    )
    m11 = MoveRecord(
        ply=21, san="Bd8#", uci="g5d8",
        fen_before="rnb2b1r/ppk2ppp/2p5/4q1B1/4n3/8/PPP2PPP/2KR1BNR w - - 2 11",
        mover="white", is_guess_point=True, annotation="x",
        legal_evals={"g5d8": {"cp": None, "mate": 1, "refutation_pv": []}},
    )
    game = _approved_game()
    game.moves = [m10, m10_reply, m11]

    final_prompt = build_move_prompt(game, m11)
    assert "BRANCH FACTS" in final_prompt
    assert "Kc7 -> Bd8#" in final_prompt and "Ke8 -> Rd8#" in final_prompt
    # The EARLIER ply must NOT carry branch facts (it would spoil the final move).
    assert "BRANCH FACTS" not in build_move_prompt(game, m10)


def test_skewer_motif_detection():
    import facts
    # Bishop to a3 hits Qe7 with Rf8 behind on the same diagonal -> skewer.
    fen = "5r1k/4q3/8/8/8/8/1B6/6K1 w - - 0 1"
    assert "skewer" in facts.tactical_motifs(fen, "b2a3")
    # Same geometry but ROOK in front (5) and QUEEN behind (9): front not more
    # valuable -> NOT a skewer (that's closer to a pin shape).
    fen2 = "5q1k/4r3/8/8/8/8/1B6/6K1 w - - 0 1"
    assert "skewer" not in facts.tactical_motifs(fen2, "b2a3")
    # King in front counts as maximal value: Ra8+ skewers the queen behind the king.
    fen3 = "1kq5/8/8/8/8/8/8/R5K1 w - - 0 1"
    assert "skewer" in facts.tactical_motifs(fen3, "a1a8")


def test_opponent_castling_rights_fact():
    import facts
    # After 1.e4 Black retains both rights.
    rights = facts.opponent_castling_rights(START_FEN, "e2e4")
    assert rights == {"kingside": True, "queenside": True}
    # No rights in the FEN -> both False.
    bare = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1"
    assert facts.opponent_castling_rights(bare, "e2e4") == {"kingside": False, "queenside": False}
    assert facts.opponent_castling_rights(START_FEN, "e2e5") is None  # illegal


def test_validate_flags_unbacked_stuck_king_claim():
    from validate import validate_move
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation="e4 keeps the enemy king stuck in the center.",
        legal_evals={"e2e4": {"cp": 30}},
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "unsupported_stuck_king_claim" in codes
    # Same claim with rights actually gone -> allowed.
    no_rights = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQ - 0 1"  # black has none
    move_ok = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=no_rights, mover="white",
        is_guess_point=True, annotation="e4 keeps the enemy king stuck in the center.",
        legal_evals={"e2e4": {"cp": 30}},
    )
    assert "unsupported_stuck_king_claim" not in {e.code for e in validate_move("g", move_ok)}


def test_move_prompt_carries_castling_fact():
    from annotate import build_move_prompt
    game = _two_point_game("placeholder")
    prompt = build_move_prompt(game, game.moves[0])
    assert "CASTLING:" in prompt
    assert "kingside and queenside" in prompt


# ----------------------------------------------------------------------- packs (S6)

def test_build_packs_table_and_pack_assignment(tmp_path):
    import sqlite3
    game = _approved_game()
    game.pack_id = "immortal-classics"
    packs = [{"id": "immortal-classics", "name": "Immortal Classics", "kind": "theme",
              "description": "d", "price_tier": "premium", "sort_order": 0}]
    db = os.path.join(tmp_path, "c.sqlite")
    build.build_sqlite([game], db, packs=packs)
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT id, name, kind, price_tier FROM packs").fetchone()
        assert row == ("immortal-classics", "Immortal Classics", "theme", "premium")
        pack_id, = conn.execute("SELECT pack_id FROM games").fetchone()
        assert pack_id == "immortal-classics"
    finally:
        conn.close()


def test_load_packs_missing_file_is_empty(tmp_path):
    assert store.load_packs(os.path.join(tmp_path, "nope.json")) == []


# ----------------------------------------------------------- zh narration (PRD 12.1)

def test_zh_prompt_carries_terminology_and_language_directive():
    from annotate import build_move_prompt, system_prompt
    game = _two_point_game("placeholder")
    prompt = build_move_prompt(game, game.moves[0], lang="zh")
    assert "用中文写" in prompt
    assert "牵制" in prompt and "双吃" in prompt          # motif table from facts.py
    assert "Position (FEN)" in prompt                      # same engine data, same facts
    assert "SPOILER GUARD" in prompt                       # spoiler rules apply to zh too
    assert "你是一名国际象棋教练" in system_prompt("zh")
    assert "chess coach" in system_prompt("en")


def test_apply_move_annotation_routes_by_lang():
    from annotate import AltAnnotation, MoveAnnotationResult, apply_move_annotation
    move = _gp_move(20, evals={"e2e4": {"cp": 30}})
    result = MoveAnnotationResult(
        annotation="中心兵推进,白方主动。",
        alt_annotations=[AltAnnotation(uci="d2d4", prose="同样占中,但稍缓。")])
    apply_move_annotation(move, result, lang="zh")
    assert move.annotation_zh == "中心兵推进,白方主动。"
    assert move.alt_annotations_zh == {"d2d4": "同样占中,但稍缓。"}
    assert move.annotation == "x"                          # en untouched


def test_validate_checks_zh_prose_with_zh_wordlists():
    from validate import validate_move
    # zh stuck-king claim while rights remain -> flagged.
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation="e4 is fine.",
        annotation_zh="e4 之后黑王被困在中路,无法易位。",
        legal_evals={"e2e4": {"cp": 30}},
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "unsupported_stuck_king_claim" in codes
    # zh material claim in an alt note without a capture in that line -> flagged.
    move2 = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation="e4 is fine.",
        legal_evals={"e2e4": {"cp": 30}, "d2d4": {"cp": 10, "refutation_pv": []}},
        alt_annotations_zh={"d2d4": "这步丢兵,不可取。"},
    )
    codes2 = {e.code for e in validate_move("g", move2)}
    assert "unsupported_material_claim" in codes2


def test_validate_zh_mate_credit_and_san_in_cjk_text():
    from validate import extract_san_tokens, validate_move
    # SAN glued to CJK must still be extracted (lookaround tokenizer).
    assert "Bg5+" in extract_san_tokens("走Bg5+之后局面立刻崩溃")
    # zh mate credit must match the computed pattern: fool's mate is QUEEN mate.
    fools = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
    move = MoveRecord(
        ply=4, san="Qh4#", uci="d8h4", fen_before=fools, mover="black",
        is_guess_point=True, annotation="Mate.",
        annotation_zh="车将杀,干净利落。",     # WRONG piece: it's the queen
        legal_evals={"d8h4": {"cp": None, "mate": 1}},
    )
    codes = {e.code for e in validate_move("g", move)}
    assert "wrong_mating_pieces" in codes


def test_build_carries_zh_fields():
    game = _approved_game()
    game.title_zh = "测试对局"
    game.narrative_intro_zh = "一段中文引言。"
    game.moves[0].annotation_zh = "e4 占据中心。"
    game.moves[0].alt_annotations_zh = {"d2d4": "稍缓。"}
    payload = build.daily_payload(game, "2026-06-12")
    assert payload["game"]["title_zh"] == "测试对局"
    assert payload["game"]["moves"][0]["annotation_zh"] == "e4 占据中心。"

    import sqlite3, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "c.sqlite")
        build.build_sqlite([game], db)
        conn = sqlite3.connect(db)
        try:
            zh, alts = conn.execute(
                "SELECT annotation_zh, alt_annotations_zh FROM moves").fetchone()
            assert zh == "e4 占据中心。"
            assert json.loads(alts) == {"d2d4": "稍缓。"}
            title_zh, = conn.execute("SELECT title_zh FROM games").fetchone()
            assert title_zh == "测试对局"
        finally:
            conn.close()


def test_store_roundtrip_preserves_zh_and_tolerates_old_files():
    game = _approved_game()
    game.title_zh = "测试"
    game.moves[0].annotation_zh = "中文讲解。"
    data = store.game_to_dict(game)
    loaded = store.game_from_dict(data)
    assert loaded.title_zh == "测试"
    assert loaded.moves[0].annotation_zh == "中文讲解。"
    # Old work-store files (no zh keys) load with defaults.
    del data["title_zh"], data["narrative_intro_zh"]
    for m in data["moves"]:
        del m["annotation_zh"], m["alt_annotations_zh"]
    legacy = store.game_from_dict(data)
    assert legacy.title_zh is None
    assert legacy.moves[0].alt_annotations_zh == {}


# ------------------------------------------------- guess-point refinement (school 2)

def _gp_move(ply, uci="e2e4", san="e4", evals=None, gp=True):
    return MoveRecord(
        ply=ply, san=san, uci=uci, fen_before=START_FEN, mover="white",
        is_guess_point=gp, annotation="x", legal_evals=evals or {},
    )


def test_is_obvious_point_rules():
    from guesspoints import is_obvious_point
    # Big CP gap -> obvious (the Opera Rd1 case).
    assert is_obvious_point(_gp_move(20, evals={"e2e4": {"cp": 250}, "d2d4": {"cp": -10}}))
    # Small gap -> a real decision, keep.
    assert not is_obvious_point(_gp_move(20, evals={"e2e4": {"cp": 250}, "d2d4": {"cp": 180}}))
    # Mating master move -> NEVER pruned, that's the drama.
    assert not is_obvious_point(_gp_move(20, evals={"e2e4": {"cp": None, "mate": 2}, "d2d4": {"cp": 90}}))
    # No engine data / single candidate -> keep (can't judge).
    assert not is_obvious_point(_gp_move(20, evals={"e2e4": {"cp": 50}}))


def test_apply_refinement_prunes_and_overrides():
    from guesspoints import apply_refinement
    game = _approved_game()
    game.moves = [
        _gp_move(20, evals={"e2e4": {"cp": 250}, "d2d4": {"cp": -10}}),   # obvious -> drop
        _gp_move(22, evals={"e2e4": {"cp": 100}, "d2d4": {"cp": 60}}),    # keep
        _gp_move(24, evals={"e2e4": {"cp": 100}, "d2d4": {"cp": 60}}),    # excluded by human
        _gp_move(26, evals={"e2e4": {"cp": 100}}, gp=False),              # included by human
    ]
    changes = apply_refinement(game, overrides={
        game.id: {"exclude": [24], "include": [26]},
    })
    assert changes == {"dropped": [20, 24], "added": [26]}
    assert [m.ply for m in game.moves if m.is_guess_point] == [22, 26]


def test_apply_refinement_include_beats_obvious_and_needs_evals():
    from guesspoints import apply_refinement
    game = _approved_game()
    game.moves = [
        _gp_move(20, evals={"e2e4": {"cp": 250}, "d2d4": {"cp": -10}}),   # obvious BUT included
        _gp_move(22, evals={}, gp=False),                                  # include without evals -> no-op
    ]
    changes = apply_refinement(game, overrides={game.id: {"include": [20, 22]}})
    assert changes == {"dropped": [], "added": []}
    assert game.moves[0].is_guess_point
    assert not game.moves[1].is_guess_point


# ---------------------------------------------------------------------- audit (5b)

def _claim(cls, quote, piece=None):
    from audit import ExtractedClaim
    return ExtractedClaim(claim_class=cls, quote=quote, piece=piece)


def _audit_move(annotation="x", legal_evals=None, fen=None):
    return MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=fen or START_FEN, mover="white",
        is_guess_point=True, annotation=annotation,
        legal_evals=legal_evals or {"e2e4": {"cp": 30}},
    )


def test_audit_unclassified_claim_fails():
    from audit import check_claims
    errors = check_claims("g", _audit_move(), [_claim("other", "weird claim")], [])
    assert [e.code for e in errors] == ["unclassified_claim"]


def test_audit_future_identifying_is_spoiler_only_when_upcoming():
    from audit import check_claims
    claims = [_claim("future_identifying", "the rook mates next")]
    assert [e.code for e in check_claims("g", _audit_move(), claims, ["Rd8#"])] == ["spoils_future_guess"]
    assert check_claims("g", _audit_move(), claims, []) == []


def test_audit_mate_claims_checked_against_board():
    from audit import check_claims
    # Fool's mate position: Qh4# is mate; e2e4 is not.
    fools = "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2"
    mate_move = MoveRecord(
        ply=4, san="Qh4#", uci="d8h4", fen_before=fools, mover="black",
        is_guess_point=True, annotation="x",
        legal_evals={"d8h4": {"cp": None, "mate": 1}},
    )
    assert check_claims("g", mate_move, [_claim("mate_now", "delivers mate", piece="queen")], []) == []
    errs = check_claims("g", mate_move, [_claim("mate_now", "the rook mates", piece="rook")], [])
    assert [e.code for e in errs] == ["wrong_mating_pieces"]
    errs = check_claims("g", _audit_move(), [_claim("mate_now", "mate on the spot")], [])
    assert [e.code for e in errs] == ["unsupported_mate_claim"]


def test_audit_mate_forced_needs_engine_mate():
    from audit import check_claims
    no_mate = _audit_move()
    assert [e.code for e in check_claims("g", no_mate, [_claim("mate_forced", "forces mate")], [])] \
        == ["unsupported_mate_claim"]
    with_mate = _audit_move(legal_evals={"e2e4": {"cp": None, "mate": 3}})
    assert check_claims("g", with_mate, [_claim("mate_forced", "forces mate")], []) == []


def test_audit_material_and_castling_and_motif():
    from audit import check_claims
    move = _audit_move()  # 1.e4 from start: no captures, opponent castles fine, no motifs
    claims = [
        _claim("material", "wins a pawn"),
        _claim("castling_inability", "king stuck in the center"),
        _claim("tactic_motif", "a deadly fork"),
    ]
    codes = sorted(e.code for e in check_claims("g", move, claims, []))
    assert codes == ["unsupported_material_claim", "unsupported_motif_claim",
                     "unsupported_stuck_king_claim"]


def test_audit_material_claim_routed_to_alt_line():
    from audit import ExtractedClaim, check_claims
    move = _audit_move(legal_evals={
        "e2e4": {"cp": 30, "refutation_pv": []},                   # master: no capture
        "d2d4": {"cp": 10, "refutation_pv": ["e7e5", "d4e5"]},     # alt line HAS a capture
    })
    claim = ExtractedClaim(claim_class="material", quote="wins a pawn", alt_uci="d2d4")
    assert check_claims("g", move, [claim], []) == []
    # Same claim about the master line (no capture) must fail.
    bare = ExtractedClaim(claim_class="material", quote="wins a pawn")
    assert [e.code for e in check_claims("g", move, [bare], [])] == ["unsupported_material_claim"]


def test_audit_interpretive_claims_pass():
    from audit import check_claims
    claims = [_claim("eval_verdict", "White is better"),
              _claim("positional_color", "smooth development")]
    assert check_claims("g", _audit_move(), claims, []) == []


def test_audit_prompt_contains_prose_and_upcoming():
    from audit import build_audit_prompt
    move = _audit_move(annotation="A fine central move.")
    move.alt_annotations = {"d2d4": "Also reasonable."}
    prompt = build_audit_prompt(move, ["Rd1"])
    assert "A fine central move." in prompt
    assert "Rd1" in prompt
    assert "Also reasonable." in prompt


def test_unshippable_reasons():
    g = _approved_game()
    assert build.unshippable_reasons(g) == []
    bad = _approved_game(); bad.moves[0].annotation = None
    assert any("unannotated" in r for r in build.unshippable_reasons(bad))
    empty = _approved_game(); empty.moves[0].is_guess_point = False
    assert any("0 guess points" in r for r in build.unshippable_reasons(empty))


# ---------------------------------------------------------------------- build

def _approved_game():
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, difficulty=1300.0, tags=["tactical"],
        eval_cp=30, legal_evals={"e2e4": {"cp": 30, "mate": None, "refutation_pv": [], "motif": "best"}},
        annotation="e4 stakes the center.", alt_annotations={},
    )
    return GameRecord(
        id="test-game-1", white="A", black="B", event="E", site="S", date="2026.06.09",
        year=2026, result="1-0", eco="C00", hero_color="white", title="T",
        narrative_intro="N", pack_id="p1", ply_count=1,
        source_hash="hash", review_status=store.REVIEW_APPROVED, moves=[move],
    )


def test_build_sqlite_roundtrip(tmp_path):
    import sqlite3
    db = os.path.join(tmp_path, "content.sqlite")
    build.build_sqlite([_approved_game()], db)

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM moves").fetchone()[0] == 1
        raw = conn.execute("SELECT legal_evals, tags FROM moves").fetchone()
        assert json.loads(raw[0])["e2e4"]["motif"] == "best"
        assert json.loads(raw[1]) == ["tactical"]
    finally:
        conn.close()


def test_daily_payload_shape():
    payload = build.daily_payload(_approved_game(), "2026-06-09")
    assert payload["daily_id"] == "2026-06-09"
    assert payload["game"]["moves"][0]["uci"] == "e2e4"
    assert payload["game"]["hero_color"] == "white"


def test_enrich_legal_evals_adds_san_and_refutation_san():
    evals = {
        "e2e4": {"cp": 30, "refutation_pv": ["d7d5", "e4d5"], "motif": "best"},
        "g1f3": {"cp": 20, "refutation_pv": [], "motif": "ok"},
    }
    out = build.enrich_legal_evals(START_FEN, evals)
    assert out["e2e4"]["san"] == "e4"
    assert out["e2e4"]["refutation_san"] == ["d5", "exd5"]   # capture rendered as SAN
    assert out["g1f3"]["san"] == "Nf3"
    assert out["g1f3"]["refutation_san"] == []
    # Original engine fields untouched.
    assert out["e2e4"]["cp"] == 30 and out["e2e4"]["motif"] == "best"
    # Empty/None passthrough.
    assert build.enrich_legal_evals(START_FEN, None) is None
    assert build.enrich_legal_evals(START_FEN, {}) == {}


def test_enrich_legal_evals_skips_garbled_uci_without_failing():
    out = build.enrich_legal_evals(START_FEN, {"zz9": {"cp": 0, "refutation_pv": []}})
    assert "san" not in out["zz9"]          # left unenriched, build survives


def test_build_outputs_carry_enriched_san():
    payload = build.daily_payload(_approved_game(), "2026-06-09")
    evals = payload["game"]["moves"][0]["legal_evals"]
    assert evals["e2e4"]["san"] == "e4"
    assert evals["e2e4"]["refutation_san"] == []


def test_daily_date_rejects_partial_pgn_dates():
    assert build.daily_date_or_none("1956.10.17") == "1956-10-17"
    assert build.daily_date_or_none("1910.??.??") is None   # classic PGN, no month/day
    assert build.daily_date_or_none("") is None
    assert build.daily_date_or_none(None) is None


# ------------------------------------------------------------- store roundtrip

def test_store_roundtrip(tmp_path):
    work = os.path.join(tmp_path, "work")
    game = ingest.parse_pgn_text(SAMPLE_PGN)[0]
    store.save_game(game, work)
    loaded = store.load_game(game.id, work)
    assert loaded.id == game.id
    assert len(loaded.moves) == game.ply_count
    assert loaded.moves[10].san == game.moves[10].san


# ---------------------------------------------------------------------- curate

def test_curate_scores_famous_decisive_game():
    game = ingest.parse_pgn_text(SAMPLE_PGN)[0]
    scored = curate.score_game(game)
    assert scored.decisive is True
    assert scored.has_famous is True          # Fischer
    assert scored.score > 4.0


# ------------------------------------------------------------- validate reading level

def test_validate_flags_run_on_sentence():
    import validate
    long_text = "This is " + " ".join(["word"] * 40) + " and more."
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation=long_text, legal_evals={"e2e4": {"cp": 30}},
    )
    codes = {e.code for e in validate.validate_move("g", move)}
    assert "hard_to_read" in codes


def test_validate_clean_sentence_not_flagged():
    import validate
    move = MoveRecord(
        ply=20, san="e4", uci="e2e4", fen_before=START_FEN, mover="white",
        is_guess_point=True, annotation="e4 grabs the center.",
        legal_evals={"e2e4": {"cp": 30}},
    )
    assert validate.validate_move("g", move) == []


# ----------------------------------------------------------------- pipeline planning

def test_plan_stages_skips_gated_when_deps_missing():
    import run_pipeline
    bare = run_pipeline.plan_stages(has_engine=False, has_key=False)
    assert "analyze" not in bare and "annotate" not in bare
    assert bare == ["ingest", "curate", "validate", "build"]


def test_plan_stages_full_chain_with_deps():
    import run_pipeline
    full = run_pipeline.plan_stages(has_engine=True, has_key=True)
    assert full == ["ingest", "curate", "analyze", "annotate", "validate", "build"]
    # annotate needs an engine too (it consumes legal_evals)
    assert "annotate" not in run_pipeline.plan_stages(has_engine=False, has_key=True)


# --------------------------------------------------------------- curation selection

def test_parse_selected_strips_comments_and_blanks():
    text = "# header\nmorphy-1858  # the opera game\n\nfischer-1956\n   \n"
    assert store.parse_selected(text) == {"morphy-1858", "fischer-1956"}


def test_load_selected_missing_file_is_none(tmp_path):
    assert store.load_selected(os.path.join(tmp_path, "nope.txt")) is None


def test_load_selected_reads_ids(tmp_path):
    path = os.path.join(tmp_path, "selected.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("a-1\n# skip\nb-2\n")
    assert store.load_selected(path) == {"a-1", "b-2"}


# ----------------------------------------------------- free-tier samples (§6)

def test_load_sample_ids_missing_file_is_empty(tmp_path):
    assert store.load_sample_ids(os.path.join(tmp_path, "nope.txt")) == set()


def test_load_sample_ids_reads_ids(tmp_path):
    path = os.path.join(tmp_path, "sample.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("morphy-1858  # showroom\n# comment\nfischer-1956\n")
    assert store.load_sample_ids(path) == {"morphy-1858", "fischer-1956"}


def test_build_sqlite_persists_is_sample(tmp_path):
    import sqlite3
    g = _approved_game()
    g.is_sample = True
    db = os.path.join(tmp_path, "content.sqlite")
    build.build_sqlite([g], db)
    conn = sqlite3.connect(db)
    try:
        flag, = conn.execute("SELECT is_sample FROM games WHERE id = ?", (g.id,)).fetchone()
        assert flag == 1
    finally:
        conn.close()


def test_build_sqlite_default_is_sample_is_zero(tmp_path):
    import sqlite3
    db = os.path.join(tmp_path, "content.sqlite")
    build.build_sqlite([_approved_game()], db)   # is_sample defaults False
    conn = sqlite3.connect(db)
    try:
        flag, = conn.execute("SELECT is_sample FROM games").fetchone()
        assert flag == 0
    finally:
        conn.close()


# ------------------------------------------------------------- review decisions

def test_decisions_roundtrip_and_overwrite(tmp_path):
    path = os.path.join(tmp_path, "decisions.json")
    assert store.load_decisions(path) == {}
    store.record_decision("g1", "approved", path)
    store.record_decision("g2", "rejected", path)
    store.record_decision("g2", "approved", path)   # decision can be revised
    assert store.load_decisions(path) == {"g1": "approved", "g2": "approved"}
