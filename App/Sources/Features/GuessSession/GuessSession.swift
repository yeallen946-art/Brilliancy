import Foundation

// Core guess loop shared by DailyChallenge and Training (TECH_SPEC §3.1).
// State machine: LOAD → SHOW_CONTEXT → [PRESENT → AWAIT_GUESS → SCORE → REVEAL
//   → AUTOPLAY] per guess point → GAME_SUMMARY. Implemented in M1.
enum GuessSession {}
