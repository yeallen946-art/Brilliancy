"""Apply agent-preview annotations into the work store (one-off; see RUNBOOK / chat).

NOT the production path. Production annotations come from 4_annotate.py (CLAUDE.md hard
rule #1). This applies a hand-prepared preview_annotations.json so a no-key quality preview
can be validated + built. Every annotation here was generated under the same grounding
constraints (engine lines only) and must still pass 5_validate.

JSON shape:
  { "<game_id>": { "narrative_intro": "...",
                   "moves": { "<ply>": {"annotation": "...",
                                        "alt_annotations": {"<uci>": "..."}} } } }
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store


def main(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    for game_id, payload in data.items():
        game = store.load_game(game_id)
        if "narrative_intro" in payload:
            game.narrative_intro = payload["narrative_intro"]
        if "narrative_intro_zh" in payload:
            game.narrative_intro_zh = payload["narrative_intro_zh"]
        if "title_zh" in payload:
            game.title_zh = payload["title_zh"]
        by_ply = {m.ply: m for m in game.moves}
        applied = 0
        for ply_str, ann in payload.get("moves", {}).items():
            move = by_ply[int(ply_str)]
            if "annotation" in ann:
                move.annotation = ann["annotation"]
                move.alt_annotations = ann.get("alt_annotations", {})
            if "annotation_zh" in ann:
                move.annotation_zh = ann["annotation_zh"]
                move.alt_annotations_zh = ann.get("alt_annotations_zh", {})
            applied += 1
        store.save_game(game)
        print(f"{game_id}: applied {applied} annotation(s) + intro")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
