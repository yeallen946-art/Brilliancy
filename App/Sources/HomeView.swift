import SwiftUI

/// M1 home (stand-in for S1 "Today"). Launches a GuessSession for a chosen game.
/// Visual system per UI_FLOW §4.1: dark shell, gold CTA, surface cards.
struct HomeView: View {
    @State private var playing: GameContent?

    private let featured = SampleGames.operaGame
    private let library: [GameContent] = [
        SampleGames.operaGame,
        SampleGames.reti,
        SampleGames.gameOfTheCentury,
    ]

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: Theme.Space.lg) {
                        VStack(spacing: Theme.Space.xs) {
                            Text(featured.title)
                                .font(.system(size: 26, weight: .medium))
                                .foregroundStyle(Theme.textPrimary)
                                .multilineTextAlignment(.center)
                            Text(featured.subtitle)
                                .font(.system(size: 13))
                                .foregroundStyle(Theme.textSecondary)
                        }
                        .padding(.top, Theme.Space.lg)

                        Button("Play today's game") { playing = featured }
                            .buttonStyle(GoldButtonStyle())
                            .accessibilityIdentifier("playTodayButton")

                        librarySection

                        NavigationLink("Board sandbox (debug)") { BoardSandboxView() }
                            .font(.footnote)
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.top, Theme.Space.xs)

                        Text("Pieces: cburnett by Colin M.L. Burnett · CC BY-SA 3.0")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textSecondary.opacity(0.7))
                            .multilineTextAlignment(.center)
                            .padding(.top, Theme.Space.lg)
                    }
                    .padding(Theme.Space.md)
                }
            }
            .navigationTitle("Brilliancy")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .fullScreenCover(item: $playing) { game in
                GuessSessionView(game: game) { playing = nil }
            }
        }
        .preferredColorScheme(.dark)
        .tint(Theme.gold)
    }

    private var librarySection: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sm) {
            Text("LIBRARY")
                .font(.system(size: 11, weight: .medium))
                .kerning(0.8)
                .foregroundStyle(Theme.textSecondary)
            ForEach(library) { game in
                Button { playing = game } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(game.title)
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(Theme.textPrimary)
                        Text(game.subtitle)
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textSecondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardSurface(padding: Theme.Space.sm)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

#Preview {
    HomeView()
}
