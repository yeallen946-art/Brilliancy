"""Stage 5 logic — automated annotation validation (TECH_SPEC §5, PRD §6).

Enforces the annotation grounding contract: every move mentioned in prose must be legal
and present in the engine's `legal_evals`; eval adjectives must match the numbers; the
master move may not be claimed "best/winning" if the evals say otherwise (the §3.2 honesty
rule); length limits apply. Importable + unit-tested with known-bad annotations; CLI in
5_validate.py. Uses python-chess to parse SAN against the real position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import chess

import facts
from store import GameRecord, MoveRecord

MAX_ANNOTATION_CHARS = 400
# Reading level for 800-2000 improvers (TECH_SPEC §5, PRD): keep sentences digestible.
MAX_SENTENCE_WORDS = 35
MAX_SENTENCE_CHARS_CJK = 60   # zh has no word spaces; bound characters instead

# English + Chinese claim wordlists run as a UNION on every prose field — zh patterns
# can't false-positive on English text and vice versa, so no language branching.
WINNING_WORDS = ("winning", "crushing", "decisive", "completely won", "totally winning",
                 "胜势", "必胜", "赢定", "完全获胜", "碾压")
EQUAL_WORDS = ("equal", "balanced", "level", "roughly equal",
               "均势", "局面相当", "势均力敌", "基本相等")
BEST_WORDS = ("the best move", "best move", "only move", "objectively best",
              "最佳着法", "唯一着法", "唯一的着法", "客观最佳", "唯一可行")
# Material claims must be backed by a capture in the engine line (TECH_SPEC §5 honesty rule).
# Phrases, not bare "drops" (avoids false positives like "drops the advantage").
MATERIAL_WORDS = (
    "drops material", "drops a piece", "drops a pawn", "drops the exchange",
    "loses material", "loses a piece", "loses a pawn", "loses the exchange",
    "wins a pawn", "win a pawn", "wins material", "win material", "wins a piece",
    "wins the exchange", "grabs a pawn", "snaps off a pawn", "and a pawn",
    "extra pawn", "up a pawn", "hangs a",
    "丢子", "失子", "丢兵", "丢车", "丢马", "丢象", "丢后", "白丢",
    "得子", "得兵", "白得", "净赚", "赢得子力", "多一个兵", "多一兵", "吃亏子力",
)

WINNING_THRESHOLD_CP = 200   # "winning" needs >= +2.0 for the mover
EQUAL_BAND_CP = 50           # "equal" needs |eval| <= 0.5

# A SAN-ish token: castling or a destination-square move (must carry file+rank), so plain
# English words don't match. Latin-only lookarounds instead of \b: Python treats CJK as
# word characters, so \b would MISS a SAN glued to Chinese text ("走Bg5+之后").
SAN_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(O-O-O|O-O|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?)(?![A-Za-z0-9])"
)

# "King stuck in the center" class of claim — only allowed when the enemy king has
# NO castling rights left (facts.opponent_castling_rights). Jerry 2026-06-11: the
# Opera m9 prose overclaimed while Black could still castle either side.
STUCK_KING_RE = re.compile(
    r"(\bstuck in the cent|\btrapped in the cent|\bcan(?:not|'t) castle|"
    r"\bno longer castle|\bnever castles?|\bunable to castle|"
    r"困在中[路心央]|无法易位|不能易位|再也不能易位|被困在中)", re.I
)

# Mate-claim patterns checked against facts.mate_pattern (the "two bishops" class).
# "double-bishop mate", "two rooks", "both knights", "pair of bishops" / 双象、两个车:
DOUBLE_KIND_RE = re.compile(
    r"\b(?:two|both|double|pair of)[\s-]+(pawns?|knights?|bishops?|rooks?|queens?)\b", re.I
)
DOUBLE_KIND_RE_ZH = re.compile(r"(?:双|两[个只枚]?)\s*(兵|马|象|车|后)")
# "rook mate", "queen mates" / "车将杀"、"后完成将杀": the credited kind must participate.
MATE_CREDIT_RE = re.compile(
    r"\b(pawn|knight|bishop|rook|queen)[\s-]+mates?\b", re.I
)
MATE_CREDIT_RE_ZH = re.compile(r"(兵|马|象|车|后)(?:完成|实施|发动)?将杀")

ZH_PIECE_KIND = {"兵": "pawn", "马": "knight", "象": "bishop", "车": "rook", "后": "queen"}

# Mate-DISTANCE wording ("mate in three", "forced mate next move", "下一步...将杀") must
# equal the engine's forced-mate count. Jerry 2026-06-17: Réti move-10 (engine #2) was
# narrated as "forced mate next move" (=#1), colliding with the real move-11 mate and
# reading as off-by-one against move-9's "mate in three". The count is an engine fact.
MATE_DISTANCE_RE = re.compile(
    r"\bmates?\s+(?:in\s+([a-z]+|\d+)|(next\s+move))\b", re.I
)
MATE_DISTANCE_RE_ZH = re.compile(
    r"(下一步|[一二两三四五六七八九十]+步)(?:内|即)?[^。,，！!?？]{0,6}?将杀"
)
EN_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
ZH_NUMBER_WORDS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

# Blanket claims about a CLASS of moves ("the quieter queen moves keep a big advantage")
# must hold across that piece's moves in legal_evals. Jerry 2026-06-17: Opera m16 said
# exactly this while 12 of 15 queen moves were blunders — the LLM generalized from the
# two good retreats it was shown to the whole class. We have every legal move at build,
# so the claim is checkable. EN only (the zh mirror is caught by prompt + human review).
CLASS_CLAIM_RE = re.compile(
    r"\b(?:other|quiet|quieter|slow|slower|slowest|remaining|alternative|those|rest of the)\s+"
    r"(queen|rook|bishop|knight|pawn|king)\s+moves\b", re.I
)
KEEPS_ADVANTAGE_RE = re.compile(
    r"\b(?:keep|keeps|hold|holds|retain|retains|stay|stays|remain|remains|still)\b[^.!?]*?"
    r"\b(?:advantage|winning|better|edge|initiative|pressure|upper hand|on top|a plus)\b", re.I
)
PIECE_WORD_TO_TYPE = {
    "pawn": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP,
    "rook": chess.ROOK, "queen": chess.QUEEN, "king": chess.KING,
}
MIN_CLASS_MOVES = 3   # need enough of that piece's moves for a class claim to be meaningful


@dataclass
class ValidationError:
    game_id: str
    ply: int
    code: str
    message: str


def extract_san_tokens(text: str) -> list[str]:
    return SAN_TOKEN_RE.findall(text or "")


def longest_sentence_words(text: str) -> int:
    """Word count of the longest sentence (rough readability proxy)."""
    sentences = re.split(r"[.!?]+", text or "")
    return max((len(s.split()) for s in sentences), default=0)


def _has_cjk(text: str) -> bool:
    return re.search(r"[一-鿿]", text or "") is not None


def longest_sentence_chars(text: str) -> int:
    """Longest sentence in characters — readability proxy for zh (no word spaces)."""
    sentences = re.split(r"[。!?.!?]+", text or "")
    return max((len(s.strip()) for s in sentences), default=0)


def _master_cp(move: MoveRecord) -> int | None:
    entry = move.legal_evals.get(move.uci)
    if entry is not None and entry.get("cp") is not None:
        return entry["cp"]
    return move.eval_cp


def _master_is_mate_for_mover(move: MoveRecord) -> bool:
    entry = move.legal_evals.get(move.uci) or {}
    mate = entry.get("mate")
    return mate is not None and mate > 0


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(p in low for p in phrases)


def _check_mentioned_moves(text: str, fen_before: str, legal_ucis: set,
                           game_id: str, ply: int) -> list[ValidationError]:
    """Every move named in prose must be legal at this position and in engine output."""
    errors: list[ValidationError] = []
    board = chess.Board(fen_before)
    for token in extract_san_tokens(text):
        try:
            parsed = board.parse_san(token)
        except ValueError:
            errors.append(ValidationError(
                game_id, ply, "illegal_move_mentioned",
                f"references illegal move '{token}'"))
            continue
        if legal_ucis and parsed.uci() not in legal_ucis:
            errors.append(ValidationError(
                game_id, ply, "move_outside_engine_output",
                f"move '{token}' is not in legal_evals"))
    return errors


def line_has_capture(fen_before: str, move_uci: str, refutation_pv: list) -> bool:
    """True if move + line contains a capture (backs material claims). Delegates to
    facts.line_material — one extractor, two consumers (TECH_SPEC §5.1)."""
    return bool(facts.line_material(fen_before, move_uci, refutation_pv).captures)


def check_mate_claims(text: str, pattern: facts.MatePattern,
                      game_id: str, ply: int) -> list[ValidationError]:
    """Verify piece-credit claims about a mate against the computed mate pattern
    (the 'double-bishop' class of error). Board-aware, not vibes."""
    errors: list[ValidationError] = []
    if not pattern.is_mate or not text:
        return errors
    double_claims = [(m.group(0), m.group(1).rstrip("s").lower())
                     for m in DOUBLE_KIND_RE.finditer(text)]
    double_claims += [(m.group(0), ZH_PIECE_KIND[m.group(1)])
                      for m in DOUBLE_KIND_RE_ZH.finditer(text)]
    for quote, kind in double_claims:
        if pattern.kind_count(kind) < 2:
            errors.append(ValidationError(
                game_id, ply, "wrong_mating_pieces",
                f"claims '{quote}' but only {pattern.kind_count(kind)} {kind}(s) "
                f"participate in the mate ({pattern.checkers + pattern.supporters})"))

    credit_claims = [(m.group(0), m.group(1).lower())
                     for m in MATE_CREDIT_RE.finditer(text)]
    credit_claims += [(m.group(0), ZH_PIECE_KIND[m.group(1)])
                      for m in MATE_CREDIT_RE_ZH.finditer(text)]
    for quote, kind in credit_claims:
        if kind not in pattern.participant_kinds:
            errors.append(ValidationError(
                game_id, ply, "wrong_mating_pieces",
                f"credits the {kind} with the mate ('{quote}'), but participants are "
                f"{pattern.checkers + pattern.supporters}"))
    return errors


def _parse_distance_en(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return EN_NUMBER_WORDS.get(token)


def _parse_distance_zh(token: str) -> int | None:
    token = token.strip()
    if token == "下一步":
        return 1
    return ZH_NUMBER_WORDS.get(token.replace("步", ""))


def check_mate_distance(text: str, mate_n: int | None, delivers_mate: bool,
                        game_id: str, ply: int, where: str) -> list[ValidationError]:
    """Mate-distance wording ('mate in three' / '下一步...将杀') must equal the engine's
    forced-mate count. Only fires when the master move IS a forced mate for the mover;
    "next move" / "下一步" mean mate-in-one only (the Réti move-10 off-by-one).

    If the move ITSELF delivers checkmate (`delivers_mate`), ANY distance phrase is wrong —
    the move is mate now, so the prose must say "checkmate", not "mate in 1" (Jerry
    2026-06-18: Opera Rd8# said "mate in 1" although it is the mating move)."""
    errors: list[ValidationError] = []
    if not text or mate_n is None or mate_n <= 0:
        return errors
    stated: list[tuple[str, int]] = []
    for m in MATE_DISTANCE_RE.finditer(text):
        d = 1 if m.group(2) else _parse_distance_en(m.group(1))
        if d is not None:
            stated.append((m.group(0), d))
    for m in MATE_DISTANCE_RE_ZH.finditer(text):
        d = _parse_distance_zh(m.group(1))
        if d is not None:
            stated.append((m.group(0), d))
    for quote, d in stated:
        if delivers_mate:
            errors.append(ValidationError(
                game_id, ply, "mate_distance_mismatch",
                f"{where}: prose says '{quote.strip()}' but this move DELIVERS checkmate — "
                f"say 'checkmate', not a distance"))
        elif d != mate_n:
            errors.append(ValidationError(
                game_id, ply, "mate_distance_mismatch",
                f"{where}: prose says '{quote.strip()}' (mate in {d}) but the engine "
                f"reads a forced mate in {mate_n}"))
    return errors


def _piece_moves_keeping(move: MoveRecord, piece_type: int) -> tuple[int, int]:
    """(keeping, total) over `move`'s legal_evals for moves BY the given piece type,
    excluding the master move. 'Keeping' = the mover stays at least equal (cp >= 0) or
    has a winning mate. Piece type is read from the board, never guessed."""
    board = chess.Board(move.fen_before)
    keeping = total = 0
    for uci, entry in move.legal_evals.items():
        if uci == move.uci or len(uci) < 4:
            continue
        try:
            piece = board.piece_at(chess.parse_square(uci[:2]))
        except ValueError:
            continue
        if piece is None or piece.piece_type != piece_type:
            continue
        total += 1
        cp = entry.get("cp")
        mate = entry.get("mate")
        if (mate is not None and mate > 0) or (cp is not None and cp >= 0):
            keeping += 1
    return keeping, total


def check_class_generalization(text: str, move: MoveRecord,
                               game_id: str, ply: int, where: str) -> list[ValidationError]:
    """Flag a blanket 'the <quieter> <piece> moves keep the advantage' claim when, per
    legal_evals, the MAJORITY of that piece's non-master moves do NOT keep it (the Opera
    m16 'quieter queen moves keep a big advantage' overgeneralization). Conservative:
    needs an explicit keep-advantage verb in the same sentence and >= MIN_CLASS_MOVES of
    that piece, and only fires when most actually throw the advantage away."""
    errors: list[ValidationError] = []
    if not text or not move.legal_evals:
        return errors
    for sentence in re.split(r"[.!?]+", text):
        if not KEEPS_ADVANTAGE_RE.search(sentence):
            continue
        for m in CLASS_CLAIM_RE.finditer(sentence):
            piece_type = PIECE_WORD_TO_TYPE[m.group(1).lower()]
            keeping, total = _piece_moves_keeping(move, piece_type)
            if total >= MIN_CLASS_MOVES and keeping * 2 < total:
                errors.append(ValidationError(
                    game_id, ply, "overgeneralized_class_claim",
                    f"{where}: claims '{m.group(0)}' keep the advantage, but only "
                    f"{keeping}/{total} {m.group(1).lower()} moves stay at least equal "
                    f"(the rest throw it away)"))
    return errors


def _normalize_san(san: str) -> str:
    return san.rstrip("+#")


def check_future_guess_spoilers(text: str, upcoming_sans: list[str],
                                game_id: str, ply: int, where: str) -> list[ValidationError]:
    """Prose at one guess point must not NAME a master move the trainee still has to
    guess (Jerry 2026-06-11). Deterministic half of the spoiler guard: literal SAN
    mentions. Semantic spoilers ('the rook mates next') are the annotate-prompt's and
    the human reviewer's job — strings can't judge those."""
    if not text or not upcoming_sans:
        return []
    upcoming = {_normalize_san(s) for s in upcoming_sans}
    return [
        ValidationError(
            game_id, ply, "spoils_future_guess",
            f"{where} names '{token}', a master move the trainee still has to guess")
        for token in extract_san_tokens(text)
        if _normalize_san(token) in upcoming
    ]


def _validate_main_prose(game_id: str, move: MoveRecord, text: str, where: str,
                         upcoming_sans: list[str]) -> list[ValidationError]:
    """All checks for one main-annotation text (en or zh — wordlists are unioned,
    SAN/spoiler/mate/castling checks are language-independent)."""
    errors: list[ValidationError] = []

    # 1) length + reading level (words for en, characters for zh)
    if len(text) > MAX_ANNOTATION_CHARS:
        errors.append(ValidationError(
            game_id, move.ply, "too_long",
            f"{where} {len(text)} chars > {MAX_ANNOTATION_CHARS}",
        ))
    if _has_cjk(text):
        longest = longest_sentence_chars(text)
        if longest > MAX_SENTENCE_CHARS_CJK:
            errors.append(ValidationError(
                game_id, move.ply, "hard_to_read",
                f"{where}: longest sentence is {longest} chars > {MAX_SENTENCE_CHARS_CJK}",
            ))
    else:
        longest = longest_sentence_words(text)
        if longest > MAX_SENTENCE_WORDS:
            errors.append(ValidationError(
                game_id, move.ply, "hard_to_read",
                f"{where}: longest sentence is {longest} words > {MAX_SENTENCE_WORDS}",
            ))

    # 2) every mentioned move is legal AND in engine output (legal_evals)
    legal_ucis = set(move.legal_evals.keys())
    errors.extend(_check_mentioned_moves(text, move.fen_before, legal_ucis, game_id, move.ply))

    # 3) eval adjectives must match numbers; honesty rule for "best/winning"
    cp = _master_cp(move)
    is_mate = _master_is_mate_for_mover(move)
    if _contains_any(text, WINNING_WORDS) and not is_mate:
        if cp is None or cp < WINNING_THRESHOLD_CP:
            errors.append(ValidationError(
                game_id, move.ply, "eval_adjective_mismatch",
                f"{where}: 'winning' claim but eval is {cp}cp (< {WINNING_THRESHOLD_CP})",
            ))
    if _contains_any(text, EQUAL_WORDS):
        if cp is None or abs(cp) > EQUAL_BAND_CP:
            errors.append(ValidationError(
                game_id, move.ply, "eval_adjective_mismatch",
                f"{where}: 'equal' claim but eval is {cp}cp",
            ))
    if _contains_any(text, BEST_WORDS) and not is_mate:
        best = max((e["cp"] for e in move.legal_evals.values() if e.get("cp") is not None), default=None)
        if best is not None and cp is not None and best - cp > 10:
            errors.append(ValidationError(
                game_id, move.ply, "false_best_claim",
                f"{where}: claims 'best' but master move is {best - cp}cp below the engine best",
            ))

    # 4) mate piece-credit claims, checked against the computed mate pattern (§5.1).
    pattern = facts.mate_pattern(move.fen_before, move.uci)
    errors.extend(check_mate_claims(text, pattern, game_id, move.ply))

    # 4d) mate-DISTANCE wording must match the engine's forced-mate count (§5.1); a move
    # that itself checkmates must say "checkmate", not "mate in 1".
    master_mate = (move.legal_evals.get(move.uci) or {}).get("mate")
    delivers_mate = facts.mate_pattern(move.fen_before, move.uci).is_mate
    errors.extend(check_mate_distance(text, master_mate, delivers_mate, game_id, move.ply, where))

    # 4e) blanket "the <quieter> <piece> moves keep the advantage" claims must hold across
    # that piece's moves in legal_evals (Opera m16 overgeneralization, §5.1).
    errors.extend(check_class_generalization(text, move, game_id, move.ply, where))

    # 4b) spoiler guard: must not name a master move the trainee still has to guess.
    errors.extend(check_future_guess_spoilers(
        text, upcoming_sans, game_id, move.ply, where))

    # 4c) "stuck in the center" claims need the rights to actually be gone.
    if STUCK_KING_RE.search(text):
        rights = facts.opponent_castling_rights(move.fen_before, move.uci)
        if rights is not None and (rights["kingside"] or rights["queenside"]):
            errors.append(ValidationError(
                game_id, move.ply, "unsupported_stuck_king_claim",
                f"{where}: claims the enemy king is stuck / cannot castle, but it still "
                f"has castling rights ({rights})"))

    return errors


def validate_annotation_text(game_id: str, move: MoveRecord, text: str, where: str,
                             upcoming_sans: list[str] | None = None) -> list[ValidationError]:
    """Run the main-prose checks on ONE annotation text — the hook the v2 repair loop uses
    to validate a freshly composed annotation before accepting it (ANNOTATION_PIPELINE_V2
    §3.4)."""
    return _validate_main_prose(game_id, move, text, where, upcoming_sans or [])


def validate_move(game_id: str, move: MoveRecord,
                  upcoming_sans: list[str] | None = None) -> list[ValidationError]:
    errors: list[ValidationError] = []
    upcoming = upcoming_sans or []
    legal_ucis = set(move.legal_evals.keys())

    # Main annotations, both languages (PRD §12.1: zh is narrated from the same
    # facts and held to the same contract).
    for text, where in ((move.annotation, "annotation"),
                        (move.annotation_zh, "annotation_zh")):
        if text:
            errors.extend(_validate_main_prose(game_id, move, text, where, upcoming))

    # Alternative-move notes (both languages): move-mention rule, spoilers, and
    # material claims backed by a capture in THAT move's line (TECH_SPEC §5).
    for alts, label in ((move.alt_annotations, "alt note"),
                        (move.alt_annotations_zh, "zh alt note")):
        for alt_uci, prose in (alts or {}).items():
            if not prose:
                continue
            errors.extend(_check_mentioned_moves(prose, move.fen_before, legal_ucis, game_id, move.ply))
            errors.extend(check_future_guess_spoilers(
                prose, upcoming, game_id, move.ply, f"{label} for '{alt_uci}'"))
            if _contains_any(prose, MATERIAL_WORDS):
                refutation = (move.legal_evals.get(alt_uci) or {}).get("refutation_pv", [])
                if not line_has_capture(move.fen_before, alt_uci, refutation):
                    errors.append(ValidationError(
                        game_id, move.ply, "unsupported_material_claim",
                        f"{label} for '{alt_uci}' claims material change, but its line has no capture",
                    ))

    return errors


def _move_san(move: MoveRecord) -> str:
    try:
        return chess.Board(move.fen_before).san(chess.Move.from_uci(move.uci))
    except (ValueError, AssertionError):
        return move.san or move.uci


def validate_game(game: GameRecord) -> list[ValidationError]:
    errors: list[ValidationError] = []
    final_mate: tuple[int, facts.MatePattern] | None = None
    guess_points = [m for m in game.moves if m.is_guess_point]
    for move in game.moves:
        if move.is_guess_point:
            upcoming = [_move_san(m) for m in guess_points if m.ply > move.ply]
            errors.extend(validate_move(game.id, move, upcoming_sans=upcoming))
            pattern = facts.mate_pattern(move.fen_before, move.uci)
            if pattern.is_mate:
                final_mate = (move.ply, pattern)
    # The game TITLE often describes the finish ("...Mate") — hold it to the same
    # mate-pattern truth (the original C2 error was in the title).
    if game.title and final_mate:
        ply, pattern = final_mate
        errors.extend(check_mate_claims(game.title, pattern, game.id, ply))
    return errors
