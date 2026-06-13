import SwiftUI

/// S3 — single-game summary (UI_FLOW §3/§4.1). Score, rating delta, per-point band row,
/// per-tag breakdown, share card (TECH_SPEC §7). Review-moves lands later.
struct GameSummaryView: View {
    let model: GuessSessionModel
    var userStore: UserStore?
    var isDaily: Bool = false
    var onClose: () -> Void

    @Environment(EntitlementStore.self) private var entitlements
    @State private var shareImage: Image?
    @State private var paywall: PaywallTrigger?

    var body: some View {
        VStack(spacing: Theme.Space.lg) {
            Text("Game complete")
                .font(.system(size: 22, weight: .medium)).foregroundStyle(Theme.textPrimary)

            Text("\(model.totalScore)")
                .font(.system(size: 52, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.gold)

            HStack(spacing: 6) {
                Text("Guess Rating \(Int(model.rating.rounded()))")
                    .font(.system(size: 15, weight: .medium)).foregroundStyle(Theme.textPrimary)
                ratingDeltaLabel
            }

            if !model.bands.isEmpty {
                Text(model.bands.map(\.emoji).joined())
                    .font(.title3).lineLimit(2).multilineTextAlignment(.center)
            }

            if !model.tagBreakdown().isEmpty {
                VStack(spacing: 4) {
                    ForEach(model.tagBreakdown()) { row in
                        Text("\(row.tag.label) \(row.hits)/\(row.total)")
                            .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                    }
                }
            }

            if let shareImage {
                ShareLink(
                    item: shareImage,
                    preview: SharePreview("Brilliancy \u{2014} \(model.totalScore)", image: shareImage)
                ) {
                    Text("Share")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Theme.gold)
                }
            }

            // Post-daily upsell (TECH_SPEC §6 conversion trigger #1). Dynamic: point at
            // the move the user did worst on so the value is "see why THAT move", not a
            // generic pitch. Coach tone (PRD §5): an invitation, never a scold; score is
            // the move's display points (mean-of-points model, §3.2), not a "cost".
            if isDaily && !entitlements.isPremium {
                VStack(spacing: Theme.Space.xs) {
                    Text(upsellHeadline)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                    Text(upsellSubcopy)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.textSecondary)
                        .multilineTextAlignment(.center)
                    Button(upsellButtonTitle) { paywall = .postDaily }
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Theme.gold)
                        .accessibilityIdentifier("postDailyUpsellButton")
                }
                .cardSurface(padding: Theme.Space.sm)
            }

            Button("Done") { onClose() }.buttonStyle(GoldButtonStyle())
        }
        .frame(maxWidth: .infinity)
        .sheet(item: $paywall) { trigger in
            PaywallView(trigger: trigger) { paywall = nil }
        }
        .task {
            // Render once; streak is read AFTER the session was recorded (the recording
            // task in GuessSessionView runs on the same summary transition).
            if shareImage == nil, !model.bands.isEmpty {
                shareImage = ShareCard.render(ShareCardData(
                    date: Date(),
                    score: model.totalScore,
                    bands: model.bands,
                    streak: userStore?.streak.current ?? 0
                ))
            }
        }
    }

    // MARK: - Dynamic upsell copy (TECH_SPEC §6)

    /// The miss worth selling the explanation for: the weakest guess point, but only
    /// when it actually fell short (a green/best move has nothing to "explain why it
    /// failed"). nil → the user aced it, so we fall back to a generic invite.
    private var upsellMiss: GuessSessionModel.PointResult? {
        guard let weakest = model.weakestResult, weakest.evaluation.band != .green
        else { return nil }
        return weakest
    }

    private var upsellHeadline: String {
        guard let miss = upsellMiss else { return "Sharp play today." }
        return "Move \(model.moveNumber(forPly: miss.ply)) scored \(miss.evaluation.displayPoints)/100."
    }

    private var upsellSubcopy: String {
        guard upsellMiss != nil else {
            return "The full library has more master games like this, with AI insights on every move."
        }
        if model.redMissCount >= 2 {
            return "See the engine line and coach explanation \u{2014} \(model.redMissCount) critical misses to review in the full library."
        }
        return "See the engine line and coach explanation, plus every master game in the full library."
    }

    private var upsellButtonTitle: String {
        upsellMiss == nil ? "Explore the library" : "See the explanation"
    }

    @ViewBuilder
    private var ratingDeltaLabel: some View {
        let delta = model.ratingDelta
        if delta > 0 {
            Text("\u{25B2} +\(delta)").foregroundStyle(Theme.feedbackGreen)
                .font(.system(size: 15, weight: .medium))
        } else if delta < 0 {
            Text("\u{25BC} \(delta)").foregroundStyle(Theme.feedbackRed)
                .font(.system(size: 15, weight: .medium))
        } else {
            Text("\u{2014}").foregroundStyle(Theme.textSecondary)
        }
    }
}
