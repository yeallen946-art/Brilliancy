"""Pipeline stage 4 — generate grounded annotations via Claude (TECH_SPEC §5, PRD §6).

Needs ANTHROPIC_API_KEY. Uses the Batch API by default (50% cost, TECH_SPEC §5 cost note);
`--no-batch` uses synchronous client.messages.parse per request for small runs / debugging.
Only annotates guess points that have engine data (run 3_analyze first). Output must pass
5_validate.py before 7_build.

Usage:
    python 4_annotate.py --game-id <id>
    python 4_annotate.py --game-id <id> --no-batch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import store
from annotate import (
    MODEL,
    GameIntroResult,
    MoveAnnotationResult,
    apply_move_annotation,
    build_intro_prompt,
    build_move_prompt,
    strict_json_schema,
    system_prompt,
)


def _first_text(message) -> str:
    return next((b.text for b in message.content if b.type == "text"), "")


def _output_config(model_cls) -> dict:
    return {"format": {"type": "json_schema", "schema": strict_json_schema(model_cls)}}


def _guess_points_with_evals(game) -> list:
    return [m for m in game.moves if m.is_guess_point and m.legal_evals]


def run_no_batch(client, game, lang: str = "en") -> None:
    """Synchronous path — simplest, no 50% discount. Good for 1-5 games / debugging."""
    intro = client.messages.parse(
        model=MODEL, max_tokens=512, system=system_prompt(lang),
        messages=[{"role": "user", "content": build_intro_prompt(game, lang)}],
        output_format=GameIntroResult,
    )
    if lang == "zh":
        game.narrative_intro_zh = intro.parsed_output.narrative_intro
    else:
        game.narrative_intro = intro.parsed_output.narrative_intro

    for move in _guess_points_with_evals(game):
        resp = client.messages.parse(
            model=MODEL, max_tokens=1024, system=system_prompt(lang),
            messages=[{"role": "user", "content": build_move_prompt(game, move, lang)}],
            output_format=MoveAnnotationResult,
        )
        apply_move_annotation(move, resp.parsed_output, lang)
        print(f"  annotated ply {move.ply} ({move.san}) [{lang}]")


def run_batch(client, game, lang: str = "en") -> None:
    """Batch API path (default) — one batch per game (intro + each guess point)."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests = [Request(
        custom_id="intro",
        params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=512, system=system_prompt(lang),
            messages=[{"role": "user", "content": build_intro_prompt(game, lang)}],
            output_config=_output_config(GameIntroResult),
        ),
    )]
    points = _guess_points_with_evals(game)
    for move in points:
        requests.append(Request(
            custom_id=f"ply-{move.ply}",
            params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=1024, system=system_prompt(lang),
                messages=[{"role": "user", "content": build_move_prompt(game, move, lang)}],
                output_config=_output_config(MoveAnnotationResult),
            ),
        ))

    batch = client.messages.batches.create(requests=requests)
    print(f"  submitted batch {batch.id} ({len(requests)} requests, lang={lang}); polling...")
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        time.sleep(30)

    by_ply = {m.ply: m for m in points}
    for result in client.messages.batches.results(batch.id):
        if result.result.type != "succeeded":
            print(f"  ! {result.custom_id}: {result.result.type}", file=sys.stderr)
            continue
        text = _first_text(result.result.message)
        if result.custom_id == "intro":
            intro = GameIntroResult.model_validate_json(text).narrative_intro
            if lang == "zh":
                game.narrative_intro_zh = intro
            else:
                game.narrative_intro = intro
        else:
            ply = int(result.custom_id.split("-")[1])
            apply_move_annotation(by_ply[ply], MoveAnnotationResult.model_validate_json(text), lang)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate grounded annotations (stage 4).")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    parser.add_argument("--no-batch", action="store_true", help="synchronous, no 50%% discount")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="narration language (PRD 12.1: zh narrates the same facts)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — stage 4 needs it.", file=sys.stderr)
        return 1

    import anthropic

    game = store.load_game(args.game_id, args.work_dir)
    points = _guess_points_with_evals(game)
    if not points:
        print("No analyzed guess points — run 3_analyze.py first.", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()
    print(f"Annotating {game.id}: {len(points)} guess point(s) + intro (lang={args.lang}).")
    (run_no_batch if args.no_batch else run_batch)(client, game, args.lang)

    store.save_game(game, args.work_dir)
    print(f"Saved annotations to {store.game_path(game.id, args.work_dir)}.")
    print("Next: python 5_validate.py --game-id", game.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
