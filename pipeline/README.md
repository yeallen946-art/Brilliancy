# pipeline — Brilliancy content pipeline

Python 3.12 content pipeline (TECH_SPEC §5). Cross-platform; fully developable on Windows
(Stockfish + Anthropic API run there). Each stage is idempotent and individually runnable.

## Setup (one time)

```bash
cd pipeline
# Use Python 3.12 (TECH_SPEC §2). The bare `python` may default to a newer version;
# pin it explicitly so the env matches across machines:
py -3.12 -m venv .venv        # Windows (py launcher)
# python3.12 -m venv .venv    # macOS/Linux
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

You also need **Stockfish** on PATH (`stockfish` command):
- Windows: download from stockfishchess.org, add the folder to PATH (or pass `--engine <path>`).
- macOS: `brew install stockfish`.

## M0 smoke test — analyze one position

```bash
python 3_analyze.py --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
```

Prints the top-5 engine moves (mover-relative cp / mate). This confirms the
venv + Stockfish loop works — the M0 pipeline acceptance criterion.

## Tests

```bash
pytest          # engine-free helper tests (no Stockfish binary needed)
```

## Data flow

PGN → `1_ingest` → work store (`content/work/<id>.json`) → `2_curate` (rank) → human pick
→ `3_analyze` (mark guess points + fill `legal_evals`) → `4_annotate` (prose) →
`5_validate` (gate) → `6_review` (human approve) → `7_build` → `content.sqlite` + daily JSON.

The work store + `content.sqlite` + `daily/*.json` + `candidates.csv` are regenerable and
git-ignored; PGN sources, the curation `selected.txt`, and review state are tracked.

## Stages

| Stage | File | Status |
|---|---|---|
| 1 ingest   | `1_ingest.py`   | ✅ done + tested |
| 2 curate   | `2_curate.py`   | ✅ done + tested (ranks candidates → `candidates.csv`) |
| 3 analyze  | `3_analyze.py`  | ✅ `--fen` · ✅ `--game-id` guess-point selection (tested); eval fill needs **Stockfish** |
| 4 annotate | `4_annotate.py` | ✅ grounded prompt + schema + apply (tested); Batch API call needs `ANTHROPIC_API_KEY` |
| 5 validate | `5_validate.py` | ✅ rules + known-bad tests |
| 6 review   | `6_review.py`   | ✅ review HTML (board + annotation) + approve/reject (tested) |
| 7 build    | `7_build.py`    | ✅ done + tested (sqlite + daily JSON) |

Engine-independent logic lives in importable modules (`ingest`, `curate`, `guesspoints`,
`validate`, `build`, `store`); the numbered files are thin CLIs. Run order example:

```bash
python 1_ingest.py
python 2_curate.py
python 3_analyze.py --game-id <id>   # needs stockfish on PATH
python 4_annotate.py --game-id <id>  # needs ANTHROPIC_API_KEY (stage not built yet)
python 5_validate.py --all
python 7_build.py
```

Hard rule: annotations are **only** produced by `4_annotate.py`, grounded in Stockfish
lines, and must pass `5_validate.py` before shipping (CLAUDE.md / AGENTS.md).
