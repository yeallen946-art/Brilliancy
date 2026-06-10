import SwiftUI

/// S3 — single-game summary (UI_FLOW §3/§4.1). Score, rating delta, per-point band row,
/// per-tag breakdown, share card (TECH_SPEC §7). Review-moves lands later.
struct GameSummaryView: View {
    let model: GuessSessionModel
    var userStore: UserStore?
    var onClose: () -> Void

    @State private var shareImage: Image?

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

            Button("Done") { onClose() }.buttonStyle(GoldButtonStyle())
        }
        .frame(maxWidth: .infinity)
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
