"""Shared work-store schema for the content pipeline (TECH_SPEC §4/§5).

Stages are idempotent and individually runnable. Between stages, each game lives as a
JSON file under the work dir (default content/work/<id>.json) — regenerable, git-ignored.
Curation lists and review state (small, human decisions) live elsewhere under content/
and ARE tracked. `7_build.py` turns approved games into content.sqlite + daily JSON.

The record shape mirrors content.sqlite (TECH_SPEC §4) so the build step is a thin map.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

# Default locations (relative to repo root). Overridable per CLI.
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CONTENT_DIR = os.path.join(REPO_ROOT, "content")
WORK_DIR = os.path.join(CONTENT_DIR, "work")
PGN_DIR = os.path.join(CONTENT_DIR, "pgn")
CURATION_DIR = os.path.join(CONTENT_DIR, "curation")

REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"


@dataclass
class MoveRecord:
    ply: int                 # 1-based half-move
    san: str
    uci: str
    fen_before: str
    mover: str               # "white" | "black"
    is_guess_point: bool = False
    difficulty: float = 1200.0
    tags: list[str] = field(default_factory=list)
    eval_cp: int | None = None       # position eval before the move (engine-best), mover POV
    eval_mate: int | None = None
    # uci -> {"cp": int|None, "mate": int|None, "refutation_pv": [uci...], "motif": str}
    legal_evals: dict = field(default_factory=dict)
    annotation: str | None = None             # prose for the master move (stage 4)
    alt_annotations: dict = field(default_factory=dict)  # uci -> prose, interesting moves only
    # Chinese prose (PRD §12.1): narrated from the SAME facts with lang="zh" —
    # never a translation of the English. None/empty until a zh annotate run.
    annotation_zh: str | None = None
    alt_annotations_zh: dict = field(default_factory=dict)


@dataclass
class GameRecord:
    id: str
    white: str
    black: str
    event: str
    site: str
    date: str
    year: int | None
    result: str              # "1-0" | "0-1" | "1/2-1/2" | "*"
    eco: str
    hero_color: str | None   # "white" | "black" | None
    title: str | None
    narrative_intro: str | None
    pack_id: str | None
    ply_count: int
    source_hash: str         # sha1 of the uci move sequence, for dedupe
    review_status: str
    # Chinese narrative fields (PRD §12.1), filled by a zh annotate run.
    title_zh: str | None = None
    narrative_intro_zh: str | None = None
    moves: list[MoveRecord] = field(default_factory=list)

    @property
    def guess_points(self) -> list[MoveRecord]:
        return [m for m in self.moves if m.is_guess_point]


# ---------------------------------------------------------------- (de)serialization

def game_to_dict(game: GameRecord) -> dict:
    return asdict(game)


def game_from_dict(data: dict) -> GameRecord:
    moves = [MoveRecord(**m) for m in data.get("moves", [])]
    fields = {k: v for k, v in data.items() if k != "moves"}
    return GameRecord(moves=moves, **fields)


# ---------------------------------------------------------------- work-store IO

def game_path(game_id: str, work_dir: str = WORK_DIR) -> str:
    return os.path.join(work_dir, f"{game_id}.json")


def save_game(game: GameRecord, work_dir: str = WORK_DIR) -> str:
    os.makedirs(work_dir, exist_ok=True)
    path = game_path(game.id, work_dir)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(game_to_dict(game), fh, ensure_ascii=False, indent=2)
    return path


def load_game(game_id: str, work_dir: str = WORK_DIR) -> GameRecord:
    with open(game_path(game_id, work_dir), encoding="utf-8") as fh:
        return game_from_dict(json.load(fh))


def load_all_games(work_dir: str = WORK_DIR) -> list[GameRecord]:
    if not os.path.isdir(work_dir):
        return []
    games = []
    for name in sorted(os.listdir(work_dir)):
        if name.endswith(".json"):
            games.append(load_game(name[:-5], work_dir))
    return games


def existing_source_hashes(work_dir: str = WORK_DIR) -> set[str]:
    return {g.source_hash for g in load_all_games(work_dir)}


# ------------------------------------------------------------- review decisions
# Human approve/reject decisions are the one thing in the work store that can't be
# regenerated — persist them in a TRACKED file so wiping content/work/ doesn't lose them.

DECISIONS_FILE = os.path.join(CONTENT_DIR, "review", "decisions.json")


def load_decisions(path: str = DECISIONS_FILE) -> dict[str, str]:
    """game_id -> review status ('approved'/'rejected'). Empty if no file."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def record_decision(game_id: str, status: str, path: str = DECISIONS_FILE) -> None:
    decisions = load_decisions(path)
    decisions[game_id] = status
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(decisions, fh, indent=2, sort_keys=True)


# ---------------------------------------------------------------- curation selection

SELECTED_FILE = os.path.join(CURATION_DIR, "selected.txt")


def parse_selected(text: str) -> set[str]:
    """Parse a selection list: one game id per line, '#' starts a comment."""
    ids: set[str] = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.add(line)
    return ids


def load_selected(path: str = SELECTED_FILE) -> set[str] | None:
    """The human's curated game ids (TECH_SPEC §5 stage 2). None = no selection (use all)."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return parse_selected(fh.read())
