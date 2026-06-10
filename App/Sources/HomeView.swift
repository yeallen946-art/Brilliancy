import SwiftUI

/// S1 "Today" (first real version). Featured slot = today's daily challenge from the
/// CDN (cache-backed), falling back to the first bundled game while offline/loading.
/// Visual system per UI_FLOW §4.1: dark shell, gold CTA (and streak), surface cards.
struct HomeView: View {
    @State private var playing: GameContent?
    @State private var dailyGame: GameContent?
    @State private var userStore = UserStore.onDisk()

    /// Pipeline content from the bundled content.sqlite (GRDB path Mac-verified,
    /// issue #3). The M1 Byrne–Fischer sample (placeholder evals, also used by unit
    /// tests) is appended last — guarantees the library is never empty.
    private let library: [GameContent] =
        ContentStore.bundledGames() + [SampleGames.gameOfTheCentury]

    private var featured: GameContent { dailyGame ?? library[0] }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: Theme.Space.lg) {
                        featuredSection
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
                GuessSessionView(
                    game: game,
                    userStore: userStore,
                    isDaily: game.id == dailyGame?.id
                ) { playing = nil }
            }
            .task {
                dailyGame = await DailyChallengeLoader().todaysGame()
            }
        }
        .preferredColorScheme(.dark)
        .tint(Theme.gold)
    }

    private var featuredSection: some View {
        VStack(spacing: Theme.Space.xs) {
            HStack(spacing: Theme.Space.xs) {
                Text(dailyGame != nil ? "TODAY'S GAME" : "FEATURED")
                    .font(.system(size: 11, weight: .medium))
                    .kerning(0.8)
                    .foregroundStyle(Theme.textSecondary)
                if let streak = userStore?.streak, streak.current > 0 {
                    Text("\u{1F525} \(streak.current)")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.gold)
                }
            }
            .padding(.top, Theme.Space.lg)
            Text(featured.title)
                .font(.system(size: 26, weight: .medium))
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
            Text(featured.subtitle)
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
        }
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
