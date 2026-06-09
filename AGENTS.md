# AGENTS.md — Brilliancy

Instructions for any coding agent working in this repo (Codex, Claude Code, etc.), regardless of machine. This file is the shared contract; **`CLAUDE.md` is part of it — read CLAUDE.md too and obey its hard rules.** If this file and CLAUDE.md ever disagree, CLAUDE.md's hard rules win.

## Project in one paragraph

iOS chess training app: user replays famous master games and guesses the master's next move; scoring is engine-based; pre-generated AI annotations explain why the master's move works and why common wrong guesses fail. Freemium: free daily challenge, subscription unlocks the training library. Solo-developer side project — optimize for shipping. Product source of truth: `PRD.md` (Chinese). Implementation spec: `TECH_SPEC.md`. Milestones + acceptance: `ROADMAP.md`.

## Who does what (multi-machine setup)

This project is developed by more than one agent on more than one machine. Typical split:

- **Windows / Claude Code** — writes features and the Python pipeline. Cannot build or run the iOS app (no Xcode on Windows). Writes Swift "blind," relying on the spec and tests.
- **macOS / Codex (or Claude Code)** — owns the build/test/debug loop: runs `xcodebuild`, reads compiler and test errors, fixes build breakage, runs the app in the simulator.

macOS/Codex sessions should also read `MACOS_CODEX.md` before running the build loop.

Roles are a convention, not a wall — but stay in your lane unless the other side is clearly blocked. The macOS agent's job is to make the code *actually compile and pass tests*; the Windows agent's job is to make it *do the right thing*. Neither invents chess content (that only comes from the pipeline — see CLAUDE.md hard rule #1).

## New-session startup checklist

Every new agent session starts from the files, not from chat history:

1. Read `AGENTS.md` first, then `CLAUDE.md`; `CLAUDE.md` hard rules win if there is any conflict.
2. For product decisions, read `PRD.md`; for implementation decisions, read `TECH_SPEC.md`; for milestone scope and acceptance, read `ROADMAP.md`.
3. Run `git status --short --branch`, then `git pull --ff-only` before making changes.
4. Commit only source/config/doc changes that belong to the task. Generated build products, DerivedData, local tool downloads, and `.xcodeproj` stay out of git.

## How agents stay in sync (normal git hygiene, nothing exotic)

There is no shared memory between agents. The only shared state is what's committed. Therefore:

1. **Everything is in the files.** Intent lives in code comments, PR descriptions, and these docs — never assume the other agent "knows why." If you make a non-obvious choice, write it down.
2. **One direction at a time.** Default flow: Windows writes feature → push → macOS pulls, builds, fixes compile/test errors → push → Windows pulls before continuing. Don't have two agents editing the same files concurrently.
3. **`git pull` before you start, push when a unit of work is done.** Small, focused commits. Conventional prefixes (`feat:`, `fix:`, `pipeline:`, `content:`, `build:` for build-only fixes by the macOS agent).
4. **Don't fight the other agent's changes.** If you pull and find the build was fixed in a way you didn't expect, understand it before changing it back. If it violates a hard rule or the spec, flag it in a commit message / note rather than silently reverting.
5. **No hand-editing the Xcode project.** The project is generated from `project.yml` by **XcodeGen** (TECH_SPEC §2.1); `.xcodeproj` is git-ignored and never committed. To add a source file, just create the `.swift` in the right folder — XcodeGen globs it in. Structural changes (targets, build settings, capabilities) go in `project.yml`, which any agent can edit from any machine. After pulling on macOS, run `xcodegen generate` before building.

## Cross-platform gotchas (set up once)

- `.gitattributes` forces `* text=auto eol=lf` so line endings don't churn between Windows and macOS.
- Filenames: git is case-sensitive, Windows is not, macOS default is not. Never create two files differing only by case.
- Swift toolchain only exists on the Mac side. The Windows agent must not claim a Swift change "works" — only that it's written; verification happens on macOS.
- The Python pipeline (`pipeline/`) is cross-platform and can be fully developed and tested on Windows (Stockfish + Anthropic API run there).

## The build/test loop (macOS agent)

```bash
# from App/ — regenerate the project first if files/project.yml changed
xcodegen generate
# Destination device must exist in the local Xcode — list with: xcrun simctl list devices available
xcodebuild -scheme Brilliancy -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
xcodebuild -scheme Brilliancy -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

The macOS agent communicates with Xcode **only through `xcodebuild`** (a command-line tool) — it does not drive the Xcode GUI. GUI-only things (visual simulator inspection, real-device debugging, App Store Connect submission) require Jerry, not an agent.

## Definition of done (before marking any ROADMAP task complete)

- `xcodebuild test` green on macOS, `pytest` green if the pipeline was touched.
- Feature demoed in the simulator (macOS agent confirms; if the writing agent can't confirm, the task isn't done until the macOS agent does).
- IAP changes: sandbox-account manual test noted in the commit/PR.
- No CLAUDE.md hard rule violated.

## Non-negotiables (shared with CLAUDE.md)

1. No freestyle chess commentary — annotations only come from `pipeline/4_annotate.py`, grounded in Stockfish lines, and must pass `5_validate.py`.
2. No on-device engine, no runtime LLM calls in the app.
3. No backend — daily challenges are static JSON on CDN.
4. No pricing/tier changes in code without PRD §7 changing first.
5. All premium gating goes through `EntitlementStore.isPremium`.
6. Chess correctness is sacred — board/move-gen changes require the SAN/FEN round-trip tests to pass.

If a build fix would require breaking one of these, stop and leave a note instead — don't trade correctness for a green build.
