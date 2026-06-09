"""Stage 1 logic — parse PGN into work-store GameRecords (TECH_SPEC §5).

Board data (san/uci/fen) comes from python-chess, so every move is legal by construction.
Dedupe is by the uci move sequence hash. Pure/importable; CLI lives in 1_ingest.py.
"""

from __future__ import annotations

import hashlib
import io
import re

import chess
import chess.pgn

from store import GameRecord, MoveRecord, REVIEW_PENDING


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def last_name(name: str) -> str:
    # PGN convention is "Last, First"; fall back to the final token otherwise.
    base = name.split(",")[0] if "," in name else name.split()[-1] if name.split() else name
    return slugify(base)


def hero_from_result(result: str) -> str | None:
    if result == "1-0":
        return "white"
    if result == "0-1":
        return "black"
    return None


def _year(headers: chess.pgn.Headers) -> int | None:
    raw = (headers.get("Date", "") or "")[:4]
    return int(raw) if raw.isdigit() else None


def game_from_pgn(pgn_game: chess.pgn.Game) -> GameRecord:
    board = pgn_game.board()  # honors a FEN header if present
    moves: list[MoveRecord] = []
    uci_seq: list[str] = []

    for ply, move in enumerate(pgn_game.mainline_moves(), start=1):
        mover = "white" if board.turn == chess.WHITE else "black"
        moves.append(MoveRecord(
            ply=ply,
            san=board.san(move),
            uci=move.uci(),
            fen_before=board.fen(),
            mover=mover,
        ))
        uci_seq.append(move.uci())
        board.push(move)

    headers = pgn_game.headers
    source_hash = hashlib.sha1(" ".join(uci_seq).encode("utf-8")).hexdigest()
    white = headers.get("White", "Unknown")
    black = headers.get("Black", "Unknown")
    year = _year(headers)
    result = headers.get("Result", "*")
    game_id = f"{last_name(white)}-{last_name(black)}-{year or 'na'}-{source_hash[:6]}"

    return GameRecord(
        id=game_id,
        white=white,
        black=black,
        event=headers.get("Event", ""),
        site=headers.get("Site", ""),
        date=headers.get("Date", ""),
        year=year,
        result=result,
        eco=headers.get("ECO", ""),
        hero_color=hero_from_result(result),
        title=None,
        narrative_intro=None,
        pack_id=None,
        ply_count=len(moves),
        source_hash=source_hash,
        review_status=REVIEW_PENDING,
        moves=moves,
    )


def parse_pgn_text(text: str) -> list[GameRecord]:
    stream = io.StringIO(text)
    games: list[GameRecord] = []
    while True:
        pgn_game = chess.pgn.read_game(stream)
        if pgn_game is None:
            break
        if pgn_game.errors:
            # Skip unparseable games rather than poison the batch.
            continue
        record = game_from_pgn(pgn_game)
        if record.ply_count > 0:
            games.append(record)
    return games
