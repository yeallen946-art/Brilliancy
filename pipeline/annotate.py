"""Stage 4 logic — LLM annotation, grounded in engine lines (TECH_SPEC §5, PRD §6).

CLAUDE.md hard rule #1: annotations come ONLY from here, every claim grounded in the
supplied Stockfish lines, and must pass 5_validate.py before shipping. This module builds
the grounded prompt + the structured-output schema and applies results back to the work
store. The actual Anthropic call (Batch API) lives in 4_annotate.py and needs
ANTHROPIC_API_KEY. Everything here is importable + unit-tested without a key.

Model + Batch API per the claude-api reference: model `claude-opus-4-8`, structured output
via output_config.format (json_schema) / client.messages.parse.
"""

from __future__ import annotations

import chess
from pydantic import BaseModel, Field

import facts
from store import GameRecord, MoveRecord

MODEL = "claude-opus-4-8"
INTERESTING_TOP_N = 4        # engine top-N get prose; long-tail templated at runtime (§4)
ANNOTATION_WORD_LIMIT = 60

SYSTEM_PROMPT = """\
You are a chess coach writing short explanations for a "guess the master's move" trainer.

HARD RULES (a validator rejects violations):
- You NARRATE the facts given in the user message; you never assert chess facts of your
  own. Treat the supplied data as the entire universe: never mention a move, line, square,
  piece role, or evaluation that is not present in it. You are describing THIS board, not
  recalling any game you may think you recognize.
- Be honest about the engine's view. If the master's move is NOT the engine's top choice,
  say so plainly. Never call a move "best", "winning", or "crushing" unless the evals
  support it.
- Only name a move in algebraic notation if it is a legal move for the side to move in
  THIS position (i.e. it appears in the candidate list). Describe the OPPONENT's replies
  in words, never in notation.
- Do NOT claim a move "wins", "loses", "drops", or "hangs" material unless the supplied
  facts list a capture in that move's line. Material words must be backed by a listed capture.
- When a mate is involved, the "MATE FACTS" line tells you exactly which pieces give check
  and which cover the escape squares. Credit ONLY those pieces — no others.
- Interpretive color ("the defense is overloaded") is welcome, but its direction must match
  the evals: only describe a side as better/struggling if the numbers say so.

STYLE:
- Audience: 800-2000 rated improvers. Prefer plain plan-language over deep variations.
- Coach tone: encouraging, never mocking a wrong guess.
- Keep every explanation under {limit} words.\
""".format(limit=ANNOTATION_WORD_LIMIT)


# ----------------------------------------------------------------- structured output

class AltAnnotation(BaseModel):
    uci: str = Field(description="UCI of the alternative move, copied from the data.")
    prose: str = Field(description="Why this move is worse / interesting (<60 words).")


class MoveAnnotationResult(BaseModel):
    annotation: str = Field(description="Why the master move works (<60 words).")
    alt_annotations: list[AltAnnotation] = Field(default_factory=list)


class GameIntroResult(BaseModel):
    narrative_intro: str = Field(description="2-3 sentence context, no result spoilers.")


def strict_json_schema(model_cls: type[BaseModel]) -> dict:
    """Pydantic schema -> a strict JSON schema for output_config.format.
    Structured outputs require `additionalProperties: false` and all keys required."""
    schema = model_cls.model_json_schema()
    _strictify(schema)
    return schema


def _strictify(node) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["additionalProperties"] = False
            node["required"] = list(node["properties"].keys())
        for value in node.values():
            _strictify(value)
    elif isinstance(node, list):
        for value in node:
            _strictify(value)


# ------------------------------------------------------------------- prompt building

def _san(fen_before: str, uci: str) -> str:
    try:
        return chess.Board(fen_before).san(chess.Move.from_uci(uci))
    except (ValueError, AssertionError):
        return uci


def _eval_str(entry: dict) -> str:
    if entry.get("mate") is not None:
        return f"#{entry['mate']:+d}"
    cp = entry.get("cp")
    return f"{cp / 100:+.2f}" if cp is not None else "?"


