# CLAUDE.md — Brilliancy

Instructions for Claude Code working in this repo.

## What this project is

iOS chess training app: the user replays famous master games and guesses the master's next move; scoring is engine-based; pre-generated AI annotations explain why the master's move works and why common wrong guesses fail. Freemium: free daily challenge, subscription unlocks the training library. Solo-developer side project; optimize for shipping, not for architecture awards.

**Read before any product/feature decision:** `PRD.md` (product source of truth, Chinese). **Read before any implementation decision:** `TECH_SPEC.md`. **Current milestone and acceptance criteria:** `ROADMAP.md`. If code and spec conflict, flag it — don't silently pick one.

## Repo layout

```
App/        # Xcode project, SwiftUI app (see TECH_SPEC §3 for module map)
pipeline/   # Python content pipeline (see TECH_SPEC §5)
content/    # PGN sources, curation lists, review state, built artifacts (gitignored: *.sqlite)
docs/       # PRD.md, TECH_SPEC.md, ROADMAP.md live at repo root or here
```

## Commands

```bash
# iOS (run from App/). The .xcodeproj is generated from project.yml, not committed.
# On macOS, regenerate after pulling if files or project.yml changed:
xcodegen generate                        # reads project.yml -> Brilliancy.xcodeproj
xcodebuild -scheme Brilliancy -destination 'platform=iOS Simulator,name=iPhone 16' build
xcodebuild -scheme Brilliancy -destination 'platform=iOS Simulator,name=iPhone 16' test
# From Windows (no Xcode): edit Swift files + project.yml only; never hand-edit .xcodeproj

# Pipeline (run from pipeline/, venv at pipeline/.venv)
python 1_ingest.py --source content/pgn/
python 3_analyze.py --game-id <id>     # needs stockfish on PATH
python 4_annotate.py --game-id <id>    # needs ANTHROPIC_API_KEY
python 5_validate.py --all             # must pass before 7_build.py
python 7_build.py                      # emits content/content.sqlite + content/daily/*.json
pytest                                 # pipeline tests
```

## Conventions

- Swift: SwiftUI + Observation (`@Observable`), iOS 17+. No UIKit unless unavoidable; justify in PR. No new SPM dependencies without a one-line justification (current allowlist: ChessKit, GRDB, TelemetryDeck).
- Scoring and rating math live in `Core/Scoring/` as pure functions with table-driven unit tests. Never inline scoring constants elsewhere — they're in one config struct (`ScoringConfig`).
- All premium gating goes through `EntitlementStore.isPremium`. Never check StoreKit transactions directly in feature code.
- User-facing strings: English only (V1), sentence case, coach tone — encouraging, never mocking a wrong guess (PRD §5).
- Python: 3.12, type hints, each pipeline stage idempotent and runnable per-game-id.
- Commits: conventional (`feat:`, `fix:`, `pipeline:`, `content:`). Small PRs per milestone task.

## Hard rules (do not violate)

1. **Never generate chess commentary freestyle.** All annotations come from `4_annotate.py`, whose prompt grounds every claim in supplied Stockfish lines. If asked to "just write" an annotation in the app or by hand, refuse and route through the pipeline. `5_validate.py` must pass before content ships.
2. **No on-device engine, no runtime LLM calls.** Everything is precomputed. The app never calls the Anthropic API.
3. **No backend.** Daily challenges are static JSON on CDN. If a feature seems to need a server, stop and discuss — it's probably out of scope (TECH_SPEC §10).
4. **Don't touch pricing/product tiers in code without PRD §7 changing first.**
5. Chess correctness is sacred: any board/move-gen change requires the SAN/FEN round-trip test suite to pass (perft tests if we ever write our own move gen).

## Testing bar

Before marking any milestone task done: `xcodebuild test` green, `pytest` green (if pipeline touched), and the feature demoed in simulator. IAP changes additionally need a sandbox-account manual test noted in the PR.

## Context for judgment calls

- Target user is an 800–2000 improver; when unsure how much chess detail to surface, less depth + clearer plan-language wins.
- The seed reviewer (1700 USCF) reviews annotation *usefulness*; the validator reviews *correctness*. Both gates are mandatory for content.
- Ship-fast bias: when a choice is reversible and not on the hard-rules list, pick the simpler option and note it in the PR rather than asking.
