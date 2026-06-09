"""Stage 2 logic — score candidate games for human curation (TECH_SPEC §5).

Engine-independent heuristics only: this just ranks candidates so Jerry/son can pick the
50 MVP games. The final selection is a human call (ROADMAP M2). Importable; CLI in 2_curate.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from store import GameRecord

# Lowercased last names that signal a famous/instructive player. Extend freely.
FAMOUS_PLAYERS = {
    "fischer", "kasparov", "karpov", "tal", "capablanca", "alekhine", "botvinnik",
    "morphy", "lasker", "carlsen", "anand", "kramnik", "spassky", "petrosian",
    "nimzowitsch", "rubinstein", "smyslov", "korchnoi", "bronstein", "keres",
    "anderssen", "steinitz", "pillsbury", "marshall", "reti", "euwe", "fine",
}


@dataclass
class CandidateScore:
    game_id: str
    score: float
    decisive: bool
    has_famous: bool
    tactic_density: float
    reasonable_length: bool


def _names(game: GameRecord) -> list[str]:
    out = []
    for full in (game.white, game.black):
        base = full.split(",")[0] if "," in full else (full.split()[-1] if full.split() else full)
        out.append(base.lower())
    return out


def tactic_density(game: GameRecord) -> float:
    """Fraction of moves that are captures or checks — a cheap proxy for sharpness."""
    if not game.moves:
        return 0.0
    sharp = sum(1 for m in game.moves if "x" in m.san or "+" in m.san or "#" in m.san)
    return sharp / len(game.moves)


def score_game(game: GameRecord) -> CandidateScore:
    decisive = game.result in ("1-0", "0-1")
    has_famous = any(name in FAMOUS_PLAYERS for name in _names(game))
    density = tactic_density(game)
    reasonable = 30 <= game.ply_count <= 90  # not a miniature, not a marathon

    score = 0.0
    score += 2.0 if decisive else 0.0
    score += 2.0 if has_famous else 0.0
    score += 4.0 * density          # 0..4
    score += 1.0 if reasonable else 0.0

    return CandidateScore(
        game_id=game.id,
        score=round(score, 3),
        decisive=decisive,
        has_famous=has_famous,
        tactic_density=round(density, 3),
        reasonable_length=reasonable,
    )


def rank(games: list[GameRecord]) -> list[CandidateScore]:
    return sorted((score_game(g) for g in games), key=lambda c: c.score, reverse=True)
