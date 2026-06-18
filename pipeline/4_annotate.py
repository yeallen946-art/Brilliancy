"""Pipeline stage 4 — generate grounded annotations via Claude (TECH_SPEC §5, PRD §6).

Default provider is the Anthropic SDK (needs ANTHROPIC_API_KEY) using the Batch API (50%
cost, TECH_SPEC §5 cost note); `--no-batch` is synchronous client.messages.parse per request.
`--provider openrouter` uses OpenRouter (OpenAI-compatible, synchronous, no batch) — reads
OPENROUTER_API_KEY / OPENROUTER_MODEL from a gitignored pipeline/.env. Set ANNOTATE_PROVIDER
in that .env to make a provider the default without passing --provider. Same prompts, schemas,
and grounding for every provider. Only annotates guess points that have engine data (run
3_analyze first). Output must pass 5_validate.py before 7_build.

Usage:
    python 4_annotate.py --game-id <id>
    python 4_annotate.py --game-id <id> --no-batch
    python 4_annotate.py --game-id <id> --provider openrouter --model anthropic/claude-opus-4-8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

import store
from annotate import (
    MODEL,
    OPENROUTER_URL,
    GameIntroResult,
    MoveAnnotationResult,
    apply_move_annotation,
    build_intro_prompt,
    build_move_prompt,
    load_dotenv,
    openrouter_request_body,
    strict_json_schema,
    system_prompt,
)

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


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


def _openrouter_chat(model: str, system: str, user_content: str, schema_model,
                     *, api_key: str, max_tokens: int):
    """One synchronous OpenRouter chat-completions call -> validated `schema_model`.
    Stdlib HTTP only (no openai dependency). Raises on transport / schema errors."""
    body = openrouter_request_body(model, system, user_content, schema_model, max_tokens)
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # OpenRouter attribution headers (optional, recommended).
            "HTTP-Referer": "https://github.com/brilliancy/pipeline",
            "X-Title": "Brilliancy annotate",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"OpenRouter HTTP {exc.code}: {detail}") from exc
    content = payload["choices"][0]["message"]["content"]
    return schema_model.model_validate_json(content)


def run_openrouter(game, lang: str, model: str, api_key: str) -> None:
    """OpenRouter path — synchronous, same prompts/schemas as the Anthropic path."""
    intro = _openrouter_chat(model, system_prompt(lang), build_intro_prompt(game, lang),
                             GameIntroResult, api_key=api_key, max_tokens=512)
    if lang == "zh":
        game.narrative_intro_zh = intro.narrative_intro
    else:
        game.narrative_intro = intro.narrative_intro

    for move in _guess_points_with_evals(game):
        res = _openrouter_chat(model, system_prompt(lang), build_move_prompt(game, move, lang),
                               MoveAnnotationResult, api_key=api_key, max_tokens=1024)
        apply_move_annotation(move, res, lang)
        print(f"  annotated ply {move.ply} ({move.san}) [{lang}] via openrouter:{model}")


def main() -> int:
    # Load pipeline/.env (gitignored) FIRST so ANNOTATE_PROVIDER / OPENROUTER_* are visible
    # to the argument defaults below and the provider branch. Real env vars win over .env.
    load_dotenv(ENV_PATH)

    parser = argparse.ArgumentParser(description="Generate grounded annotations (stage 4).")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--work-dir", default=store.WORK_DIR)
    parser.add_argument("--no-batch", action="store_true", help="synchronous, no 50%% discount")
    # Default provider is ANNOTATE_PROVIDER from .env (else anthropic) — set it once in
    # pipeline/.env to lock OpenRouter in without passing --provider every run.
    parser.add_argument("--provider", choices=["anthropic", "openrouter"],
                        default=os.environ.get("ANNOTATE_PROVIDER", "anthropic"),
                        help="anthropic SDK or OpenRouter (sync, no batch); default from "
                             "ANNOTATE_PROVIDER in .env, else anthropic")
    parser.add_argument("--model", help="override the model id (OpenRouter slug, "
                                        "e.g. anthropic/claude-opus-4-8; or set OPENROUTER_MODEL)")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="narration language (PRD 12.1: zh narrates the same facts)")
    args = parser.parse_args()

    game = store.load_game(args.game_id, args.work_dir)
    points = _guess_points_with_evals(game)
    if not points:
        print("No analyzed guess points — run 3_analyze.py first.", file=sys.stderr)
        return 1

    if args.provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print(f"OPENROUTER_API_KEY not set — put it in {ENV_PATH} (gitignored) or the "
                  "environment.", file=sys.stderr)
            return 1
        model = args.model or os.environ.get("OPENROUTER_MODEL") or f"anthropic/{MODEL}"
        if args.no_batch:
            print("note: --no-batch is implied for OpenRouter (no batch endpoint).", file=sys.stderr)
        print(f"Annotating {game.id}: {len(points)} guess point(s) + intro "
              f"(lang={args.lang}, openrouter:{model}).")
        run_openrouter(game, args.lang, model, api_key)
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY not set — stage 4 needs it (or use --provider openrouter).",
                  file=sys.stderr)
            return 1
        import anthropic

        client = anthropic.Anthropic()
        if args.model:
            print(f"note: --model is ignored for the anthropic provider (uses {MODEL}).",
                  file=sys.stderr)
        print(f"Annotating {game.id}: {len(points)} guess point(s) + intro (lang={args.lang}).")
        (run_no_batch if args.no_batch else run_batch)(client, game, args.lang)

    store.save_game(game, args.work_dir)
    print(f"Saved annotations to {store.game_path(game.id, args.work_dir)}.")
    print("Next: python 5_validate.py --game-id", game.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
