"""Stage 6 logic — render review HTML (board + annotation side by side, TECH_SPEC §5).

The seed reviewer (1700 USCF) checks annotation *usefulness*; 5_validate checks
*correctness*. Both gates are mandatory before content ships (CLAUDE.md). Pure/importable;
CLI in 6_review.py. Board diagrams come from python-chess's SVG renderer.
"""

from __future__ import annotations

import html

import chess
import chess.svg

from store import GameRecord, MoveRecord

_STYLE = """
<style>
 body { font-family: -apple-system, system-ui, sans-serif; max-width: 820px; margin: 2rem auto; }
 .point { display: flex; gap: 1rem; align-items: flex-start; border-top: 1px solid #ddd; padding: 1rem 0; }
 .board { flex: 0 0 320px; }
 .note { flex: 1; }
 .intro { font-style: italic; color: #555; }
 .alt { color: #444; font-size: 0.95em; }
 h3 { margin: 0 0 .4rem; }
</style>
"""


def _esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def _san(fen_before: str, uci: str) -> str:
    try:
        return chess.Board(fen_before).san(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return uci


def _board_svg(move: MoveRecord) -> str:
    board = chess.Board(move.fen_before)
    try:
        last = chess.Move.from_uci(move.uci)
    except ValueError:
        last = None
    orientation = chess.WHITE if move.mover == "white" else chess.BLACK
    return chess.svg.board(board, size=320, lastmove=last, orientation=orientation)


def render_game_html(game: GameRecord) -> str:
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>Review: {_esc(game.id)}</title>", _STYLE, "</head><body>",
        f"<h1>{_esc(game.title or game.id)}</h1>",
        f"<p>{_esc(game.white)} vs {_esc(game.black)} · {_esc(game.event)} {_esc(game.year)} "
        f"— review status: <b>{_esc(game.review_status)}</b></p>",
    ]
    if game.narrative_intro:
        parts.append(f"<p class='intro'>{_esc(game.narrative_intro)}</p>")

    for move in game.guess_points:
        parts.append("<div class='point'>")
        parts.append(f"<div class='board'>{_board_svg(move)}</div>")
        parts.append("<div class='note'>")
        parts.append(f"<h3>Move {(move.ply + 1) // 2}: {_esc(move.san)}</h3>")
        parts.append(f"<p>{_esc(move.annotation or '(no annotation yet)')}</p>")
        if move.alt_annotations:
            parts.append("<div class='alt'><b>Alternatives:</b><ul>")
            for uci, prose in move.alt_annotations.items():
                parts.append(f"<li><b>{_esc(_san(move.fen_before, uci))}</b>: {_esc(prose)}</li>")
            parts.append("</ul></div>")
        parts.append("</div></div>")

    parts.append("</body></html>")
    return "\n".join(parts)
