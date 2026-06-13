import Foundation

/// Runtime content model for one master game. In M1 this is populated by a hardcoded
/// Swift literal (`SampleGames`); in M2 the pipeline builds it into content.sqlite and
/// the app decodes equivalent rows (TECH_SPEC §4). Kept deliberately close to the DB shape.
struct GameContent: Identifiable {
    /// Pack membership (S5/S6); nil for unpacked games. Declared first so the
    /// memberwise init keeps existing call sites (which omit it) unchanged.
    var packId: String? = nil
    /// Curated free-tier sample (TECH_SPEC §6). Defaulted like packId so existing
    /// call sites / Swift literals that omit it stay valid.
    var isSample: Bool = false
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
    var heroDisplayName: String {
        if let comma = heroName.firstIndex(of: ",") {
            return String(heroName[..<comma]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return heroName.split(separator: " ").last.map(String.init) ?? heroName
    }
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
    /// uci -> display info per candidate, all PRECOMPUTED by the pipeline (build.py
    /// enrich_legal_evals): the move's own SAN, the refutation line in SAN, motif.
    /// Display-only; scoring stays on candidateEvals.
    let candidateDetails: [String: CandidateDetail]
    /// uci -> pipeline prose for the "interesting" wrong moves (TECH_SPEC §4
    /// alt_annotations). Long-tail moves are absent here and get a runtime template
    /// built from engine data (WrongGuessExplainer) — never freestyle commentary.
    let altAnnotations: [String: String]
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
        candidateDetails: [String: CandidateDetail] = [:],
        altAnnotations: [String: String] = [:],
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
        self.candidateDetails = candidateDetails
        self.altAnnotations = altAnnotations
        self.difficulty = difficulty
    }
}

/// Display-only facts about one candidate move at a guess point, precomputed by the
/// pipeline (no SAN generation on device — TECH_SPEC §10).
struct CandidateDetail: Equatable {
    let san: String?
    let refutationSan: [String]
    let motif: String?
}

/// Pack metadata (S5/S6, TECH_SPEC §4 packs table).
struct ContentPack: Identifiable {
    let id: String
    let name: String
    let kind: String          // player | theme | daily_archive
    let description: String
    let priceTier: String     // free | premium (display only; gating stays per-game)
    let sortOrder: Int
    /// Short skill-promise (TECH_SPEC §6): what the user gets better AT. Empty = none.
    /// Defaulted so call sites that predate the field stay valid.
    var promise: String = ""
}

/// Weakness-breakdown tags (TECH_SPEC §3.3).
enum GuessTag: String, CaseIterable {
    case tactical, positional, endgame, opening, defense

    var label: String { rawValue.capitalized }
}
