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
ANNOTATION_CHAR_LIMIT_ZH = 120   # zh counts characters, not words

# Player-name 中译 (PRD §12.1 deterministic table — extend as the library grows;
# names not in the table are kept in the original spelling, never invented).
PLAYER_NAMES_ZH = {
    "Paul Morphy": "保罗·莫菲", "Morphy": "莫菲",
    "Richard Reti": "理查德·雷蒂", "Reti": "雷蒂", "Réti": "雷蒂",
    "Savielly Tartakower": "萨维利·塔尔塔科维尔", "Tartakower": "塔尔塔科维尔",
    "Adolf Anderssen": "阿道夫·安德森", "Anderssen": "安德森",
    "Lionel Kieseritzky": "利昂内尔·基塞里茨基", "Kieseritzky": "基塞里茨基",
    "Jean Dufresne": "让·杜弗雷涅", "Dufresne": "杜弗雷涅",
    "Robert J. Fischer": "鲍比·费舍尔", "Fischer": "费舍尔",
    "Donald Byrne": "唐纳德·伯恩", "Byrne": "伯恩",
    "Duke Karl / Count Isouard": "布伦瑞克公爵与伊苏阿尔伯爵",
    "Mikhail Tal": "米哈伊尔·塔尔", "Tal": "塔尔",
    "Magnus Carlsen": "马格努斯·卡尔森", "Carlsen": "卡尔森",
}


def player_name_zh(name: str) -> str:
    return PLAYER_NAMES_ZH.get(name, name)

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
- King-safety claims are bounded by the CASTLING line in the data: say the enemy king is
  "stuck in the center" / "can no longer castle" ONLY if it has no castling rights left.
  While rights remain, say "still in the center" or "behind in development" instead.

STYLE:
- Audience: 800-2000 rated improvers. Prefer plain plan-language over deep variations.
- Coach tone: encouraging, never mocking a wrong guess.
- Keep every explanation under {limit} words.\
""".format(limit=ANNOTATION_WORD_LIMIT)

# zh narration (PRD §12.1): the SAME hard rules, narrating the SAME facts in Chinese.
# Not a translation pass — the model writes Chinese directly from the engine data.
SYSTEM_PROMPT_ZH = """\
你是一名国际象棋教练,为"猜大师着法"训练应用撰写简短的中文讲解。

硬性规则(校验器会拒绝违规内容):
- 你只能叙述用户消息中提供的事实,绝不自行断言任何棋局事实。提供的数据就是全部世界:
  不得提及数据中不存在的着法、变着、格子、棋子作用或评估。你描述的是这个棋盘,
  不是你记忆中的任何名局。
- 对引擎的评估保持诚实。大师着法若不是引擎首选,要直说。评估不支持时,
  禁用"最佳""必胜""碾压"等说法。
- 只有出现在候选着法列表中的着法才能用记谱法点名;着法记谱保留英文代数记谱法
  (如 Bg5+、O-O-O),不要翻译成中文记谱。对手的应着用文字描述,不用记谱。
- 除非该着法的变着数据中列有吃子,否则不得声称"得子""丢子""丢兵"等子力变化。
- 涉及将杀时,"MATE FACTS"一行明确了哪些棋子参与将杀,只能归功于这些棋子。
- 棋子与战术术语用以下对照,不得自创:兵/马/象/车/后/王;双吃(fork)、
  牵制(pin)、闪将(discovered check)、串击(skewer)。
- 解释性色彩(如"防线不堪重负")欢迎,但方向必须与评估一致。

