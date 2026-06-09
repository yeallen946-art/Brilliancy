import SwiftUI

/// M1 home (stand-in for S1 "Today"). Launches a GuessSession for a chosen game.
/// Featured = the Opera Game (real pipeline content: Stockfish evals + grounded
/// annotations). The full Today/Train/Progress tabs (UI_FLOW §1) come later.
struct HomeView: View {
    @State private var playing: GameContent?

    private let featured = SampleGames.operaGame
    private let library: [GameContent] = [
        SampleGames.operaGame,
        SampleGames.retiDoubleBishop,
        SampleGames.gameOfTheCentury,
    ]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    VStack(spacing: 8) {
                        Text(featured.title)
                            .font(.title.bold()).multilineTextAlignment(.center)
                        Text(featured.subtitle)
                            .font(.subheadline).foregroundStyle(.secondary)
                    }

                    Button("Play today's game") { playing = featured }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .accessibilityIdentifier("playTodayButton")

                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Library").font(.headline)
                        ForEach(library) { game in
                            Button { playing = game } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(game.title).font(.body.weight(.semibold))
                                    Text(game.subtitle)
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .buttonStyle(.bordered)
                        }
                    }

                    NavigationLink("Board sandbox (debug)") { BoardSandboxView() }
                        .font(.footnote)
                }
                .padding()
            }
            .navigationTitle("Brilliancy")
            .fullScreenCover(item: $playing) { game in
                GuessSessionView(game: game) { playing = nil }
            }
        }
    }
}

#Preview {
    HomeView()
}
