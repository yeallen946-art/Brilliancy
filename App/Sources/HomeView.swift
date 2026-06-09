import SwiftUI

/// M1 home (a stand-in for S1 "Today"). Launches the sample game's GuessSession.
/// Full Today/Train/Progress tab structure (UI_FLOW §1) arrives with later milestones.
struct HomeView: View {
    @State private var isPlaying = false

    private let game = SampleGames.gameOfTheCentury

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Spacer()

                VStack(spacing: 8) {
                    Text(game.title)
                        .font(.title.bold()).multilineTextAlignment(.center)
                    Text(game.subtitle)
                        .font(.subheadline).foregroundStyle(.secondary)
                }

                Button("Play today's game") { isPlaying = true }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .accessibilityIdentifier("playTodayButton")

                Spacer()

                NavigationLink("Board sandbox (debug)") { BoardSandboxView() }
                    .font(.footnote)
            }
            .padding()
            .navigationTitle("Brilliancy")
            .fullScreenCover(isPresented: $isPlaying) {
                GuessSessionView(game: game) { isPlaying = false }
            }
        }
    }
}

#Preview {
    HomeView()
}
