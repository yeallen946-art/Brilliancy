import SwiftUI

/// S5 "Train" — first honest version: a flat, playable list of all bundled games.
/// Pack browsing (by player / by theme) + premium locks arrive with M4's
/// EntitlementStore; this screen is structured so packs slot in above the list.
struct TrainView: View {
    let userStore: UserStore?
    @State private var playing: GameContent?

    private let games: [GameContent] = ContentStore.bundledGames()

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
                            Button { playing = game } label: {
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
                                    if userStore?.completedGameIds().contains(game.id) == true {
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
        }
    }
}
