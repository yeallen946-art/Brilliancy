import SwiftUI

/// S2 — the core guess loop, presented modally full-screen (UI_FLOW §2/§3/§4.1).
/// Visual flow: top bar → board → feedback bar → annotation card (the star) → gold button.
struct GuessSessionView: View {
    @State private var model: GuessSessionModel
    @State private var recorded = false
    private let onClose: () -> Void
    private let userStore: UserStore?
    private let isDaily: Bool

    init(game: GameContent,
         userStore: UserStore? = nil,
         isDaily: Bool = false,
         onClose: @escaping () -> Void = {}) {
        // Rating continuity (TECH_SPEC §3.3): start from the last persisted snapshot.
        var config = ScoringConfig.default
        if let store = userStore {
            config.startRating = store.latestRating(default: config.startRating)
        }
        _model = State(initialValue: GuessSessionModel(game: game, config: config))
        self.userStore = userStore
        self.isDaily = isDaily
        self.onClose = onClose
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: Theme.Space.md) {
                header
                switch model.phase {
                case .context:       contextView
                case .autoplaying:   autoplayView
                case .awaitingGuess: guessView
                case .revealed:      revealView
                case .summary:       GameSummaryView(model: model, userStore: userStore, isDaily: isDaily, onClose: onClose)
                }
                Spacer(minLength: 0)
            }
            .padding(Theme.Space.md)
            .animation(.default, value: model.phase)
        }
        .preferredColorScheme(.dark)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("guessSessionView")
        // Drive autoplay: one move every ~320ms (UI_FLOW §4: walk in step by step,
        // never jump-cut). task(id:) cancels/restarts when the phase changes.
        .task(id: model.phase == .autoplaying) {
            guard model.phase == .autoplaying else { return }
            while model.phase == .autoplaying, !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 320_000_000)
                if Task.isCancelled { return }
                withAnimation(.easeInOut(duration: 0.25)) {
                    model.stepAutoplay()
                }
            }
        }
        // Persist the finished session exactly once (TECH_SPEC §4 user.sqlite).
        .task(id: model.phase == .summary) {
            guard model.phase == .summary, !recorded, let store = userStore else { return }
            recorded = true
            store.record(model.outcome, isDaily: isDaily)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Button { onClose() } label: {
                Image(systemName: "xmark").font(.headline).foregroundStyle(Theme.textSecondary)
            }
            Spacer()
            if model.phase == .awaitingGuess || model.phase == .revealed {
                Text("Move \(model.currentMoveNumber)")
                    .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
            }
        }
    }

    // MARK: - Phases

    private var contextView: some View {
        VStack(spacing: Theme.Space.md) {
            Text(model.game.title)
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(Theme.textPrimary).multilineTextAlignment(.center)
            Text(model.game.subtitle)
                .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
            board(interactive: false)
            Text("You play \(heroColorName) (\(heroLastName)).")
                .font(.system(size: 15, weight: .medium)).foregroundStyle(Theme.textPrimary)
            Text(model.game.narrativeIntro)
                .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                .lineSpacing(5).multilineTextAlignment(.center)
            Button("Begin") { model.begin() }.buttonStyle(GoldButtonStyle())
        }
    }

    private var autoplayView: some View {
        VStack(spacing: Theme.Space.md) {
            board(interactive: false)
            Text("\u{2026}")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Theme.textSecondary)
        }
    }

    private var guessView: some View {
        VStack(spacing: Theme.Space.md) {
            board(interactive: true)
                .id(model.index) // reset board selection state per guess point
            Text("\(heroColorName) to move. What did \(heroLastName) play?")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Theme.textPrimary).multilineTextAlignment(.center)
        }
    }

    private var revealView: some View {
        VStack(spacing: Theme.Space.md) {
            if let eval = model.lastEvaluation {
                feedbackBanner(eval)
            }
            board(interactive: false, emphasis: revealEmphasis)
            annotationCard
            Button("Next") { model.proceed() }.buttonStyle(GoldButtonStyle())
        }
    }

    private func feedbackBanner(_ eval: GuessEvaluation) -> some View {
        HStack(spacing: Theme.Space.xs) {
            Text(eval.band.icon).font(.title2.weight(.medium))
            Text(eval.label).font(.system(size: 17, weight: .medium))
            if !eval.isMatch && eval.evalDeltaCp > 0 {
                Text(String(format: "(-%.1f)", Double(eval.evalDeltaCp) / 100.0))
                    .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(.vertical, Theme.Space.xs).padding(.horizontal, Theme.Space.md)
        .background(bandColor(eval.band).opacity(0.18), in: Capsule())
        .foregroundStyle(bandColor(eval.band))
        .accessibilityIdentifier("feedbackPanel")
    }

    private var annotationCard: some View {
        VStack(alignment: .leading, spacing: Theme.Space.xs) {
            Text("Master played \(model.currentMove?.san ?? "")")
                .font(.system(size: 13, weight: .medium)).foregroundStyle(Theme.gold)
            Text(model.currentMove?.annotation ?? "")
                .font(.system(size: 13)).foregroundStyle(Theme.textPrimary)
                .lineSpacing(5).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface()
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
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.board))
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
        case .green:  return Theme.feedbackGreen
        case .yellow: return Theme.feedbackYellow
        case .red:    return Theme.feedbackRed
        }
    }
}
