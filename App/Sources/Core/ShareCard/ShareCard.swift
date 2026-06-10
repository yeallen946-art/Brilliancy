import SwiftUI

/// Share card (TECH_SPEC §7, UI_FLOW S4): app name, date, per-point emoji band
/// (🟩🟨🟥 — never move spoilers), score, streak. Rendered offscreen to an image
/// and shared via ShareLink.
struct ShareCardData {
    let date: Date
    let score: Int
    let bands: [ScoreBand]
    let streak: Int
}

struct ShareCardView: View {
    let data: ShareCardData

    var body: some View {
        VStack(spacing: Theme.Space.sm) {
            HStack {
                Text("Brilliancy")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundStyle(Theme.gold)
                Spacer()
                if data.streak > 0 {
                    Text("\u{1F525} \(data.streak)")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Theme.gold)
                }
            }
            Text(data.date.formatted(date: .abbreviated, time: .omitted))
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text(data.bands.map(\.emoji).joined())
                .font(.system(size: 24))
                .padding(.vertical, Theme.Space.xs)

            Text("Score \(data.score)")
                .font(.system(size: 34, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.textPrimary)

            Text("Guess the master's move")
                .font(.system(size: 11))
                .kerning(0.4)
                .foregroundStyle(Theme.textSecondary)
        }
        .padding(Theme.Space.lg)
        .frame(width: 340)
        .background(Theme.background)
    }
}

enum ShareCard {
    /// Offscreen render -> shareable Image (TECH_SPEC §7). ImageRenderer is the
    /// sanctioned SwiftUI API; its output type (UIImage) is the one UIKit touchpoint,
    /// unavoidable for ShareLink image payloads.
    @MainActor
    static func render(_ data: ShareCardData) -> Image? {
        let renderer = ImageRenderer(content: ShareCardView(data: data))
        renderer.scale = 3
        guard let uiImage = renderer.uiImage else { return nil }
        return Image(uiImage: uiImage)
    }
}