def interesting_moves(move: MoveRecord, top_n: int = INTERESTING_TOP_N) -> list[str]:
    """The master move + the engine's top-N candidates (deduped, master first).
    Only these get LLM prose; long-tail moves are templated at runtime (TECH_SPEC §4)."""
    by_cp = sorted(
        (u for u, e in move.legal_evals.items() if e.get("cp") is not None),
        key=lambda u: move.legal_evals[u]["cp"],
        reverse=True,
    )
    ordered = [move.uci] + [u for u in by_cp if u != move.uci]
    return ordered[: top_n + 1]


def candidate_rows(move: MoveRecord) -> list[dict]:
    rows = []
    for uci in interesting_moves(move):
        entry = move.legal_evals.get(uci, {})
        rows.append({
            "uci": uci,
            "san": _san(move.fen_before, uci),
            "eval": _eval_str(entry),
            "motif": entry.get("motif", "?"),
            "is_master": uci == move.uci,
        })
    return rows


def build_move_prompt(game: GameRecord, move: MoveRecord) -> str:
    """User-message text: position + engine data + computed facts (TECH_SPEC §5.1).

    Game identity is deliberately ABSENT — the model describes this board, not its
    (possibly wrong) memory of a famous game. `game` is accepted for call-site
    compatibility but never read.
    """
    _ = game  # identity intentionally unused (§5.1 strip-identity rule)
    board = chess.Board(move.fen_before)
    mover = "White" if board.turn == chess.WHITE else "Black"
    master_san = _san(move.fen_before, move.uci)
    rows = candidate_rows(move)

    lines = [
        f"Position (FEN): {move.fen_before}",
        f"{mover} to move. The master played: {master_san}.",
        "",
        "Engine evaluations (centipawns from the mover's POV; '#'=mate). "
        "These are the ONLY moves and lines you may reference:",
    ]
    for r in rows:
        tag = " [master]" if r["is_master"] else ""
        entry = move.legal_evals.get(r["uci"], {})
        refutation = entry.get("refutation_pv") or []
        ref = f"  reply: {' '.join(refutation)}" if refutation else ""
        lines.append(f"  {r['san']:7s} {r['eval']:>6s}  ({r['motif']}){tag}{ref}")
        # Computed facts per candidate (the only material/mate claims allowed):
        mat = facts.line_material(move.fen_before, r["uci"], refutation)
        if mat.captures:
            lines.append(f"           captures in line: {', '.join(mat.captures)} "
                         f"(net {mat.net_pawns:+d} pawn-units for the mover)")
        pattern = facts.mate_pattern(move.fen_before, r["uci"])
        if pattern.is_mate:
            lines.append(f"           MATE FACTS: checking piece(s): {', '.join(pattern.checkers)}; "
                         f"escape squares covered by: {', '.join(pattern.supporters) or 'none needed'}")

    alt_sans = ", ".join(r["san"] for r in rows if not r["is_master"])
    lines += [
        "",
        f"Write `annotation`: why {master_san} works — or, if the engine prefers another "
        f"move, what {master_san} is going for, with the engine's honest view.",
        f"Write `alt_annotations` for these moves only: {alt_sans or '(none)'}. For each, "
        "base the note on THAT move's engine reply line above; say why a guesser might try "
        "it and why it is worse. Describe the opponent's replies in words, not notation, and "
        "claim material loss only if that reply line shows a capture.",
    ]
    return "\n".join(lines)


def build_intro_prompt(game: GameRecord) -> str:
    return (
        f"Write a 2-3 sentence narrative intro for this game: "
        f"{game.white} vs {game.black}, {game.event} {game.year}. "
        f"The player to study is {game.hero_color or 'the hero'}. "
        "Set the scene and build anticipation. Do NOT reveal the result or any specific move."
    )


# --------------------------------------------------------------------- apply results

def apply_move_annotation(move: MoveRecord, result: MoveAnnotationResult) -> None:
    move.annotation = result.annotation
    move.alt_annotations = {a.uci: a.prose for a in result.alt_annotations}
