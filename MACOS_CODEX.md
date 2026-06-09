# MACOS_CODEX.md — Brilliancy

Project-local instructions for Codex sessions running on macOS. These extend `AGENTS.md` and `CLAUDE.md`; they do not replace either file.

## Read first

At the start of a macOS/Codex session:

1. Read `AGENTS.md`.
2. Read `CLAUDE.md` and obey its hard rules.
3. Read `MACOS_CODEX.md`.
4. For product decisions, read `PRD.md`; for implementation decisions, read `TECH_SPEC.md`; for milestone scope and acceptance, read `ROADMAP.md`.

## Role

The macOS/Codex agent owns the local build/test/debug loop:

- Run XcodeGen and `xcodebuild`.
- Read compiler/test failures.
- Fix build-layer issues: signing, missing file references, `project.yml` configuration, dependencies, and compile errors.
- Report functional/product logic problems clearly for the Windows/Claude Code side instead of rewriting feature intent.

Do not write new product features just to make the build green. Do not violate `CLAUDE.md` hard rules.

## Xcode project

`App/Brilliancy.xcodeproj` is generated from `App/project.yml` by XcodeGen.

- Never hand-edit `App/Brilliancy.xcodeproj`.
- Never commit `App/Brilliancy.xcodeproj`.
- To add Swift files, create them under the appropriate `App/Sources` or `App/Tests` folder; XcodeGen globs them in.
- Structural changes go in `App/project.yml`.

## Build loop

From the repo root:

```bash
git status --short --branch
git pull --ff-only
cd App
xcodegen generate
xcodebuild -scheme Brilliancy -destination 'platform=iOS Simulator,name=iPhone 16' build
xcodebuild -scheme Brilliancy -destination 'platform=iOS Simulator,name=iPhone 16' test
```

If `iPhone 16` is not installed on the Mac, use an available iPhone simulator and report the exact destination used.

To inspect available simulators:

```bash
xcrun simctl list devices available
```

## Simulator check

When the app builds, verify it can install and launch in the simulator. Use command-line tools, not Xcode GUI:

```bash
xcrun simctl boot <device-id>
xcrun simctl bootstatus <device-id> -b
xcrun simctl install <device-id> <path-to-Brilliancy.app>
xcrun simctl launch <device-id> com.brilliancy.app
```

Screenshots are useful for reporting UI problems:

```bash
xcrun simctl io <device-id> screenshot /tmp/brilliancy-simulator.png
```

## Reporting

When reporting back, include:

- The exact `xcodegen` / `xcodebuild` commands used.
- The simulator destination used.
- Whether build, test, install, and launch passed.
- Any first failure, classified as build-layer or functional/product logic.
- Any commit hash pushed.
