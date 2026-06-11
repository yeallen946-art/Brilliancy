import Foundation

/// The "your move" card on the reveal screen (PRD §6). Three cases (Jerry's spec,
/// 2026-06-11):
///   - Matched the master  -> nil: the master-annotation card covers it alone.
///   - Engine-equal or better than the master -> a POSITIVE explanation of the
///     user's move, shown alongside the master annotation.
///   - Worse -> why it falls short.
/// Content priority per TECH_SPEC §4: pipeline prose (alt_annotations) first, then a
/// deterministic template over precomputed engine data (eval delta + refutation SAN).
/// Templates state engine facts only — never invented commentary (hard rule #1).
enum GuessExplainer {

    struct Explanation: Equatable {
        let guessSan: String   // "Qxf7", falls back to UCI if the DB predates enrichment
        let text: String
    }

    /// How many refutation moves to show — enough to see the punishment, not a wall.
    static let refutationMovesShown = 3

    /// Evals at/over this magnitude mean a forced mate is on the board
    /// (ContentStore clamps mate scores around mateBaseCp).
    static let mateThresholdCp = ContentStore.mateBaseCp - 10000

    /// nil only when the user played the master move (single merged card).
    static func explanation(
        guessUci: String,
        evaluation: GuessEvaluation,
        point: ContentMove
    ) -> Explanation? {
        guard !evaluation.isMatch else { return nil }

        let detail = point.candidateDetails[guessUci]
        let guessSan = detail?.san ?? guessUci
        let guessEvalCp = point.candidateEvals[guessUci]

        // Good non-match: praise with engine numbers. The alt prose is written from a
        // "why it is worse" angle, so when the engine PREFERS the user's move the
        // numbers speak instead of the prose.
        if evaluation.flags.contains(.beatMaster) {
            return Explanation(
                guessSan: guessSan,
                text: praiseTemplate(
                    guessSan: guessSan, guessEvalCp: guessEvalCp,
                    masterSan: point.san, masterEvalCp: point.candidateEvals[point.uci],
                    beatMaster: true))
        }
        if evaluation.flags.contains(.engineTop) {
            return Explanation(
                guessSan: guessSan,
                text: point.altAnnotations[guessUci] ?? praiseTemplate(
                    guessSan: guessSan, guessEvalCp: guessEvalCp,
                    masterSan: point.san, masterEvalCp: point.candidateEvals[point.uci],
                    beatMaster: false))
        }

        if let prose = point.altAnnotations[guessUci] {
            return Explanation(guessSan: guessSan, text: prose)
        }
        return Explanation(
            guessSan: guessSan,
            text: shortfallTemplate(
                guessSan: guessSan,
                guessEvalCp: guessEvalCp,
                evalDeltaCp: evaluation.evalDeltaCp,
                refutationSan: detail?.refutationSan ?? []
            )
        )
    }

    /// Engine-facts praise for an equal-or-better non-match. Coach tone, numbers only.
    static func praiseTemplate(
        guessSan: String,
        guessEvalCp: Int?,
        masterSan: String,
        masterEvalCp: Int?,
        beatMaster: Bool
    ) -> String {
        if let eval = guessEvalCp, eval >= mateThresholdCp {
            return "\(guessSan) also forces mate \u{2014} every bit as deadly as \(masterSan)."
        }
        if beatMaster, let g = guessEvalCp, let m = masterEvalCp {
            return "The engine actually prefers \(guessSan): \(pawns(g)) against \(pawns(m)) for the master's \(masterSan)."
        }
        if let g = guessEvalCp {
            return "\(guessSan) is just as strong by the engine \u{2014} about \(pawns(g)), level with the master's \(masterSan)."
        }
        return "\(guessSan) is just as strong by the engine as the master's \(masterSan)."
    }

    /// Engine-facts-only fallback text for a weaker move. No claims beyond the numbers.
    static func shortfallTemplate(
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

        let shortfall = String(format: "%.1f", Double(evalDeltaCp) / 100.0)
        if line.isEmpty {
            return "After \(guessSan), the engine puts you about \(shortfall) pawns short of the best move here."
        }
        return "After \(guessSan), the strongest reply is \(line), leaving you about \(shortfall) pawns short of the best move here."
    }

    /// "+2.5" style signed pawn figure from a cp eval (mover's POV).
    private static func pawns(_ cp: Int) -> String {
        String(format: "%+.1f", Double(cp) / 100.0)
    }
}
