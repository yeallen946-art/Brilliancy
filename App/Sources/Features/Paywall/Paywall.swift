import Foundation

// Freemium split (PRD §7, TECH_SPEC §6). All premium checks go through
// EntitlementStore.isPremium — never read StoreKit transactions in feature code
// (CLAUDE.md hard rule). Do not touch tiers/pricing without PRD §7 changing first.

/// What the free tier can play besides today's daily challenge.
enum FreeTier {
    /// PRD §7: the free tier includes 3 sample games with full annotations.
    static let sampleGameCount = 3

    /// The free slice of the library, by library order (= stable game-id order).
    /// A curated `is_sample` flag in content.sqlite can replace this rule later
    /// without touching the gating call sites.
    static func unlockedGameIDs(in library: [GameContent]) -> Set<String> {
        Set(library.prefix(sampleGameCount).map(\.id))
    }
}

/// Where the paywall was summoned from (TECH_SPEC §6 conversion triggers;
/// becomes the `paywall_shown(trigger)` analytics dimension when TelemetryDeck lands).
enum PaywallTrigger: String, Identifiable {
    case postDaily = "post_daily"
    case lockedGame = "locked_game"
    case lockedProgress = "locked_progress"

    var id: String { rawValue }
}