文风:
- 读者为 800-2000 等级分的中文棋手。讲计划与威胁,不堆变着。
- 教练语气,鼓励为主,绝不嘲讽猜错。
- 每条讲解不超过 {limit} 个字符。\
""".format(limit=ANNOTATION_CHAR_LIMIT_ZH)


def system_prompt(lang: str = "en") -> str:
    return SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT


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


def upcoming_guess_sans(game: GameRecord, move: MoveRecord) -> list[str]:
    """SANs of the master moves the trainee must STILL guess after this one.
    These are spoiler-protected: the annotation for this move may not identify them
    (Jerry's report 2026-06-11: move-9 prose gave away moves 10-11)."""
    return [
        _san(m.fen_before, m.uci)
        for m in game.moves
        if m.is_guess_point and m.ply > move.ply
    ]


def build_move_prompt(game: GameRecord, move: MoveRecord, lang: str = "en") -> str:
    """User-message text: position + engine data + computed facts (TECH_SPEC §5.1).

    Game IDENTITY is deliberately absent — the model describes this board, not its
    (possibly wrong) memory of a famous game. Only the move list is read from `game`,
    to compute which master moves are still unguessed (spoiler guard).
    """
    board = chess.Board(move.fen_before)
    mover = "White" if board.turn == chess.WHITE else "Black"
    master_san = _san(move.fen_before, move.uci)
    upcoming = upcoming_guess_sans(game, move)

    # Drop alternatives whose SAN collides with a still-to-be-guessed master move:
    # the prompt would otherwise ask the model to discuss (and badmouth) the very
    # move the trainee must find later (the "Rd1 is much weaker" leak, 2026-06-11).
    protected = {s.rstrip("+#") for s in upcoming}
    rows = [
        r for r in candidate_rows(move)
        if r["is_master"] or r["san"].rstrip("+#") not in protected
    ]

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
        # Computed facts per candidate (the only material/mate/tactic claims allowed):
        mat = facts.line_material(move.fen_before, r["uci"], refutation)
        if mat.captures:
            lines.append(f"           captures in line: {', '.join(mat.captures)} "
                         f"(net {mat.net_pawns:+d} pawn-units for the mover)")
        motifs = facts.tactical_motifs(move.fen_before, r["uci"])
        if motifs:
            lines.append(f"           tactics: {', '.join(m.replace('_', ' ') for m in motifs)}")
        pattern = facts.mate_pattern(move.fen_before, r["uci"])
        if pattern.is_mate:
            lines.append(f"           MATE FACTS: checking piece(s): {', '.join(pattern.checkers)}; "
                         f"escape squares covered by: {', '.join(pattern.supporters) or 'none needed'}")

    rights = facts.opponent_castling_rights(move.fen_before, move.uci)
    if rights is not None:
        sides = [s for s, ok in (("kingside", rights["kingside"]),
                                 ("queenside", rights["queenside"])) if ok]
        lines += [
            "",
            f"CASTLING: after {master_san}, the opponent "
            + (f"still has castling rights ({' and '.join(sides)})." if sides
               else "has NO castling rights left."),
        ]

    if upcoming:
        lines += [
            "",
            "SPOILER GUARD: after this move, the trainee must still GUESS these master "
            f"moves themselves: {', '.join(upcoming)}. Your prose must not identify any "
            "of them in any way — never name such a move, the piece that will play it, "
            "or its destination square, and never describe its concrete effect (no 'the "
            "rook mates next', no 'the bishop delivers mate'). You may state the engine "
            "VERDICT in general terms ('this forces mate', 'the attack crashes through') "
            "without showing how.",
        ]

    alt_sans = ", ".join(r["san"] for r in rows if not r["is_master"])
    if lang == "zh":
        motif_table = ", ".join(f"{en}={zh}" for en, zh in facts.MOTIF_ZH.items())
        piece_table = ", ".join(f"{en}={zh}" for en, zh in facts.PIECE_NAMES_ZH.items())
        lines += [
            "",
            f"用中文写 `annotation`:为什么 {master_san} 成立 — 若引擎更偏好别的着法,"
            f"则说明 {master_san} 的意图并诚实给出引擎观点。",
            f"用中文为这些着法写 `alt_annotations`(仅限这些):{alt_sans or '(无)'}。"
            "每条都以上方该着法自己的引擎应着变化为依据;说明猜棋的人为何会想走它、为何不如实着。"
            "对手应着用文字描述不用记谱;只有该变化中列了吃子才能声称子力得失。",
            f"术语对照(只用这些):棋子 {piece_table};战术 {motif_table}。"
            "着法记谱保留英文代数记谱法。",
        ]
    else:
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


def build_intro_prompt(game: GameRecord, lang: str = "en") -> str:
    if lang == "zh":
        return (
            f"用中文写 2-3 句对局引言:{player_name_zh(game.white)}(白)对 "
            f"{player_name_zh(game.black)}(黑),{game.event} {game.year}。"
            f"要研究的一方是{'白方' if game.hero_color == 'white' else '黑方'}。"
            "渲染气氛、制造期待。不得透露结果或任何具体着法。"
            "棋手名按给出的中译;表中没有的名字保留原文。"
        )
    return (
        f"Write a 2-3 sentence narrative intro for this game: "
        f"{game.white} vs {game.black}, {game.event} {game.year}. "
        f"The player to study is {game.hero_color or 'the hero'}. "
        "Set the scene and build anticipation. Do NOT reveal the result or any specific move."
    )


# --------------------------------------------------------------------- apply results

def apply_move_annotation(move: MoveRecord, result: MoveAnnotationResult,
                          lang: str = "en") -> None:
    if lang == "zh":
        move.annotation_zh = result.annotation
        move.alt_annotations_zh = {a.uci: a.prose for a in result.alt_annotations}
    else:
        move.annotation = result.annotation
        move.alt_annotations = {a.uci: a.prose for a in result.alt_annotations}
