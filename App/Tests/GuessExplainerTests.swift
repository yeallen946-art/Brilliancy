import XCTest
@testable import Brilliancy

/// The "your move" card (PRD section 6). Three cases: master match -> nil (merged
/// into the master card); engine-equal/better -> positive explanation; worse -> why
/// it falls short. Prose comes from alt_annotations; templates state engine facts only.
final class GuessExplainerTests: XCTestCase {

    private let startFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    private func makePoint(
        masterUci: String = "e2e4",
        masterSan: String = "e4",
        candidateEvals: [String: Int],
        candidateDetails: [String: CandidateDetail] = [:],
        altAnnotations: [String: String] = [:]
    ) -> ContentMove {
        ContentMove(
            ply: 1, uci: masterUci, san: masterSan, fenBefore: startFen, mover: .white,
            isGuessPoint: true, tags: [], annotation: "Master move prose.",
            candidateEvals: candidateEvals,
            candidateDetails: candidateDetails,
            altAnnotations: altAnnotations
        )
    }

    private func explain(_ guessUci: String, point: ContentMove) -> GuessExplainer.Explanation? {
        let evaluation = Scoring.evaluate(
            guessUci: guessUci,
            masterUci: point.uci,
            candidateEvals: point.candidateEvals
        )
        return GuessExplainer.explanation(guessUci: guessUci, evaluation: evaluation, point: point)
    }

    // MARK: - Master match: single merged card

    func testNoCardWhenMatchingTheMaster() throws {
        let point = makePoint(candidateEvals: ["e2e4": 30, "d2d4": -100])
        XCTAssertNil(explain("e2e4", point: point))
    }

    // MARK: - Engine-equal / better: positive explanation

