import Foundation

// Scoring + guess-rating math (TECH_SPEC §3.2 / §3.3). PURE functions, table-driven tests.
// ALL tunable constants live in ScoringConfig — never inline scoring numbers elsewhere
// (CLAUDE.md). The core principle (§3.2): a guess is scored on the OBJECTIVE quality of
// the move (engine), with matching the master as a floor, never the cap.

/// All scoring/rating constants in one place. Tune during TestFlight.
struct ScoringConfig {
    // qualityScore buckets: max eval_delta (cp) for each tier, and the points awarded.
    var bucketBest = 10        // engine-best or tied
    var bucketExcellent = 40
    var bucketGood = 80
    var bucketInaccuracy = 150
    var bucketMistake = 300    // above this -> blunder

    var pointsBest = 100
    var pointsExcellent = 90
    var pointsGood = 70
    var pointsInaccuracy = 45
    var pointsMistake = 20
    var pointsBlunder = 0

    /// Within this many cp of the best move counts as "engine top".
    var engineTopToleranceCp = 10

    /// M1 ONLY: a guess not present in candidateEvals is treated as this eval_delta.
    /// In M2 every legal move is in legal_evals, so this fallback never triggers (TECH_SPEC §10).
    var missingMoveDeltaCp = 1000

    // Rating (Elo-like, §3.3).
    var startRating = 1200.0
    var standardK = 16.0
    var fastK = 24.0           // first N guesses move faster (generous early curve, PRD §4.3)
    var fastGuessThreshold = 100

    static let `default` = ScoringConfig()
}

/// 3-tier feedback band (color + accessible icon, UI_FLOW §4 — never color alone).
enum ScoreBand {
    case green   // match / engine-best / good
    case yellow  // playable but not best
    case red     // mistake / blunder

    var icon: String {
        switch self {
        case .green:  return "\u{2713}"   // ✓
        case .yellow: return "\u{2248}"   // ≈
        case .red:    return "\u{2717}"   // ✗
        }
    }

    /// Emoji square for the summary/share band (TECH_SPEC §7, no move spoilers).
    var emoji: String {
        switch self {
        case .green:  return "\u{1F7E9}"  // 🟩
        case .yellow: return "\u{1F7E8}"  // 🟨
        case .red:    return "\u{1F7E5}"  // 🟥
        }
    }
}

enum GuessFlag {
    case match        // played the master's move
    case beatMaster   // engine prefers the user's move over the master's
    case engineTop    // user's move is (tied for) engine-best
}

/// Outcome of scoring one guess.
struct GuessEvaluation {
    let displayPoints: Int      // shown to the user (after master-match floor)
    let qualityPoints: Int      // OBJECTIVE quality only — drives the rating (§3.3)
    let evalDeltaCp: Int        // how far from best (>= 0), for "(-0.8)" style display
    let band: ScoreBand
    let flags: Set<GuessFlag>
    let label: String           // short coach-tone feedback

    var isMatch: Bool { flags.contains(.match) }
}

enum Scoring {

    /// Objective move quality from eval_delta in centipawns (TECH_SPEC §3.2).
    static func qualityScore(evalDeltaCp delta: Int, config: ScoringConfig = .default) -> Int {
        let d = max(0, delta)
        if d <= config.bucketBest { return config.pointsBest }
        if d <= config.bucketExcellent { return config.pointsExcellent }
        if d <= config.bucketGood { return config.pointsGood }
        if d <= config.bucketInaccuracy { return config.pointsInaccuracy }
        if d <= config.bucketMistake { return config.pointsMistake }
        return config.pointsBlunder
    }

    /// Score a guess against a guess point's candidate evals.
    /// `candidateEvals`: uci -> eval cp (mover POV, higher better). Best move = max value.
    static func evaluate(
        guessUci: String,
        masterUci: String,
        candidateEvals: [String: Int],
        config: ScoringConfig = .default
    ) -> GuessEvaluation {
        let bestEval = candidateEvals.values.max()
        let masterEval = candidateEvals[masterUci] ?? bestEval

        let isMatch = guessUci == masterUci
        let guessEvalKnown = candidateEvals[guessUci]

        // eval_delta = best - guessEval, clamped >= 0. Missing move (M1 only) -> fallback.
        let delta: Int
        if let best = bestEval, let g = guessEvalKnown {
            delta = max(0, best - g)
        } else if isMatch {
            delta = 0
        } else {
            delta = config.missingMoveDeltaCp
        }

        let quality = qualityScore(evalDeltaCp: delta, config: config)
        let display = max(quality, isMatch ? config.pointsBest : 0)

        var flags: Set<GuessFlag> = []
        if isMatch { flags.insert(.match) }
        if let best = bestEval, let g = guessEvalKnown, best - g <= config.engineTopToleranceCp {
            flags.insert(.engineTop)
        }
        if !isMatch, let g = guessEvalKnown, let m = masterEval, g > m {
            flags.insert(.beatMaster)
        }

        return GuessEvaluation(
            displayPoints: display,
            qualityPoints: quality,
            evalDeltaCp: delta,
            band: computeBand(displayPoints: display, flags: flags, config: config),
            flags: flags,
            label: computeLabel(displayPoints: display, flags: flags, config: config)
        )
    }

    private static func computeBand(displayPoints points: Int, flags: Set<GuessFlag>, config: ScoringConfig) -> ScoreBand {
        if flags.contains(.match) || flags.contains(.beatMaster) { return .green }
        if points >= config.pointsGood { return .green }
        if points >= config.pointsInaccuracy { return .yellow }
        return .red
    }

    private static func computeLabel(displayPoints points: Int, flags: Set<GuessFlag>, config: ScoringConfig) -> String {
        if flags.contains(.beatMaster) { return "You beat the master!" }
        if flags.contains(.match) { return "Match!" }
        switch points {
        case config.pointsBest:       return "Best move!"
        case config.pointsExcellent:  return "Excellent"
        case config.pointsGood:       return "Good move"
        case config.pointsInaccuracy: return "Inaccuracy"
        case config.pointsMistake:    return "Mistake"
        default:                      return "Blunder"
        }
    }
}

/// Elo-like guess rating (TECH_SPEC §3.3). The rating tracks OBJECTIVE quality
/// (qualityPoints), not the master-floored display score.
enum GuessRating {

    /// Expected normalized score for a player of `rating` facing a point of `difficulty`.
    static func expectedScore(rating: Double, difficulty: Double) -> Double {
        1.0 / (1.0 + pow(10.0, (difficulty - rating) / 400.0))
    }

    /// New rating after one guess. `qualityPoints` is 0…100; `priorGuessCount` selects K.
    static func updated(
        rating: Double,
        difficulty: Double,
        qualityPoints: Int,
        priorGuessCount: Int,
        config: ScoringConfig = .default
    ) -> Double {
        let s = Double(qualityPoints) / 100.0
        let k = priorGuessCount < config.fastGuessThreshold ? config.fastK : config.standardK
        let e = expectedScore(rating: rating, difficulty: difficulty)
        return rating + k * (s - e)
    }
}
