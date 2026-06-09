"""Run the whole content pipeline end to end (TECH_SPEC §5).

Convenience orchestrator over the numbered stage CLIs. Stages that need external deps are
auto-skipped (and logged) when those deps are absent:
  - 3_analyze  needs Stockfish on PATH
  - 4_annotate needs ANTHROPIC_API_KEY

So on a machine with neither, this runs ingest → curate → validate → build (no engine evals
or annotations). On Jerry's machine with both, it runs the full chain per game.

Usage:
    python run_pipeline.py            # auto-detect deps, build approved games
    python run_pipeline.py --all      # build regardless of review status (dev)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

import store

HERE = os.path.dirname(os.path.abspath(__file__))


def plan_stages(*, has_engine: bool, has_key: bool) -> list[str]:
    """Ordered stage names to run given available deps. Pure — unit-tested.
    Annotate is included only with BOTH an engine (for evals) and an API key."""
    stages = ["ingest", "curate"]
    if has_engine:
        stages.append("analyze")
    if has_engine and has_key:
        stages.append("annotate")
    stages += ["validate", "build"]
    return stages


def _run(argv: list[str]) -> None:
    print(f"\n$ {' '.join(argv)}")
    subprocess.run([sys.executable, *argv], cwd=HERE, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full content pipeline.")
    parser.add_argument("--all", action="store_true", help="build non-approved games too")
    parser.add_argument("--engine", default="stockfish")
    args = parser.parse_args()

    has_engine = shutil.which(args.engine) is not None
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    stages = plan_stages(has_engine=has_engine, has_key=has_key)

    print("Pipeline plan:", " -> ".join(stages))
    if not has_engine:
        print("  (Stockfish not found - skipping 3_analyze; guess points will be unmarked)")
    if not has_key:
        print("  (ANTHROPIC_API_KEY not set - skipping 4_annotate)")

    _run(["1_ingest.py"])
    _run(["2_curate.py"])

    if "analyze" in stages or "annotate" in stages:
        # Only spend engine/API budget on the human-selected games, if a selection exists.
        selected = store.load_selected()
        games = store.load_all_games()
        if selected is not None:
            games = [g for g in games if g.id in selected]
            print(f"\nSelection active: analyzing/annotating {len(games)} selected game(s).")
        for game in games:
            if "analyze" in stages:
                _run(["3_analyze.py", "--game-id", game.id, "--engine", args.engine])
            if "annotate" in stages:
                _run(["4_annotate.py", "--game-id", game.id])

    # Validation gates the build; tolerate a non-zero exit so we can report it.
    print("\n$ 5_validate.py --all")
    validate = subprocess.run([sys.executable, "5_validate.py", "--all"], cwd=HERE)
    if validate.returncode != 0:
        print("Validation failed — fix annotations before building.", file=sys.stderr)
        return 1

    _run(["7_build.py", *(["--all"] if args.all else [])])
    print("\nPipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