    func testEngineTopGuessPrefersAltProse() throws {
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "g1f3": 25],
            candidateDetails: ["g1f3": CandidateDetail(san: "Nf3", refutationSan: [], motif: "best")],
            altAnnotations: ["g1f3": "Equally strong: it develops with tempo."]
        )
        let explanation = try XCTUnwrap(explain("g1f3", point: point))
        XCTAssertEqual(explanation.guessSan, "Nf3")
        XCTAssertEqual(explanation.text, "Equally strong: it develops with tempo.")
    }

    func testEngineTopGuessTemplateWithoutProse() throws {
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "g1f3": 25],
            candidateDetails: ["g1f3": CandidateDetail(san: "Nf3", refutationSan: [], motif: "best")]
        )
        let text = try XCTUnwrap(explain("g1f3", point: point)).text
        XCTAssertTrue(text.contains("just as strong"), text)
        XCTAssertTrue(text.contains("+0.2"), text)        // the guess's own eval, in pawns
    }

    func testBeatMasterUsesEngineNumbersNotAltProse() throws {
        // Alt prose is written from a "why it is worse" angle — must not be shown
        // when the engine PREFERS the user's move.
        let point = makePoint(
            candidateEvals: ["e2e4": 10, "d2d4": 60],
            candidateDetails: ["d2d4": CandidateDetail(san: "d4", refutationSan: [], motif: "best")],
            altAnnotations: ["d2d4": "Worse because reasons (stale prose)."]
        )
        let text = try XCTUnwrap(explain("d2d4", point: point)).text
        XCTAssertTrue(text.contains("engine actually prefers d4"), text)
        XCTAssertTrue(text.contains("+0.6") && text.contains("+0.1"), text)
        XCTAssertFalse(text.contains("stale prose"), text)
    }

    func testEqualMateGuessPraisedAsAlsoForcingMate() throws {
        let mate2 = ContentStore.mateBaseCp - 200
        let point = makePoint(
            candidateEvals: ["e2e4": mate2, "d2d4": mate2],
            candidateDetails: ["d2d4": CandidateDetail(san: "d4", refutationSan: [], motif: "best")]
        )
        let text = try XCTUnwrap(explain("d2d4", point: point)).text
        XCTAssertTrue(text.contains("also forces mate"), text)
        XCTAssertFalse(text.contains("pawns"), text)
    }

    // MARK: - Worse: content priority

    func testPipelineProsePreferredOverTemplate() throws {
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "f2f3": -200],
            candidateDetails: ["f2f3": CandidateDetail(san: "f3", refutationSan: ["e5"], motif: "blunder")],
            altAnnotations: ["f2f3": "This weakens your king for nothing."]
        )
        let explanation = try XCTUnwrap(explain("f2f3", point: point))
        XCTAssertEqual(explanation.guessSan, "f3")
        XCTAssertEqual(explanation.text, "This weakens your king for nothing.")
    }

    func testTemplateUsedForLongTailMoves() throws {
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "a2a3": -90],
            candidateDetails: ["a2a3": CandidateDetail(san: "a3", refutationSan: ["d7d5-as-SAN", "x", "y", "z"], motif: "mistake")]
        )
        let explanation = try XCTUnwrap(explain("a2a3", point: point))
        XCTAssertEqual(explanation.guessSan, "a3")
        // delta = 30 - (-90) = 120cp -> "1.2 pawns"; refutation capped at 3 moves.
        XCTAssertTrue(explanation.text.contains("1.2 pawns"), explanation.text)
        XCTAssertTrue(explanation.text.contains("d7d5-as-SAN x y"), explanation.text)
        XCTAssertFalse(explanation.text.contains(" z"), explanation.text)
    }

    func testSharpSpotPrefixWhenOnlyBestMoveHeld() throws {
        // Only the master move avoids a blunder (a2a3 is 4.3 pawns worse) -> the card
        // frames the 0 as a sharp spot, grounded in the candidate evals.
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "a2a3": -400],
            candidateDetails: ["a2a3": CandidateDetail(san: "a3", refutationSan: ["e5"], motif: "blunder")]
        )
        let text = try XCTUnwrap(explain("a2a3", point: point)).text
        XCTAssertTrue(text.contains("sharp spot"), text)
        XCTAssertTrue(text.contains("4.3 pawns"), text)   // still states the engine fact
    }

    func testNoSharpSpotPrefixWhenOtherMovesHold() throws {
        // a2a3 is only 1.2 pawns worse and within the non-blunder band -> not sharp.
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "a2a3": -90, "b2b3": -100],
            candidateDetails: ["a2a3": CandidateDetail(san: "a3", refutationSan: [], motif: "mistake")]
        )
        let text = try XCTUnwrap(explain("a2a3", point: point)).text
        XCTAssertFalse(text.contains("sharp spot"), text)
    }

    func testGuessSanFallsBackToUciWithoutEnrichment() throws {
        let point = makePoint(candidateEvals: ["e2e4": 30, "a2a3": -90])
        let explanation = try XCTUnwrap(explain("a2a3", point: point))
        XCTAssertEqual(explanation.guessSan, "a2a3")
    }

    // MARK: - Mate-aware phrasing (clamped evals, no absurd pawn counts)

    func testTemplateWhenGuessGetsMated() throws {
        let mated = -ContentStore.mateBaseCp + 200   // mated in 2
        let point = makePoint(
            candidateEvals: ["e2e4": 30, "g2g4": mated],
            candidateDetails: ["g2g4": CandidateDetail(san: "g4", refutationSan: ["e6", "Qh4#"], motif: "blunder")]
        )
        let text = try XCTUnwrap(explain("g2g4", point: point)).text
        XCTAssertTrue(text.contains("forced mate against you"), text)
        XCTAssertTrue(text.contains("e6 Qh4#"), text)
        XCTAssertFalse(text.contains("pawns"), text)
    }

    func testTemplateWhenMissingAForcedMate() throws {
        let mating = ContentStore.mateBaseCp - 300   // master mates in 3
        let point = makePoint(
            candidateEvals: ["e2e4": mating, "a2a3": 50],
            candidateDetails: ["a2a3": CandidateDetail(san: "a3", refutationSan: [], motif: "mistake")]
        )
        let text = try XCTUnwrap(explain("a2a3", point: point)).text
        XCTAssertTrue(text.contains("forced mate slip"), text)
        XCTAssertFalse(text.contains("pawns"), text)
    }
}
