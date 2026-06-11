import Foundation

/// "Why your move falls short" for the reveal screen (PRD §6: explain the wrong
/// guess, not just the master move). Content priority per TECH_SPEC §4:
///   1. Pipeline prose (alt_annotations) for the interesting wrong moves.
///   2. Long tail: a deterministic template over precomputed engine data only
///      (eval delta + refutation SAN). This is the spec-sanctioned runtime
///      templating — it states engine facts, it never invents chess commentary
///      (CLAUDE.md hard rule #1 stays intact).
enum WrongGuessExplainer {

    struct Explanation: Equatable {
        let guessSan: String   // "Qxf7", falls back to UCI if the DB predates enrichment
        let text: String
    }

    /// How many refutation moves to show — enough to see the punishment, not a wall.
    static let refutationMovesShown = 3

    /// Evals at/over this magnitude mean a forced mate is on the board
    /// (ContentStore clamps mate scores around mateBaseCp).
    static let mateThresholdCp = ContentStore.mateBaseCp - 10000

    /// nil when no explanation is owed: the user matched the master, found an
    /// engine-top move, or outscored the master — those cases are praised, not explained.
    static func explanation(
        guessUci: String,
        evaluation: GuessEvaluation,
        point: ContentMove
    ) -> Explanation? {
        guard !evaluation.isMatch,
              !evaluation.flags.contains(.engineTop),
              !evaluation.flags.contains(.beatMaster)
        else { return nil }

        let detail = point.candidateDetails[guessUci]
        let guessSan = detail?.san ?? guessUci

        if let prose = point.altAnnotations[guessUci] {
            return Explanation(guessSan: guessSan, text: prose)
        }
        return Explanation(
            guessSan: guessSan,
            text: templated(
                guessSan: guessSan,
                guessEvalCp: point.candidateEvals[guessUci],
                evalDeltaCp: evaluation.evalDeltaCp,
                refutationSan: detail?.refutationSan ?? []
            )
        )
    }

    /// Engine-facts-only fallback text. Coach tone, no chess claims beyond the numbers.
    static func templated(
        guessSan: String,
        guessEvalCp: Int?,
        evalDeltaCp: Int,
        refutationSan: [String]
    ) -> String {
        let line = refutationSan.prefix(refutationMovesShown).joined(separator: " ")

        // Mate-aware phrasing (clamped evals make pawn units meaningless here).
        if let eval = guessEvalCp, eval <= -mateThresholdCp {
            return line.isEmpty
                ? "After \(guessSan), the engine finds a forced mate against you."
                : "After \(guessSan), \(line) leads to a forced mate against you."
        }
        if evalDeltaCp >= mateThresholdCp {
            return "\(guessSan) lets a forced mate slip away \u{2014} the winning idea is still on the board."
        }

        let pawns = String(format: "%.1f", Double(evalDeltaCp) / 100.0)
        if line.isEmpty {
            return "After \(guessSan), the engine puts you about \(pawns) pawns short of the best move here."
        }
        return "After \(guessSan), the strongest reply is \(line), leaving you about \(pawns) pawns short of the best move here."
    }
}
