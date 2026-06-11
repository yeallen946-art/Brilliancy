"""Pipeline stage 5b — LLM claim-extraction audit (TECH_SPEC §5.2).

Needs ANTHROPIC_API_KEY. Extracts every claim each annotation makes into the closed
taxonomy (audit.py), then verifies each claim deterministically against facts.py.
Required before content ships; 5_validate.py (keyless) remains the hard CI gate.

Usage:
    python 5b_audit.py --all
    python 5b_audit.py --game-id <id>
"""

from __future__ import annotations

import argparse
import os
import sys

import store
from audit import AUDIT_MODEL, AUDIT_SYSTEM_PROMPT, AuditResult, build_audit_prompt, check_claims
from validate import _move_san


def audit_game(client, game) -> int:
    error_count = 0
    guess_points = [m for m in game.moves if m.is_guess_point and m.annotation]
    for move in guess_points:
        upcoming = [_move_san(m) for m in guess_points if m.ply > move.ply]
        resp = client.messages.parse(
            model=AUDIT_MODEL, max_tokens=2048, system=AUDIT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_audit_prompt(move, upcoming)}],
            output_format=AuditResult,
        )
        errors = check_claims(game.id, move, resp.parsed_output.claims, upcoming)
        error_count += len(errors)
        for e in errors:
            print(f"[{e.code}] {e.game_id} ply {e.ply}: {e.message}")
    return error_count


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM claim-extraction audit (stage 5b).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--game-id")
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — stage 5b needs it.", file=sys.stderr)
        return 1

    import anthropic

    games = (
        store.load_all_games(args.work_dir)
        if args.all else [store.load_game(args.game_id, args.work_dir)]
    )
    client = anthropic.Anthropic()

    total = 0
    for game in games:
        total += audit_game(client, game)

    if total:
        print(f"\nFAIL: {total} audited-claim error(s).")
        return 1
    print("\nOK: all extracted claims verified against facts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
