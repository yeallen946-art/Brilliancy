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

from store import GameRecord, MoveRecord

MODEL = "claude-opus-4-8"
INTERESTING_TOP_N = 4        # engine top-N get prose; long-tail templated at runtime (§4)
ANNOTATION_WORD_LIMIT = 60

SYSTEM_PROMPT = """\
You are a chess coach writing short explanations for a "guess the master's move" trainer.

HARD RULES (a validator rejects violations):
- Ground EVERY chess claim in the engine data provided in the user message. Never mention
  a move, line, square, or evaluation that is not present in that data.
- Be honest about the engine's view. If the master's move is NOT the engine's top choice,
  say so plainly. Never call a move "best", "winning", or "crushing" unless the evals
  support it.
- Refer to moves in standard algebraic notation exactly as written in the data (e.g. "Be6").

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
    """User-message text: position + grounded engine data + what to annotate."""
    board = chess.Board(move.fen_before)
    mover = "White" if board.turn == chess.WHITE else "Black"
    master_san = _san(move.fen_before, move.uci)
    rows = candidate_rows(move)

    lines = [
        f"Game: {game.white} vs {game.black}, {game.event} {game.year}.",
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

    alt_sans = ", ".join(r["san"] for r in rows if not r["is_master"])
    lines += [
        "",
        f"Write `annotation`: why {master_san} works — or, if the engine prefers another "
        f"move, what {master_san} is going for, with the engine's honest view.",
        f"Write `alt_annotations` for these moves only: {alt_sans or '(none)'} — "
        "one short note each on why a guesser might try it and why it is worse.",
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
