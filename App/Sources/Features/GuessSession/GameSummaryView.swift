import SwiftUI

/// S3 — single-game summary (UI_FLOW §3). Score, rating delta, per-point band row,
/// per-tag breakdown. Share + Review land in M3; this is the M1 functional version.
struct GameSummaryView: View {
    let model: GuessSessionModel
    var onClose: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Text("Game complete").font(.title2.bold())

            Text("Score \(model.totalScore)")
                .font(.system(size: 44, weight: .bold, design: .rounded))

            HStack(spacing: 6) {
                Text("Guess Rating \(Int(model.rating.rounded()))").font(.headline)
                ratingDeltaLabel
            }

            if !model.bands.isEmpty {
                Text(model.bands.map(\.emoji).joined())
                    .font(.title3)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
            }

            if !model.tagBreakdown().isEmpty {
                VStack(spacing: 4) {
                    ForEach(model.tagBreakdown()) { row in
                        Text("\(row.tag.label) \(row.hits)/\(row.total)")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
            }

            Button("Done") { onClose() }
                .buttonStyle(.borderedProminent)

            // Share / Review moves arrive in M3 (TECH_SPEC §7) — intentionally omitted here.
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var ratingDeltaLabel: some View {
        let delta = model.ratingDelta
        if delta > 0 {
            Text("\u{25B2} +\(delta)").foregroundStyle(.green).font(.headline)
        } else if delta < 0 {
            Text("\u{25BC} \(delta)").foregroundStyle(.red).font(.headline)
        } else {
            Text("\u{2014}").foregroundStyle(.secondary)
        }
    }
}
