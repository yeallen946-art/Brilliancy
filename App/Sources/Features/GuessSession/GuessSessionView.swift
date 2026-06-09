import SwiftUI

/// S2 — the core guess loop, presented modally full-screen (UI_FLOW §2/§3).
/// The annotation/feedback area is the star; tone is coach, not judge.
struct GuessSessionView: View {
    @State private var model: GuessSessionModel
    private let onClose: () -> Void

    init(game: GameContent, onClose: @escaping () -> Void = {}) {
        _model = State(initialValue: GuessSessionModel(game: game))
        self.onClose = onClose
    }

    var body: some View {
        VStack(spacing: 16) {
            header
            switch model.phase {
            case .context:       contextView
            case .awaitingGuess: guessView
            case .revealed:      revealView
            case .summary:       GameSummaryView(model: model, onClose: onClose)
            }
            Spacer(minLength: 0)
        }
        .padding()
        .animation(.default, value: model.phase)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("guessSessionView")
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Button { onClose() } label: {
                Image(systemName: "xmark").font(.headline)
            }
            Spacer()
            if model.phase == .awaitingGuess || model.phase == .revealed {
                Text("Move \(model.currentMoveNumber)")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Phases

    private var contextView: some View {
        VStack(spacing: 16) {
            Text(model.game.title).font(.title2.bold()).multilineTextAlignment(.center)
            Text(model.game.subtitle).font(.subheadline).foregroundStyle(.secondary)
            board(interactive: false)
            Text("You play \(heroColorName) (\(heroLastName)).")
                .font(.headline)
            Text(model.game.narrativeIntro)
                .font(.callout).foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Begin") { model.begin() }
                .buttonStyle(.borderedProminent)
        }
    }

    private var guessView: some View {
        VStack(spacing: 16) {
            board(interactive: true)
                .id(model.index) // reset board selection state per guess point
            Text("\(heroColorName) to move. What did \(heroLastName) play?")
                .font(.headline).multilineTextAlignment(.center)
        }
    }

    private var revealView: some View {
        VStack(spacing: 16) {
            if let eval = model.lastEvaluation {
                feedbackBanner(eval)
            }
            board(interactive: false, emphasis: revealEmphasis)
            annotationCard
            Button("Next") { model.proceed() }
                .buttonStyle(.borderedProminent)
        }
    }

    private func feedbackBanner(_ eval: GuessEvaluation) -> some View {
        HStack(spacing: 8) {
            Text(eval.band.icon).font(.title2.bold())
            Text(eval.label).font(.title3.bold())
            if !eval.isMatch && eval.evalDeltaCp > 0 {
                Text(String(format: "(-%.1f)", Double(eval.evalDeltaCp) / 100.0))
                    .font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 8).padding(.horizontal, 16)
        .background(bandColor(eval.band).opacity(0.18), in: Capsule())
        .foregroundStyle(bandColor(eval.band))
        .accessibilityIdentifier("feedbackPanel")
    }

    private var annotationCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Master played \(model.currentMove?.san ?? "")")
                .font(.subheadline.bold())
            Text(model.currentMove?.annotation ?? "")
                .font(.callout)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Board

    private func board(interactive: Bool, emphasis: Set<Sq> = []) -> some View {
        let onMove: ((Sq, Sq) -> Void)? = interactive
            ? { from, to in model.submitGuess(from: from, to: to) }
            : nil
        return BoardView(
            game: .constant(model.board),
            isInteractive: interactive,
            onMove: onMove,
            emphasis: emphasis,
            orientation: model.game.heroColor
        )
    }

    /// On reveal, emphasize both the user's move and the master's move squares.
    private var revealEmphasis: Set<Sq> {
        var squares: Set<Sq> = []
        if let guess = model.lastGuessUci, let parsed = ChessGame.parse(uci: guess) {
            squares.insert(parsed.from); squares.insert(parsed.to)
        }
        if let master = model.currentMove?.uci, let parsed = ChessGame.parse(uci: master) {
            squares.insert(parsed.from); squares.insert(parsed.to)
        }
        return squares
    }

    // MARK: - Helpers

    private var heroColorName: String { model.game.heroColor == .white ? "White" : "Black" }
    private var heroLastName: String { model.game.heroName.split(separator: " ").last.map(String.init) ?? model.game.heroName }

    private func bandColor(_ band: ScoreBand) -> Color {
        switch band {
        case .green:  return .green
        case .yellow: return .yellow
        case .red:    return .red
        }
    }
}
