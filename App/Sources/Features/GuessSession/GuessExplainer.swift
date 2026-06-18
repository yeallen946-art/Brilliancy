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

        // Mate-relevant misses use the deterministic mate-aware template even when prose
        // exists. The template states the squandered/allowed forced mate plainly and stays
        // spoiler-safe (it never names the still-unguessed mating line), whereas hand prose
        // can gloss a thrown-away mate as merely "still winning" (Jerry 2026-06-17: Qb7 at
        // Opera m16 read as "keeps a winning position" while it gave up mate in two).
        let squandersMate = evaluation.evalDeltaCp >= mateThresholdCp
        let allowsMate = (guessEvalCp ?? 0) <= -mateThresholdCp
        if !squandersMate, !allowsMate, let prose = point.altAnnotations[guessUci] {
            return Explanation(guessSan: guessSan, text: prose)
        }
        return Explanation(
            guessSan: guessSan,
            text: shortfallTemplate(
                guessSan: guessSan,
                guessEvalCp: guessEvalCp,
                masterEvalCp: point.candidateEvals[point.uci],
                evalDeltaCp: evaluation.evalDeltaCp,
                refutationSan: detail?.refutationSan ?? [],
                onlyMoveHeld: onlyBestMoveHeld(point)
            )
        )
    }

    /// True when only the engine-best move avoided a blunder at this point — a genuinely
    /// sharp position where a 0 is fair, not harsh. Grounded in the candidate evals (a
    /// deterministic engine fact, like the score itself — not commentary, hard rule #1):
    /// counts moves within the blunder threshold of best. Sparse/empty evals → false, so
    /// we never claim sharpness we can't actually see (e.g. an M1 row with one candidate).
    static func onlyBestMoveHeld(_ point: ContentMove) -> Bool {
        guard let best = point.candidateEvals.values.max(),
              point.candidateEvals.count >= 2 else { return false }
        let threshold = ScoringConfig.default.bucketMistake
        let held = point.candidateEvals.values.filter { best - $0 <= threshold }.count
        return held <= 1
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
        masterEvalCp: Int? = nil,
        evalDeltaCp: Int,
        refutationSan: [String],
        onlyMoveHeld: Bool = false
    ) -> String {
        let line = refutationSan.prefix(refutationMovesShown).joined(separator: " ")

        // Mate-aware phrasing (clamped evals make pawn units meaningless here). No sharp-
        // spot prefix needed — a forced mate already says the position was decisive.
        if let eval = guessEvalCp, eval <= -mateThresholdCp {
            return line.isEmpty
                ? "After \(guessSan), the engine finds a forced mate against you."
                : "After \(guessSan), \(line) leads to a forced mate against you."
        }
        // Squandered a forced mate. The finishing line is the next move the trainee still
        // has to guess, so we never show it. The bare "doesn't force mate" confused the
        // user ("I thought my move could mate too") — so TEACH the distinction: a winning
        // move still lets the opponent wriggle out of the mate, a forced mate leaves no way
        // out (Jerry 2026-06-17). "winning" vs "forced mate" is the lesson for 800-2000.
        if evalDeltaCp >= mateThresholdCp {
            let stillWinning = (guessEvalCp ?? 0) >= 200   // clearly better — the validator's "winning" bar
            let lead = stillWinning
                ? "\(guessSan) is still winning, but it doesn't force mate \u{2014} the defender still has a way out of the checkmate."
                : "\(guessSan) doesn't force mate \u{2014} the defender still has a way out of the checkmate."
            // Only credit the master's move with the mate when it IS the mating move; else
            // some other candidate was (never overclaim — chess correctness is sacred).
            let tail = (masterEvalCp ?? 0) >= mateThresholdCp
                ? " The master's move leaves none."
                : " A forced mate was on the board here."
            return lead + tail
        }

        // Frame a fair 0: when only the top move held, say so (grounded fact) before the
        // shortfall, so a low score reads as "this spot was sharp", not "you blundered".
        let prefix = onlyMoveHeld ? "A sharp spot \u{2014} only the top move held here. " : ""
        let shortfall = String(format: "%.1f", Double(evalDeltaCp) / 100.0)
        if line.isEmpty {
            return prefix + "After \(guessSan), the engine puts you about \(shortfall) pawns short of the best move here."
        }
        return prefix + "After \(guessSan), the strongest reply is \(line), leaving you about \(shortfall) pawns short of the best move here."
    }

    /// "+2.5" style signed pawn figure from a cp eval (mover's POV).
    private static func pawns(_ cp: Int) -> String {
        String(format: "%+.1f", Double(cp) / 100.0)
    }
}
