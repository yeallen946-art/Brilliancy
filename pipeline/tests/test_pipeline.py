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
