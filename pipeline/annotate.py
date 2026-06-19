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

import json
import os

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
- Never write a bare board square or coordinate in prose — the validator reads any
  letter+number like "g5"/"d8" as a move and REJECTS the whole annotation. This is the
  single most common failure, so be strict:
    * a pawn/piece named by its square -> drop the square. Write "the pawn" or "the
      queenside pawn", NEVER "the b5 pawn"; "the bishop", NEVER "the bishop on g5".
    * a destination -> describe by role. Write "drops onto the back rank", NEVER "lands on d8".
  Describe squares only by ROLE ("the back rank", "the long diagonal", "the escape squares").
  A letter+number may appear ONLY inside a listed candidate MOVE's notation (e.g. Bg5+, Rd8#).
- Do NOT claim a move "wins", "loses", "drops", or "hangs" material unless the supplied
  facts list a capture in that move's line. Material words must be backed by a listed capture.
- Do NOT generalize about a CATEGORY of moves ("the other queen moves", "the quieter rook
  moves", "the slow tries all keep the edge"): you are shown only the top candidates, not
  every legal move, so a sweeping claim that a whole class keeps or loses the advantage is
  ungrounded (most such moves are often far worse than the few you see). Characterize only
  the specific alternatives listed in the data, by name.
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
- 散文中绝不能出现单独的格子坐标——校验器会把任何"字母+数字"(如 g5、d8)当成着法
  而拒绝整条讲解。这是最常见的失败,务必严格:
    * 用格子称呼棋子/兵时,去掉格子:写"那个兵""后翼兵",绝不写"b5 兵";写"象",
      绝不写"g5 的象"。
    * 表示落点时,用作用描述:写"杀入底线",绝不写"落在 d8"。
  只能用作用描述格子(如"底线""大斜线""逃格")。"字母+数字"只允许作为候选着法
  列表里某一着的英文代数记谱出现(如 Bg5+、Rd8#)。
- 除非该着法的变着数据中列有吃子,否则不得声称"得子""丢子""丢兵"等子力变化。
- 不得对一整类着法笼统下结论(如"其余后的着法""慢一些的车着""那些缓手都保有优势"):
  你只看到排名靠前的候选着法,并非全部合法着法,因此"某一类着法都保有/丢失优势"
  这种泛泛之论缺乏依据(这类着法多半比你看到的差得多)。只针对数据中列出的具体着法逐一说明。
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

class MoveAnnotationResult(BaseModel):
    rationale: str = Field(description=(
        "1-2 short sentences on WHY the master move works — the plan/idea only, in plain "
        "language. State NO facts: no mate counts, no captures or material, no eval numbers, "
        "no bare squares. Those are given separately and must NOT be repeated."))


class GameIntroResult(BaseModel):
    narrative_intro: str = Field(description="2-3 sentence context, no result spoilers.")


class JudgeResult(BaseModel):
    verdict: str = Field(description="exactly 'pass' or 'revise'")
    issues: list[str] = Field(
        default_factory=list,
        description="concrete grounding/consistency problems; empty when verdict is 'pass'")


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


# ----------------------------------------------------------- OpenRouter (alt provider)
# Stage 4 can run against OpenRouter instead of the Anthropic SDK (Jerry has no Anthropic
# key locally). OpenRouter is OpenAI-compatible — synchronous /chat/completions with a
# json_schema response_format, no batch endpoint. The HTTP call + key handling live in
# 4_annotate.py; these importable helpers are the testable parts. Keys come from a
# gitignored pipeline/.env, never from a memory file or source.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def load_dotenv(path: str) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser (no dependency). Sets parsed keys into os.environ
    WITHOUT overriding values already in the real environment; returns what it parsed.
    Missing file -> {}. Ignores blank lines, comments, and `export ` prefixes."""
    parsed: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return parsed
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        parsed[key] = value
        os.environ.setdefault(key, value)
    return parsed


# Low temperature: annotations are grounded fact-narration, not creative writing — keep the
# model tight to the rules (sentence-length / no-material-without-capture slips drop sharply).
OPENROUTER_TEMPERATURE = 0.2


def openrouter_request_body(model: str, system: str, user_content: str,
                            schema_model: type[BaseModel], max_tokens: int) -> dict:
    """OpenAI-compatible chat-completions body with strict json_schema structured output —
    the same MoveAnnotationResult/GameIntroResult schema the Anthropic path enforces."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": OPENROUTER_TEMPERATURE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_model.__name__,
                "strict": True,
                "schema": strict_json_schema(schema_model),
            },
        },
    }


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


