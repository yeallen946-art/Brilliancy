# pipeline — Brilliancy content pipeline

Python 3.12 content pipeline (TECH_SPEC §5). Cross-platform; fully developable on Windows
(Stockfish + Anthropic API run there). Each stage is idempotent and individually runnable.

## Setup (one time)

```bash
cd pipeline
python -m venv .venv
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

## Stages (full set lands M2)

| Stage | File | Status |
|---|---|---|
| 1 ingest   | `1_ingest.py`   | M2 |
| 2 curate   | `2_curate.py`   | M2 |
| 3 analyze  | `3_analyze.py`  | M0: `--fen` single position · M2: `--game-id` full game |
| 4 annotate | `4_annotate.py` | M2 (Claude API; needs `ANTHROPIC_API_KEY`) |
| 5 validate | `5_validate.py` | M2 |
| 6 review   | `6_review.py`   | M2 |
| 7 build    | `7_build.py`    | M2 |

Hard rule: annotations are **only** produced by `4_annotate.py`, grounded in Stockfish
lines, and must pass `5_validate.py` before shipping (CLAUDE.md / AGENTS.md).
