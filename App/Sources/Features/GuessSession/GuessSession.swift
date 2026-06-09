import Foundation
import Observation

/// Core guess loop (TECH_SPEC §3.1), shared by DailyChallenge and Training.
///
/// State machine:
///   context → awaitingGuess → revealed → (awaitingGuess | summary)
///
/// The user plays the hero's color for the whole game. Opening moves and the opponent's
/// replies / skipped forced moves autoplay; the user only acts at guess points.
@Observable
final class GuessSessionModel {

    enum Phase: Equatable {
        case context        // SHOW_CONTEXT — intro before the first guess
        case awaitingGuess  // AWAIT_GUESS — user to move at a guess point
        case revealed       // SCORE + REVEAL — master move + annotation shown
        case summary        // GAME_SUMMARY
    }

    /// Per-guess-point outcome, accumulated for the summary.
    struct PointResult: Identifiable {
        let ply: Int
        let evaluation: GuessEvaluation
        let masterUci: String
        let masterSan: String
        let tags: [GuessTag]
        var id: Int { ply }
    }

    let game: GameContent
    private let config: ScoringConfig

    private(set) var board: ChessGame
    private(set) var phase: Phase = .context
    /// Index into `game.moves` of the move currently being processed / guessed.
    private(set) var index = 0
    private(set) var rating: Double
    private(set) var results: [PointResult] = []

    // Reveal state (valid while phase == .revealed).
    private(set) var lastEvaluation: GuessEvaluation?
    private(set) var lastGuessUci: String?

    let startRating: Double

    init(game: GameContent, config: ScoringConfig = .default) {
        self.game = game
        self.config = config
        self.rating = config.startRating
        self.startRating = config.startRating
        self.board = ChessGame(fen: game.startFen) ?? ChessGame(fen: FEN.start)!
    }

    // MARK: - Derived

    /// The guess point the user is currently on (valid in awaitingGuess / revealed).
    var currentMove: ContentMove? {
        guard game.moves.indices.contains(index) else { return nil }
        return game.moves[index]
    }

    /// 1-based "Move N" in chess move-pair terms, for the header.
    var currentMoveNumber: Int { ((currentMove?.ply ?? 1) + 1) / 2 }

    var guessPointsDone: Int { results.count }

    // MARK: - Transitions

    /// Leave the context screen: autoplay up to the first guess point.
    func begin() {
        guard phase == .context else { return }
        advanceToNextGuessPoint()
    }

    /// Submit the user's guess (already validated legal by the board). Scores + reveals.
    func submitGuess(from: Sq, to: Sq) {
        guard phase == .awaitingGuess, let point = currentMove, point.isGuessPoint else { return }

        let guessUci = board.uci(from: from, to: to)
        let evaluation = Scoring.evaluate(
            guessUci: guessUci,
            masterUci: point.uci,
            candidateEvals: point.candidateEvals,
            config: config
        )

        rating = GuessRating.updated(
            rating: rating,
            difficulty: point.difficulty,
            qualityPoints: evaluation.qualityPoints,
            priorGuessCount: results.count,
            config: config
        )

        results.append(PointResult(
            ply: point.ply,
            evaluation: evaluation,
            masterUci: point.uci,
            masterSan: point.san,
            tags: point.tags
        ))

        lastEvaluation = evaluation
        lastGuessUci = guessUci
        phase = .revealed
    }

    /// From the reveal screen: play the master move, autoplay to the next guess point
    /// (or finish). Animation/pacing is a view concern; the model advances atomically.
    func proceed() {
        guard phase == .revealed, let point = currentMove else { return }
        board.apply(uci: point.uci) // play the master's actual move
        index += 1
        lastEvaluation = nil
        lastGuessUci = nil
        advanceToNextGuessPoint()
    }

    // MARK: - Helpers

    /// Apply non-guess moves until the next guess point, or end the game.
    private func advanceToNextGuessPoint() {
        while game.moves.indices.contains(index) {
            if game.moves[index].isGuessPoint {
                phase = .awaitingGuess
                return
            }
            board.apply(uci: game.moves[index].uci)
            index += 1
        }
        phase = .summary
    }

    // MARK: - Summary

    /// Mean of display scores (0 if no guesses). TECH_SPEC §3.2 game score.
    var totalScore: Int {
        guard !results.isEmpty else { return 0 }
        let sum = results.reduce(0) { $0 + $1.evaluation.displayPoints }
        return Int((Double(sum) / Double(results.count)).rounded())
    }

    var ratingDelta: Int { Int(rating.rounded()) - Int(startRating.rounded()) }

    /// Per-guess-point bands in play order (for the emoji row / share card).
    var bands: [ScoreBand] { results.map { $0.evaluation.band } }

    /// Hit-rate per tag. "Hit" = green band. Returned in a stable tag order.
    func tagBreakdown() -> [TagStat] {
        var totals: [GuessTag: (hits: Int, total: Int)] = [:]
        for result in results {
            let isHit = result.evaluation.band == .green
            for tag in result.tags {
                var entry = totals[tag] ?? (0, 0)
                entry.total += 1
                if isHit { entry.hits += 1 }
                totals[tag] = entry
            }
        }
        return GuessTag.allCases.compactMap { tag in
            guard let e = totals[tag] else { return nil }
            return TagStat(tag: tag, hits: e.hits, total: e.total)
        }
    }
}

/// Per-tag hit-rate row for the summary (Identifiable for ForEach).
struct TagStat: Identifiable {
    let tag: GuessTag
    let hits: Int
    let total: Int
    var id: GuessTag { tag }
}
