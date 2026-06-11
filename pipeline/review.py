"""Stage 6 logic — render review HTML (board + annotation side by side, TECH_SPEC §5).

The seed reviewer (1700 USCF) checks annotation *usefulness*; 5_validate checks
*correctness*. Both gates are mandatory before content ships (CLAUDE.md). Pure/importable;
CLI in 6_review.py. Board diagrams come from python-chess's SVG renderer.
"""

from __future__ import annotations

import html

import chess
import chess.svg

import facts
from store import GameRecord, MoveRecord

_STYLE = """
<style>
 body { font-family: -apple-system, system-ui, sans-serif; max-width: 820px; margin: 2rem auto; }
 .point { display: flex; gap: 1rem; align-items: flex-start; border-top: 1px solid #ddd; padding: 1rem 0; }
 .board { flex: 0 0 320px; }
 .note { flex: 1; }
 .intro { font-style: italic; color: #555; }
 .alt { color: #444; font-size: 0.95em; }
 .facts { color: #246; font-size: 0.9em; background: #eef4fb; padding: .4rem .6rem; border-radius: 6px; }
 .spoiler-check { color: #832; font-size: 0.9em; }
 .zh { color: #354; }
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


def _fact_sheet(move: MoveRecord) -> str:
    """One-line computed ground truth for the reviewer (TECH_SPEC §5.2)."""
    entry = move.legal_evals.get(move.uci) or {}
    bits: list[str] = []
    if entry.get("mate") is not None:
        bits.append(f"eval #{entry['mate']:+d}")
    elif entry.get("cp") is not None:
        bits.append(f"eval {entry['cp'] / 100:+.2f}")
    pv = entry.get("refutation_pv") or []
    if pv:
        bits.append("PV: " + " ".join(pv[:4]))
    rights = facts.opponent_castling_rights(move.fen_before, move.uci)
    if rights is not None:
        sides = [s for s, ok in (("K", rights["kingside"]), ("Q", rights["queenside"])) if ok]
        bits.append("opponent castling: " + ("+".join(sides) if sides else "NONE"))
    mat = facts.line_material(move.fen_before, move.uci, pv)
    if mat.captures:
        bits.append(f"captures in line: {', '.join(mat.captures)} (net {mat.net_pawns:+d})")
    motifs = facts.tactical_motifs(move.fen_before, move.uci)
    if motifs:
        bits.append("motifs: " + ", ".join(motifs))
    pattern = facts.mate_pattern(move.fen_before, move.uci)
    if pattern.is_mate:
        bits.append(f"MATE by {', '.join(pattern.checkers)}; cover: {', '.join(pattern.supporters) or 'none'}")
    return " · ".join(bits) or "(no engine data)"


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

    guess_points = list(game.guess_points)
    for move in guess_points:
        parts.append("<div class='point'>")
        parts.append(f"<div class='board'>{_board_svg(move)}</div>")
        parts.append("<div class='note'>")
        parts.append(f"<h3>Move {(move.ply + 1) // 2}: {_esc(move.san)}</h3>")
        # Spoiler lens for the reviewer (Jerry 2026-06-11): the prose above must not
        # give these away — the validator only catches literal SAN mentions, the human
        # catches semantic leaks ("the rook mates next").
        still = ", ".join(_esc(m.san) for m in guess_points if m.ply > move.ply)
        if still:
            parts.append(f"<p class='spoiler-check'><b>Still to guess after this:</b> {still} "
                         "— the annotation must not give these away.</p>")
        # FACT SHEET (TECH_SPEC §5.2): the reviewer verifies prose against printed
        # ground truth, not memory.
        parts.append(f"<p class='facts'><b>Facts:</b> {_esc(_fact_sheet(move))}</p>")
        parts.append(f"<p>{_esc(move.annotation or '(no annotation yet)')}</p>")
        if move.annotation_zh:
            parts.append(f"<p class='zh'>{_esc(move.annotation_zh)}</p>")
        if move.alt_annotations:
            parts.append("<div class='alt'><b>Alternatives:</b><ul>")
            for uci, prose in move.alt_annotations.items():
                zh = (move.alt_annotations_zh or {}).get(uci)
                zh_html = f"<br><span class='zh'>{_esc(zh)}</span>" if zh else ""
                parts.append(f"<li><b>{_esc(_san(move.fen_before, uci))}</b>: {_esc(prose)}{zh_html}</li>")
            parts.append("</ul></div>")
        parts.append("</div></div>")

    parts.append("</body></html>")
    return "\n".join(parts)
