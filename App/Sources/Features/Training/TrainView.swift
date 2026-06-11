import SwiftUI

/// S5 "Train" — a flat, playable list of all bundled games, now with the freemium
/// split (PRD §7): free users play the FreeTier sample slice; locked rows show a
/// lock and summon the paywall (S8). Pack browsing slots in above this list later.
struct TrainView: View {
    let userStore: UserStore?
    @Environment(EntitlementStore.self) private var entitlements
    @State private var playing: GameContent?
    @State private var paywall: PaywallTrigger?

    private let games: [GameContent] = {
        var games = ContentStore.bundledGames()
        #if DEBUG
        // UI-test-only fixture (positive reveal card needs an engine-equal guess,
        // which curated content never contains). Inert without the launch argument.
        if UITestFixtures.isEqualGuessFixtureEnabled {
            games.append(UITestFixtures.equalGuessGame)
        }
        #endif
        return games
    }()

    private var unlockedIDs: Set<String> {
        entitlements.isPremium ? Set(games.map(\.id)) : FreeTier.unlockedGameIDs(in: games)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Space.sm) {
                        Text("ALL GAMES")
                            .font(.system(size: 11, weight: .medium))
                            .kerning(0.8)
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.top, Theme.Space.md)

                        if games.isEmpty {
                            Text("No games available.")
                                .font(.system(size: 13))
                                .foregroundStyle(Theme.textSecondary)
                        }

                        ForEach(games) { game in
                            let unlocked = unlockedIDs.contains(game.id)
                            Button {
                                if unlocked { playing = game } else { paywall = .lockedGame }
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(game.title)
                                            .font(.system(size: 15, weight: .medium))
                                            .foregroundStyle(Theme.textPrimary)
                                        Text(game.subtitle)
                                            .font(.system(size: 11))
                                            .foregroundStyle(Theme.textSecondary)
                                    }
                                    Spacer()
                                    if !unlocked {
                                        Image(systemName: "lock.fill")
                                            .font(.system(size: 13))
                                            .foregroundStyle(Theme.textSecondary)
                                    } else if userStore?.completedGameIds().contains(game.id) == true {
                                        Image(systemName: "checkmark.circle.fill")
                                            .foregroundStyle(Theme.feedbackGreen)
                                    }
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .cardSurface(padding: Theme.Space.sm)
                            }
                            .buttonStyle(.plain)
                        }

                        Text("Packs by player & theme arrive with the premium library (M4).")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textSecondary.opacity(0.7))
                            .padding(.top, Theme.Space.md)
                    }
                    .padding(Theme.Space.md)
                }
            }
            .navigationTitle("Train")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .fullScreenCover(item: $playing) { game in
                GuessSessionView(game: game, userStore: userStore) { playing = nil }
            }
            .sheet(item: $paywall) { trigger in
                PaywallView(trigger: trigger) { paywall = nil }
            }
        }
    }
}