def _fact_sheet_for(move: MoveRecord) -> facts.FactSheet:
    """Deterministic FactSheet for the master move (ANNOTATION_PIPELINE_V2 §3.1)."""
    entry = move.legal_evals.get(move.uci) or {}
    cp = entry["cp"] if "cp" in entry else move.eval_cp
    mate = entry["mate"] if "mate" in entry else move.eval_mate
    return facts.build_fact_sheet(move.fen_before, move.uci, eval_cp=cp, eval_mate=mate)


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

    # The deterministic fact line (checkmate / forced mate in N / eval verdict) is composed
    # by facts.build_fact_sheet and prepended to the rationale downstream. Show it here so
    # the model writes ONLY the "why" and never restates a fact it could get wrong (the whole
    # point of v2: facts are not LLM-generated). See ANNOTATION_PIPELINE_V2 §3.1-3.2.
    _fact_line = (_fact_sheet_for(move).fact_line_zh if lang == "zh"
                  else _fact_sheet_for(move).fact_line_en)
    if _fact_line:
        lines += [
            "",
            "FACTS ALREADY STATED — these are prepended to your rationale; do NOT repeat or "
            f"re-derive them (no mate counts, no eval numbers): \"{_fact_line}\"",
        ]

    # BRANCH FACTS: when THIS move delivers mate and the hero's PREVIOUS move was a
    # forced mate-in-two, list every defense + its mate so the prose can honestly say
    # "every retreat lost" (Jerry 2026-06-11: Réti has Kc7->Bd8# AND Ke8->Rd8#).
    # Only at the FINAL mate — earlier plies would spoil still-unguessed moves.
    if facts.mate_pattern(move.fen_before, move.uci).is_mate:
        prior = next((m for m in reversed(game.moves)
                      if m.ply < move.ply - 1 and m.mover == move.mover), None)
        if prior is not None:
            branches = facts.mate_in_two_defenses(prior.fen_before, prior.uci)
            if len(branches) > 1:
                lines += ["", "BRANCH FACTS (the game is over after this move; nothing left "
                              "to spoil): one move earlier the mate was already forced in "
                              "every variation. Defenses and their mates:"]
                for b in branches:
                    lines.append(
                        f"  reply {b['reply_san']} -> {b['mate_san']} "
                        f"(checkers: {', '.join(b['checkers'])}; "
                        f"covers: {', '.join(b['supporters']) or 'none needed'})")
                lines.append(
                    "  You may say every defense lost and credit ONLY the pieces listed "
                    "above; describe the opponent's alternative replies in words, never "
                    "in notation.")

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

    if lang == "zh":
        motif_table = ", ".join(f"{en}={zh}" for en, zh in facts.MOTIF_ZH.items())
        piece_table = ", ".join(f"{en}={zh}" for en, zh in facts.PIECE_NAMES_ZH.items())
        lines += [
            "",
            f"用中文写 `rationale`:为什么 {master_san} 成立 —— 只写计划/思路,1-2 句。"
            "不要重复上面已陈述的事实(不写第几步将杀、不写得失子、不写分数、不写裸格子)。"
            f"若引擎更偏好别的着法,就诚实说明 {master_san} 的意图。",
            f"术语对照(只用这些):棋子 {piece_table};战术 {motif_table}。"
            "着法记谱保留英文代数记谱法(如 Bg5+)。",
        ]
    else:
        lines += [
            "",
            f"Write `rationale`: why {master_san} works — the plan/idea only, 1-2 short "
            "sentences. Do NOT repeat the facts already stated above (no mate counts, no "
            "material, no eval numbers, no bare squares). If the engine prefers another move, "
            f"say honestly what {master_san} is going for.",
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

def compose_annotation(move: MoveRecord, rationale: str, lang: str = "en") -> str:
    """Final annotation = deterministic fact_line + the LLM rationale (v2 §3.2). The
    fact_line carries the verifiable claims; the rationale carries only the 'why'."""
    fs = _fact_sheet_for(move)
    line = fs.fact_line_zh if lang == "zh" else fs.fact_line_en
    rationale = (rationale or "").strip()
    return f"{line} {rationale}".strip() if line else rationale


def _validate_one(game_id: str, move: MoveRecord, text: str, lang: str,
                  upcoming_sans: list[str]) -> list[str]:
    import validate
    where = "annotation_zh" if lang == "zh" else "annotation"
    return [e.message for e in
            validate.validate_annotation_text(game_id, move, text, where, upcoming_sans)]


def build_judge_prompt(move: MoveRecord, composed: str, lang: str = "en") -> str:
    """Check the explanation for CONSISTENCY with authoritative engine facts (v2 §3.3).

    Hard lesson (Jerry 2026-06-19 live run): asking the judge to re-derive legality/geometry
    from a FEN makes it hallucinate (it called the real played move 'illegal') and flag
    everything. So we feed it the ground-truth facts and forbid re-derivation — the judge
    only checks the prose against those facts, the same fact-vs-interpretation split as the
    rest of v2. It cannot catch motif-detector looseness (a separate, deferred concern)."""
    fs = _fact_sheet_for(move)
    san = _san(move.fen_before, move.uci)
    motifs = facts.tactical_motifs(move.fen_before, move.uci)
    motif_str = ", ".join(motifs) if motifs else "none"
    verdict = ("checkmate" if fs.is_checkmate
               else f"forced mate in {fs.mate_in}" if fs.mate_in
               else f"engine eval {fs.eval_cp}cp for the side to move")
    return (
        "Check whether one chess explanation is CONSISTENT with the authoritative facts "
        "below. These facts are GROUND TRUTH from an engine. Do NOT question them, do NOT "
        "re-derive legality, checks, diagonals, or mate — the move was actually played and "
        "is legal. Only compare the prose against the facts.\n"
        f"Move: {san}. Engine verdict: {verdict}. Tactics actually present (the ONLY tactic "
        f"names that may legitimately appear): {motif_str}.\n"
        f"Explanation ({lang}):\n\"\"\"{composed}\"\"\"\n\n"
        "Flag a problem ONLY if the explanation:\n"
        "- names a tactic/motif NOT in the 'tactics actually present' list, or\n"
        "- contradicts the engine verdict (calls a winning move weak, denies the mate, etc.), or\n"
        "- is generic filler that doesn't explain THIS move's idea.\n"
        "Be conservative: when unsure, verdict='pass'. Otherwise verdict='revise' and quote the "
        "exact phrase at fault."
    )


def generate_rationale_with_repair(game_id: str, move: MoveRecord, lang: str,
                                   upcoming_sans: list[str], *, generate, judge=None,
                                   max_repairs: int = 3) -> tuple[str, list[str]]:
    """Per-field generate -> compose -> validate -> judge -> repair loop (v2 §3.4).

    `generate(error_messages)` returns a rationale; on a repair pass it receives the prior
    issues so it can fix exactly those (no blind whole-game re-roll). `judge(composed)`
    (optional) returns a list of grounding/consistency issues and runs only AFTER the cheap
    deterministic checks pass. Returns (composed_annotation, residual_issues): residual empty
    means clean; non-empty means the caller should flag the move NEEDS_HUMAN."""
    errors: list[str] = []
    composed = ""
    for _ in range(max_repairs + 1):
        rationale = generate(errors)
        composed = compose_annotation(move, rationale, lang)
        errors = _validate_one(game_id, move, composed, lang, upcoming_sans)
        if not errors and judge is not None:
            errors = judge(composed)            # only spend a judge call on validator-clean text
        if not errors:
            return composed, []
    return composed, errors


def apply_move_annotation(move: MoveRecord, result: MoveAnnotationResult,
                          lang: str = "en") -> None:
    composed = compose_annotation(move, result.rationale, lang)
    # Alt-move notes are templated by the app (GuessExplainer) from the engine reply line,
    # not generated here (v2 decision E) — leave them empty.
    if lang == "zh":
        move.annotation_zh = composed
        move.alt_annotations_zh = {}
    else:
        move.annotation = composed
        move.alt_annotations = {}
