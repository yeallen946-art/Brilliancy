import Foundation

// Paywall + StoreKit gating. ALL premium checks go through EntitlementStore.isPremium —
// never read StoreKit transactions in feature code (CLAUDE.md hard rule). TECH_SPEC §6.
// Implemented in M4. Do not touch product tiers/pricing without PRD §7 changing first.
enum Paywall {}
