import Foundation

/// Runtime content model for one master game. In M1 this is populated by a hardcoded
/// Swift literal (`SampleGames`); in M2 the pipeline builds it into content.sqlite and
/// the app decodes equivalent rows (TECH_SPEC §4). Kept deliberately close to the DB shape.
struct GameContent: Identifiable {
    let id: String
    let white: String
    let black: String
    let event: String
    let year: Int
    let result: String
    let heroColor: PieceColor
    let title: String
    let narrativeIntro: String
    let startFen: String
    let moves: [ContentMove]

    var guessPoints: [ContentMove] { moves.filter(\.isGuessPoint) }
    var guessPointCount: Int { guessPoints.count }
    var heroName: String { heroColor == .white ? white : black }
    var subtitle: String { "\(white) vs. \(black) · \(event) · \(year)" }
}

/// One half-move (ply). For guess points it also carries the data the loop needs:
/// candidate evals (to score the guess) and a placeholder annotation.
struct ContentMove: Identifiable {
    let ply: Int               // 1-based half-move index
    let uci: String            // the move actually played (the master move at guess points)
    let san: String
    let fenBefore: String      // position before this move — what the user sees at a guess point
    let mover: PieceColor
    let isGuessPoint: Bool
    let tags: [GuessTag]
    let annotation: String?    // why the master move works (placeholder in M1)
    /// uci -> eval cp from the mover's POV (higher = better). The best candidate is the max.
    /// M1: only a few entries (master + maybe one alt). M2 fills EVERY legal move (TECH_SPEC §4).
    let candidateEvals: [String: Int]
    /// Guess-point difficulty for the rating model (TECH_SPEC §3.3). Placeholder in M1.
    let difficulty: Double

    var id: Int { ply }
    /// Best (highest) candidate eval; nil if none recorded.
    var bestEvalCp: Int? { candidateEvals.values.max() }

    init(
        ply: Int,
        uci: String,
        san: String,
        fenBefore: String,
        mover: PieceColor,
        isGuessPoint: Bool,
        tags: [GuessTag],
        annotation: String?,
        candidateEvals: [String: Int],
        difficulty: Double = 1200
    ) {
        self.ply = ply
        self.uci = uci
        self.san = san
        self.fenBefore = fenBefore
        self.mover = mover
        self.isGuessPoint = isGuessPoint
        self.tags = tags
        self.annotation = annotation
        self.candidateEvals = candidateEvals
        self.difficulty = difficulty
    }
}

/// Weakness-breakdown tags (TECH_SPEC §3.3).
enum GuessTag: String, CaseIterable {
    case tactical, positional, endgame, opening, defense

    var label: String { rawValue.capitalized }
}
