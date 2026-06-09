# Pipeline runbook — producing content (M2 "先精做 5 局")

Step-by-step for the part of M2 that needs a human + external deps: turning curated PGNs
into a shipped `content.sqlite`. The pipeline code is done and tested; this is the operating
procedure. Run everything from `pipeline/` with the venv active (see README for setup).

## Prerequisites (one-time, on a machine that has them)

- **Stockfish** on PATH — `brew install stockfish` (macOS). Needed by stage 3.
- **`ANTHROPIC_API_KEY`** in the environment — Claude Max / API. Needed by stage 4.
  - `export ANTHROPIC_API_KEY=sk-ant-...`

Without these, the pipeline still runs ingest → curate → validate → build, but guess points
stay unmarked and there are no annotations (fine for a dry run; not shippable content).

## The flow

```bash
# 1. Drop PGNs into content/pgn/ (the MVP candidate pool). Public-domain classics +
#    Lichess elite exports both work. Then parse them into the work store:
python 1_ingest.py

# 2. Rank candidates and write a starter selection of the top N (then EDIT it by hand —
#    this is the taste call, you + son pick the games):
python 2_curate.py --select-top 5
#    -> writes content/curation/selected.txt. Open it, keep the 5 you want, delete the rest.

# 3. Engine analysis + LLM annotation, ONLY for the selected games (cost control).
#    The orchestrator auto-detects Stockfish + the API key and runs the gated stages:
python run_pipeline.py
#    (or run per game manually:)
#      python 3_analyze.py  --game-id <id>     # marks guess points, fills legal_evals
#      python 4_annotate.py --game-id <id>     # grounded annotations via Batch API

# 4. Correctness gate — must pass before review/build:
python 5_validate.py --all

# 5. Human review (son, ~1700): generate the board+annotation pages, eyeball usefulness,
#    then record decisions:
python 6_review.py --all                       # writes content/review/<id>.html
python 6_review.py --approve <id>              # for each good game
python 6_review.py --reject  <id>              # for ones that need rework

# 6. Build the shippable DB from approved + selected games:
python 7_build.py
#    -> content/content.sqlite (+ content/daily/*.json)
```

`run_pipeline.py` does steps 1, 3, 4, 5, 6 in sequence (respecting `selected.txt`); steps 2
and 5 are the human-judgment steps. For a tiny run, `4_annotate.py --no-batch` is simpler
(synchronous, no 50% batch discount).

## Acceptance (ROADMAP M2)

5 games pass both gates — `5_validate.py` (correctness) and son's review (usefulness, "有用、
像人话"). If three rounds of prompt tuning still leave annotations hollow or wrong, that's the
M2 kill-criterion: reconsider the annotation feature (ROADMAP).

## Cost (rough)

Annotation uses `claude-opus-4-8` via the Batch API (50% off, `$2.50 / $12.50` per 1M
in/out). ~5 games × ~20 guess points ≈ ~105 requests, short prompts and outputs:
**well under $1 for 5 games, ~a few dollars for all 50** — within Claude Max / Batch budget
(TECH_SPEC §5 cost note). Only failed items need regenerating.

## What's tracked vs regenerable

- **Tracked** (git): `content/pgn/*.pgn` (sources), `content/curation/selected.txt` (your pick).
- **Regenerable / git-ignored**: `content/work/` (per-game JSON), `candidates.csv`,
  `content/review/*.html`, `content/content.sqlite`, `content/daily/*.json`.
  Review decisions currently live in the work store; re-running stages 1–4 preserves them
  only if you don't wipe `content/work/`. (A tracked decisions file is a future refinement.)
