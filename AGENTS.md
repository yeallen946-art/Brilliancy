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
4. Run `gh issue list --state open` and read anything labeled for your side (see
   "Cross-agent handoffs" below). If `gh` isn't authed on this machine, ask Jerry.
5. Commit only source/config/doc changes that belong to the task. Generated build products, DerivedData, local tool downloads, and `.xcodeproj` stay out of git.

## How agents stay in sync (normal git hygiene, nothing exotic)

There is no shared memory between agents. The only shared state is what's committed. Therefore:

1. **Everything is in the files.** Intent lives in code comments, PR descriptions, and these docs — never assume the other agent "knows why." If you make a non-obvious choice, write it down.
2. **One direction at a time.** Default flow: Windows writes feature → push → macOS pulls, builds, fixes compile/test errors → push → Windows pulls before continuing. Don't have two agents editing the same files concurrently.
3. **`git pull` before you start, push when a unit of work is done.** Small, focused commits. Conventional prefixes (`feat:`, `fix:`, `pipeline:`, `content:`, `build:` for build-only fixes by the macOS agent).
4. **Don't fight the other agent's changes.** If you pull and find the build was fixed in a way you didn't expect, understand it before changing it back. If it violates a hard rule or the spec, flag it in a commit message / note rather than silently reverting.
5. **No hand-editing the Xcode project.** The project is generated from `project.yml` by **XcodeGen** (TECH_SPEC §2.1); `.xcodeproj` is git-ignored and never committed. To add a source file, just create the `.swift` in the right folder — XcodeGen globs it in. Structural changes (targets, build settings, capabilities) go in `project.yml`, which any agent can edit from any machine. After pulling on macOS, run `xcodegen generate` before building.

## Cross-agent handoffs: GitHub Issues (not files in the repo)

Handoffs between agents go through **GitHub Issues** (`gh` CLI), NOT through a handoff
file in the working tree — repo files get concurrent-write conflicts (we've had real
truncation/lock incidents); issues are server-side, atomic, and stateful.

**Protocol:**

1. **Startup (both agents):** after `git pull`, run `gh issue list --state open` and read
   anything labeled for your side before starting work.
2. **Labels route work:** `needs-mac-verify` = Windows wrote it blind, macOS must
   build/test/eyeball it. `needs-windows-fix` = macOS found a logic/feature problem that
   Windows owns. `blocked-on-human` = needs Jerry (keys, accounts, taste calls).
3. **Open an issue when you hand off** — one issue per verifiable unit, with: the commit
   hash, what to check, and the expected result. Don't batch unrelated items.
4. **Close the loop in the issue, not in a new file:** the verifying agent comments the
   actual result (pass/fail + errors verbatim) and closes the issue if green, or relabels
   it back (`needs-windows-fix`) if not. Reference commits with the hash so they link.
5. **Commit messages still carry the "why"** (point 1 above stands); issues carry the
   *work routing*. An issue is not a substitute for writing intent down in the code/commit.
6. One-time setup per machine: `gh` installed + `gh auth login` (Jerry does auth; agents
   never store their own credentials).

## Repo structure & cross-client sharing (monorepo)

One repo, not one-per-client. Two clients ship from it — native iOS (overseas) and, later, a WeChat mini-program (China) — plus a shared Python pipeline and a shared data/contract layer.

```
/pipeline       Python content pipeline (shared upstream, single source of truth)
/shared         cross-client contract: content JSON schema + golden test vectors
/content        data: source PGNs committed; build artifacts gitignored
/App            native iOS (SwiftUI, XcodeGen) — overseas
/miniprogram    WeChat mini-program (JS) — China, NEAR-TERM parallel track
(docs at root: PRD.md, TECH_SPEC.md, AGENTS.md, CLAUDE.md, ROADMAP.md, UI_FLOW.md)
```

Why monorepo: schema, test vectors, content, and pipeline are shared by both clients. One repo = a scoring/schema change touches pipeline + contract + both clients' tests in ONE atomic commit, no cross-repo skew. Simplest for a solo dev + agents.

**Sequencing note (PRD §12.6):** the mini-program is NOT a far-future "phase 3" — Jerry already has a paid mini-program launching, so the China entity / ICP / payment / 备案 infrastructure is already paid for. The two clients are near-parallel. Build the shared layer (`/pipeline`, `/shared`) and the thin-client architecture FIRST so neither client is throwaway; then native (overseas) and mini-program (China) proceed near-parallel. The native client must be built thin NOW (logic precomputed into the JSON) precisely because the mini-program is close behind.

**Sharing principle — thin clients over a fat shared data layer. Do NOT port logic between Swift and JS.**

- Push every computable value into the pipeline → precomputed into the shared JSON (per-move score + score band, motif tags, annotation text, templated long-tail prose, difficulty). Both clients only *render* it. This is the bulk of reuse and it's free — it's data, not code. **Refines TECH_SPEC §3.2: scoring is precomputed in the pipeline, not computed in the client.** Build the native client thin NOW so the mini-program is later just "another UI shell over the same JSON."
- Chess move-gen / SAN-FEN: standard library per platform (ChessKit on native, chess.js in the mini-program). Don't hand-roll twice.
- Irreducible stateful logic that can't be precomputed (rating update, streak): reimplement minimally per client, kept identical by **golden test vectors in `/shared`** — the Swift and JS test suites run the same input→expected cases. The shared thing is the test vector, not the code.
- No backend just to share logic. No Swift↔JS cross-compilation.

**Branching:**

- Shared layer (`pipeline`, `shared`, `content`) → trunk: small commits straight to `main`; everyone depends on it.
- Client-specific work (`App`, `miniprogram`) → feature branches merged via PR, so the two clients develop in parallel without stepping on each other.

**CI enforces the cross-client guarantee:** every push runs pipeline `pytest` + Swift tests + JS tests, all against the same `/shared` golden vectors. Divergent scoring/rating fails CI and can't merge.

**Entity ≠ repo.** Individual (overseas) vs China-company (mainland) is a *publishing-account* matter (App Store / WeChat), not a code-repo matter — one private repo builds both. Only future exception: if China requires domestic source hosting, *mirror* `/miniprogram` to a domestic git (Gitee/Coding) — a sync, not a split.

**Release tags are independent:** `app-vX.Y` and `mp-vX.Y` ship on separate cadences; don't couple them.

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
