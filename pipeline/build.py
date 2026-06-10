"""Stage 7 logic — assemble approved games into content.sqlite + daily JSON (TECH_SPEC §4).

Importable + tested; CLI in 7_build.py. Schema mirrors TECH_SPEC §4 exactly so the app's
read-only GRDB layer can rely on it.
"""

from __future__ import annotations

import json
import os
import sqlite3

from store import GameRecord

SCHEMA = """
CREATE TABLE games (
    id TEXT PRIMARY KEY,
    white TEXT, black TEXT, event TEXT, year INTEGER, result TEXT, eco TEXT,
    hero_color TEXT, title TEXT, narrative_intro TEXT, pack_id TEXT, ply_count INTEGER
);
CREATE TABLE moves (
    game_id TEXT, ply INTEGER, san TEXT, uci TEXT, fen_before TEXT,
    is_guess_point INTEGER, difficulty REAL, tags TEXT,
    eval_cp INTEGER, eval_mate INTEGER,
    legal_evals TEXT, annotation TEXT, alt_annotations TEXT,
    PRIMARY KEY (game_id, ply)
);
CREATE TABLE packs (
    id TEXT PRIMARY KEY, name TEXT, kind TEXT, description TEXT,
    price_tier TEXT, sort_order INTEGER
);
"""


def _move_row(game_id: str, m) -> tuple:
    return (
        game_id, m.ply, m.san, m.uci, m.fen_before,
        1 if m.is_guess_point else 0, m.difficulty, json.dumps(m.tags),
        m.eval_cp, m.eval_mate,
        json.dumps(m.legal_evals), m.annotation, json.dumps(m.alt_annotations),
    )


def build_sqlite(games: list[GameRecord], db_path: str, packs: list[dict] | None = None) -> None:
    """(Re)build the content DB at db_path from the given games. Overwrites any existing file."""
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for g in games:
            conn.execute(
                "INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (g.id, g.white, g.black, g.event, g.year, g.result, g.eco,
                 g.hero_color, g.title, g.narrative_intro, g.pack_id, g.ply_count),
            )
            conn.executemany(
                "INSERT INTO moves VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [_move_row(g.id, m) for m in g.moves],
            )
        for p in packs or []:
            conn.execute(
                "INSERT INTO packs VALUES (?,?,?,?,?,?)",
                (p["id"], p["name"], p["kind"], p.get("description", ""),
                 p.get("price_tier", "premium"), p.get("sort_order", 0)),
            )
        conn.commit()
    finally:
        conn.close()


def unshippable_reasons(game: GameRecord) -> list[str]:
    """Why a game must NOT ship (TECH_SPEC §9 / reviewer guard): no empty or partly-
    annotated games in content.sqlite or daily JSON."""
    reasons: list[str] = []
    guess_points = [m for m in game.moves if m.is_guess_point]
    if not guess_points:
        reasons.append("0 guess points (not analyzed)")
    unannotated = [m.ply for m in guess_points if not m.annotation]
    if unannotated:
        reasons.append(f"unannotated guess points at plies {unannotated}")
    if not game.title:
        reasons.append("missing title")
    return reasons


def daily_date_or_none(pgn_date: str | None) -> str | None:
    """Convert a PGN date ('1956.10.17') to 'YYYY-MM-DD', or None for partial dates
    ('1910.??.??') — many classic PGNs lack a real month/day."""
    parts = (pgn_date or "").split(".")
    if len(parts) == 3 and len(parts[0]) == 4 and all(p.isdigit() for p in parts):
        return "-".join(parts)
    return None


def daily_payload(game: GameRecord, date: str) -> dict:
    """One full game in the daily-challenge JSON shape (TECH_SPEC §4)."""
    return {
        "daily_id": date,
        "game": {
            "id": game.id, "white": game.white, "black": game.black,
            "event": game.event, "year": game.year, "result": game.result,
            "eco": game.eco, "hero_color": game.hero_color, "title": game.title,
            "narrative_intro": game.narrative_intro, "ply_count": game.ply_count,
            "moves": [
                {
                    "ply": m.ply, "san": m.san, "uci": m.uci, "fen_before": m.fen_before,
                    "is_guess_point": m.is_guess_point, "difficulty": m.difficulty,
                    "tags": m.tags, "eval_cp": m.eval_cp, "eval_mate": m.eval_mate,
                    "legal_evals": m.legal_evals, "annotation": m.annotation,
                    "alt_annotations": m.alt_annotations,
                }
                for m in game.moves
            ],
        },
    }


def write_daily(game: GameRecord, date: str, daily_dir: str) -> str:
    os.makedirs(daily_dir, exist_ok=True)
    path = os.path.join(daily_dir, f"{date}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(daily_payload(game, date), fh, ensure_ascii=False, indent=2)
    return path
