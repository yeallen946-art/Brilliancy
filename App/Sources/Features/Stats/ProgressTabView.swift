import SwiftUI

/// S7 "Progress" — first honest version: rating, streak, games completed, from the
/// user DB. Rating-history chart + weakness breakdown (and the premium lock) come
/// later; this screen is where they land.
struct ProgressTabView: View {
    let userStore: UserStore?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: Theme.Space.lg) {
                        VStack(spacing: Theme.Space.xs) {
                            Text("GUESS RATING")
                                .font(.system(size: 11, weight: .medium))
                                .kerning(0.8)
                                .foregroundStyle(Theme.textSecondary)
                            Text("\(Int(userStore?.latestRating() ?? 1200))")
                                .font(.system(size: 52, weight: .medium, design: .rounded))
                                .foregroundStyle(Theme.gold)
                        }
                        .padding(.top, Theme.Space.lg)

                        HStack(spacing: Theme.Space.md) {
                            statCard(
                                label: "STREAK",
                                value: "\u{1F525} \(userStore?.streak.current ?? 0)")
                            statCard(
                                label: "LONGEST",
                                value: "\(userStore?.streak.longest ?? 0)")
                            statCard(
                                label: "GAMES",
                                value: "\(userStore?.completedGameIds().count ?? 0)")
                        }

                        Text("Rating history and your strengths & weaknesses by theme appear here as you play.")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.textSecondary)
                            .multilineTextAlignment(.center)
                            .padding(.top, Theme.Space.md)
                    }
                    .padding(Theme.Space.md)
                }
            }
            .navigationTitle("Progress")
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
    }

    private func statCard(label: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .kerning(0.8)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.system(size: 20, weight: .medium))
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity)
        .cardSurface(padding: Theme.Space.sm)
    }
}
