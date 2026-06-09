import SwiftUI

/// M0 acceptance harness: set any FEN and make legal moves on the board.
/// This is a throwaway dev screen — M1 replaces the root with real navigation.
struct BoardSandboxView: View {
    @State private var game = ChessGame(fen: FEN.start)!
    @State private var fenInput = FEN.start
    @State private var loadError: String?

    var body: some View {
        VStack(spacing: 16) {
            Text("Brilliancy — Board Sandbox")
                .font(.headline)

            BoardView(game: $game)
                .padding(.horizontal)

            Text("Side to move: \(game.sideToMove == .white ? "White" : "Black")")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 8) {
                TextField("FEN", text: $fenInput, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(.system(.footnote, design: .monospaced))

                if let loadError {
                    Text(loadError).font(.caption).foregroundStyle(.red)
                }

                HStack {
                    Button("Load FEN") { loadFEN() }
                        .buttonStyle(.borderedProminent)
                    Button("Reset") {
                        fenInput = FEN.start
                        loadFEN()
                    }
                    .buttonStyle(.bordered)
                    Spacer()
                    Button("Copy current") { fenInput = game.fen }
                        .buttonStyle(.bordered)
                }
            }
            .padding(.horizontal)

            Spacer(minLength: 0)
        }
        .padding(.vertical)
    }

    private func loadFEN() {
        let trimmed = fenInput.trimmingCharacters(in: .whitespacesAndNewlines)
        if let loaded = ChessGame(fen: trimmed) {
            game = loaded
            loadError = nil
        } else {
            loadError = "Invalid FEN."
        }
    }
}

#Preview {
    BoardSandboxView()
}
