import Foundation
import Observation

/// Core guess loop (TECH_SPEC §3.1), shared by DailyChallenge and Training.
///
/// State machine:
///   context → autoplaying → awaitingGuess → revealed → (autoplaying → awaitingGuess | summary)
///
/// The user plays the hero's color for the whole game. Opening moves and the opponent's
/// replies / skipped forced moves AUTOPLAY ONE MOVE AT A TIME (UI_FLOW §4: never jump-cut
/// to a position). The model exposes a single `stepAutoplay()` tick; the view drives it on
/// a timer (~300ms/move), tests drive it synchronously.
@Observable
final class GuessSessionModel {

    enum Phase: Equatable {
        case context        // SHOW_CONTEXT — intro before the first guess
        case autoplaying    // AUTOPLAY — stepping moves one by one toward the next guess point
        case awaitingGuess  // AWAIT_GUESS — user to move at a guess point
        case revealed       // SCORE + REVEAL — master move + annotation shown
        case summary        // GAME_SUMMARY
    }

    /// Per-guess-point outcome, accumulated for the summary.
    struct PointResult: Identifiable {
        let ply: Int
        let guessedUci: String
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

    /// The "your move" card content (valid while revealed; nil when the user matched
    /// the master — the master annotation alone covers that case). PRD §6.
    var guessExplanation: GuessExplainer.Explanation? {
        guard phase == .revealed,
              let evaluation = lastEvaluation,
              let guessUci = lastGuessUci,
              let point = currentMove
        else { return nil }
        return GuessExplainer.explanation(
            guessUci: guessUci,
            evaluation: evaluation,
            point: point
        )
    }

    var guessPointsDone: Int { results.count }

    // MARK: - Transitions

    /// Leave the context screen: start stepping moves toward the first guess point.
    func begin() {
        guard phase == .context else { return }
        phase = .autoplaying
        settleIfAtGuessPoint()
    }

    /// Apply exactly one pending move (one autoplay tick). The view calls this on a
    /// timer; tests call it in a loop. No-op unless autoplaying.
    func stepAutoplay() {
        guard phase == .autoplaying else { return }
        guard game.moves.indices.contains(index) else {
            phase = .summary
            return
        }
        board.apply(uci: game.moves[index].uci)
        index += 1
        settleIfAtGuessPoint()
    }

    /// Stop autoplay when the next move is a guess point (or the game is over);
    /// otherwise stay in .autoplaying so the next tick continues.
    private func settleIfAtGuessPoint() {
        if !game.moves.indices.contains(index) {
            phase = .summary
        } else if game.moves[index].isGuessPoint {
            phase = .awaitingGuess
        }
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
            guessedUci: guessUci,
            evaluation: evaluation,
            masterUci: point.uci,
            masterSan: point.san,
            tags: point.tags
        ))

        lastEvaluation = evaluation
        lastGuessUci = guessUci
        phase = .revealed
    }

    /// From the reveal screen: re-enter autoplay. `index` still points at the revealed
    /// guess point, so the first tick plays the master's actual move (animated, like
    /// every other move), then continues to the next guess point or the summary.
    func proceed() {
        guard phase == .revealed, currentMove != nil else { return }
        lastEvaluation = nil
        lastGuessUci = nil
        phase = .autoplaying
        // Note: no settle here — the move at `index` IS a guess point (the revealed
        // one); the first stepAutoplay() applies it and moves past.
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

    /// The guess point the user did worst on (lowest display points) — drives the
    /// dynamic post-daily upsell (TECH_SPEC §6). nil if no guesses; ties → earliest ply.
    var weakestResult: PointResult? {
        results.min {
            $0.evaluation.displayPoints != $1.evaluation.displayPoints
                ? $0.evaluation.displayPoints < $1.evaluation.displayPoints
                : $0.ply < $1.ply
        }
    }

    /// Number of red-band misses, for "N critical misses to review" copy.
    var redMissCount: Int { results.filter { $0.evaluation.band == .red }.count }

    /// 1-based "Move N" (move-pair terms) for any ply — same rule as `currentMoveNumber`.
    func moveNumber(forPly ply: Int) -> Int { (ply + 1) / 2 }

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

/// Everything the user DB needs from a finished session (TECH_SPEC §4 user.sqlite).
struct GameOutcome {
    let gameId: String
    let totalScore: Int
    let finalRating: Double
    let guesses: [(ply: Int, uci: String, score: Int, band: ScoreBand)]
}

extension GuessSessionModel {
    var outcome: GameOutcome {
        GameOutcome(
            gameId: game.id,
            totalScore: totalScore,
            finalRating: rating,
            guesses: results.map {
                ($0.ply, $0.guessedUci, $0.evaluation.displayPoints, $0.evaluation.band)
            }
        )
    }
}
