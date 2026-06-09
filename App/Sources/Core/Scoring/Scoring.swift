import Foundation

// Scoring + guess-rating math as PURE functions with table-driven tests (TECH_SPEC §3.2/3.3).
// All tunable constants live in ONE config struct (ScoringConfig) — never inline scoring
// numbers elsewhere (CLAUDE.md). Implemented in M1.
enum Scoring {}
