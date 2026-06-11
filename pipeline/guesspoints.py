"""Guess-point selection, tagging, and difficulty (TECH_SPEC §3.1/§3.3/§5 stage 3).

The WHICH-plies decision is engine-independent and unit-tested here. Eval-derived bits
(difficulty from the best/second gap) take engine output and are computed in a small pure
function so they're testable with synthetic evals. The actual Stockfish run lives in
3_analyze.py behind the engine boundary.
"""

from __future__ import annotations

import json
import os

import store
from store import GameRecord, MoveRecord

# Skip opening book: the first ~8 full moves (16 plies) unless a novelty (TECH_SPEC §5).
BOOK_PLIES = 16
TARGET_MIN_POINTS = 15
TARGET_MAX_POINTS = 30

# "Highlight reel" pacing (PRD §5 school-2 decision, 2026-06-11): a guess point whose
# master move is this far ahead of the second-best CP move is an only-move — no fun to
# guess (the Opera-game Rd1 case: 2.5 pawns clear, difficulty 788). Mating moves are
# exempt: forced mates ARE the drama (Qd8+!!).
OBVIOUS_GAP_CP = 250


def _is_capture(move: MoveRecord) -> bool:
    return "x" in move.san


def _target_square(uci: str) -> str:
    return uci[2:4] if len(uci) >= 4 else ""


def is_forced_recapture(moves: list[MoveRecord], index: int) -> bool:
    """A capture that takes back on the very square just captured on — a near-forced reply
    we don't ask the user to "guess". Engine-independent heuristic (refined by eval later)."""
    if index == 0:
        return False
    prev, cur = moves[index - 1], moves[index]
    return (
        _is_capture(prev)
        and _is_capture(cur)
        and _target_square(prev.uci) == _target_square(cur.uci)
    )


def candidate_guess_plies(
    game: GameRecord,
    hero_color: str | None = None,
    *,
    book_plies: int = BOOK_PLIES,
    max_points: int = TARGET_MAX_POINTS,
) -> list[int]:
    """Plies (the hero's moves) eligible to be guess points, capped at max_points by
    even downsampling. Skips book moves and forced recaptures."""
    hero = hero_color or game.hero_color
    candidates: list[int] = []
    for i, move in enumerate(game.moves):
        if hero is not None and move.mover != hero:
            continue
        if move.ply <= book_plies:
            continue
        if is_forced_recapture(game.moves, i):
            continue
        candidates.append(move.ply)

    if len(candidates) <= max_points:
        return candidates
    return _downsample_even(candidates, max_points)


def _downsample_even(items: list[int], count: int) -> list[int]:
    """Keep `count` items spread evenly across the list (preserves order)."""
    if count <= 0:
        return []
    n = len(items)
    step = n / count
    picked = [items[min(int(i * step), n - 1)] for i in range(count)]
    # de-dup while preserving order (rounding can collide on short lists)
    seen: set[int] = set()
    result = []
    for p in picked:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


# ------------------------------------------------- school-2 refinement (PRD §5)
# Auto-prune only-moves, then let a tracked per-game override file have the last
# word — the human curates the highlight reel, the machine proposes it.

OVERRIDES_FILE = os.path.join(store.CONTENT_DIR, "curation", "guesspoint_overrides.json")


def is_obvious_point(move: MoveRecord) -> bool:
    """True when the master move is an only-move by CP gap (>= OBVIOUS_GAP_CP ahead
    of the second-best). Mating master moves are never obvious-pruned: forced mates
    are the drama the product exists for."""
    entry = move.legal_evals.get(move.uci) or {}
    if entry.get("mate") is not None:
        return False
    cps = sorted(
        (e["cp"] for e in move.legal_evals.values() if e.get("cp") is not None),
        reverse=True,
    )
    if len(cps) < 2:
        return False
    return cps[0] - cps[1] >= OBVIOUS_GAP_CP


def load_overrides(path: str = OVERRIDES_FILE) -> dict:
    """{game_id: {"include": [ply...], "exclude": [ply...]}} — tracked human picks."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def apply_refinement(game: GameRecord, overrides: dict | None = None) -> dict:
    """Refine is_guess_point flags IN MEMORY (callers: 7_build / 6_review / publish —
    the work store on disk is never mutated, so this is idempotent and reversible):
    auto-drop obvious only-moves, then apply the tracked per-game overrides, which
    always win. `include` can only resurrect plies that have engine data (a ply with
    no legal_evals needs a 3_analyze re-run first). Returns {"dropped": [...],
    "added": [...]} for logging."""
    per_game = (overrides if overrides is not None else load_overrides()).get(game.id, {})
    include = set(per_game.get("include", []))
    exclude = set(per_game.get("exclude", []))
    dropped: list[int] = []
    added: list[int] = []
    for move in game.moves:
        if move.is_guess_point and move.ply not in include \
                and (move.ply in exclude or is_obvious_point(move)):
            move.is_guess_point = False
            dropped.append(move.ply)
        elif not move.is_guess_point and move.ply in include and move.legal_evals:
            move.is_guess_point = True
            added.append(move.ply)
    return {"dropped": dropped, "added": added}


def difficulty_from_evals(
    legal_evals: dict,
    *,
    base: float = 1200.0,
    span: float = 600.0,
) -> float:
    """Estimate difficulty from move-quality spread (TECH_SPEC §3.3).

    A large gap between the best and second-best move => the move is "obvious"
    (only-move) => EASIER => lower rating. A small gap => many comparable moves =>
    harder to find THE one => higher rating. Returns ~ base ± span.
    """
    cps = sorted(
        (e["cp"] for e in legal_evals.values() if e.get("cp") is not None),
        reverse=True,
    )
    if len(cps) < 2:
        return base
    gap = cps[0] - cps[1]  # >= 0
    # Map gap 0cp -> base+span (hard), >=300cp -> base-span (easy). Linear, clamped.
    obviousness = min(1.0, max(0.0, gap / 300.0))
    return base + span * (1.0 - 2.0 * obviousness)


def tag_for_move(move: MoveRecord) -> list[str]:
    """Placeholder tagging (TECH_SPEC §3.3 tags). Real motif-aware tagging is a later
    refinement once engine motifs exist; this is the engine-independent first pass."""
    san = move.san
    if "#" in san or "+" in san or _is_capture(move):
        return ["tactical"]
    if move.ply >= 60:
        return ["endgame"]
    return ["positional"]
