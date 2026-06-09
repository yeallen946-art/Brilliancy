import XCTest
@testable import Brilliancy

/// Table-driven tests for the scoring + rating math (TECH_SPEC §3.2 / §3.3, CLAUDE.md).
final class ScoringTests: XCTestCase {

    private let config = ScoringConfig.default

    func testQualityScoreBuckets() {
        // (eval_delta cp, expected points) at and just past each boundary.
        let cases: [(Int, Int)] = [
            (-50, 100), (0, 100), (10, 100),
            (11, 90), (40, 90),
            (41, 70), (80, 70),
            (81, 45), (150, 45),
            (151, 20), (300, 20),
            (301, 0), (5000, 0),
        ]
        for (delta, expected) in cases {
            XCTAssertEqual(Scoring.qualityScore(evalDeltaCp: delta), expected, "delta \(delta)")
        }
    }

    func testMatchScoresFullAndFlagsMatch() {
        let eval = Scoring.evaluate(guessUci: "e2e4", masterUci: "e2e4", candidateEvals: ["e2e4": 0])
        XCTAssertEqual(eval.displayPoints, 100)
        XCTAssertEqual(eval.qualityPoints, 100)
        XCTAssertTrue(eval.flags.contains(.match))
        XCTAssertEqual(eval.band, .green)
        XCTAssertEqual(eval.label, "Match!")
    }

    func testBeatMasterWhenEnginePrefersGuess() {
        // master eval -30, user's move eval 0 (better) -> beats master, full marks.
        let eval = Scoring.evaluate(
            guessUci: "g", masterUci: "m", candidateEvals: ["m": -30, "g": 0]
        )
        XCTAssertEqual(eval.displayPoints, 100)
        XCTAssertTrue(eval.flags.contains(.beatMaster))
        XCTAssertFalse(eval.flags.contains(.match))
        XCTAssertEqual(eval.band, .green)
    }

    func testMasterFloorRescuesDisplayButNotRating() {
        // Master move is engine-suboptimal: best 0, master -100 (delta 100 -> quality 45).
        // Matching it still shows 100 (floor), but the rating must use the objective 45.
        let eval = Scoring.evaluate(
            guessUci: "m", masterUci: "m", candidateEvals: ["best": 0, "m": -100]
        )
        XCTAssertEqual(eval.displayPoints, 100, "master-match floor")
        XCTAssertEqual(eval.qualityPoints, 45, "rating uses objective quality")
        XCTAssertTrue(eval.flags.contains(.match))
    }

    func testGoodAlternativeIsGreenYellowRedByDelta() {
        let good = Scoring.evaluate(guessUci: "g", masterUci: "m", candidateEvals: ["m": 0, "g": -50])
        XCTAssertEqual(good.displayPoints, 70)
        XCTAssertEqual(good.band, .green)

        let yellow = Scoring.evaluate(guessUci: "g", masterUci: "m", candidateEvals: ["m": 0, "g": -120])
        XCTAssertEqual(yellow.displayPoints, 45)
        XCTAssertEqual(yellow.band, .yellow)

        let red = Scoring.evaluate(guessUci: "g", masterUci: "m", candidateEvals: ["m": 0, "g": -400])
        XCTAssertEqual(red.displayPoints, 0)
        XCTAssertEqual(red.band, .red)
    }

    func testMissingMoveFallsBackToBlunder() {
        // M1 placeholder: a legal guess not present in candidateEvals scores as a blunder.
        let eval = Scoring.evaluate(guessUci: "x", masterUci: "m", candidateEvals: ["m": 0])
        XCTAssertEqual(eval.displayPoints, 0)
        XCTAssertEqual(eval.band, .red)
    }

    func testExpectedScoreSymmetry() {
        XCTAssertEqual(GuessRating.expectedScore(rating: 1200, difficulty: 1200), 0.5, accuracy: 1e-9)
        XCTAssertGreaterThan(GuessRating.expectedScore(rating: 1600, difficulty: 1200), 0.5)
        XCTAssertLessThan(GuessRating.expectedScore(rating: 800, difficulty: 1200), 0.5)
    }

    func testRatingUpdateDirectionAndK() {
        // priorGuessCount < 100 -> fast K (24), E = 0.5 when rating == difficulty.
        let up = GuessRating.updated(rating: 1200, difficulty: 1200, qualityPoints: 100, priorGuessCount: 0)
        XCTAssertEqual(up, 1212, accuracy: 1e-9)

        let down = GuessRating.updated(rating: 1200, difficulty: 1200, qualityPoints: 0, priorGuessCount: 0)
        XCTAssertEqual(down, 1188, accuracy: 1e-9)

        // priorGuessCount >= 100 -> standard K (16).
        let slow = GuessRating.updated(rating: 1200, difficulty: 1200, qualityPoints: 100, priorGuessCount: 100)
        XCTAssertEqual(slow, 1208, accuracy: 1e-9)
    }
}
