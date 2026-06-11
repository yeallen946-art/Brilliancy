import XCTest
@testable import Brilliancy

/// "Why your move falls short" (PRD section 6). Prose comes from alt_annotations; the
/// long-tail template only states engine facts (eval delta + refutation SAN).
final class WrongGuessExplainerTests: XCTestCase {

    private let startFen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    private func makePoint(
        masterUci: String = "e2e4",
        candidateEvals: [String: Int],
        candidateDetails: [String: CandidateDetail] = [:],
        altAnnotations: [String: String] = [:]
    ) -> ContentMove {
        ContentMove(
            ply: 1, uci: masterUci, san: "e4", fenBefore: startFen, mover: .white,
            isGuessPoint: true, tags: [], annotation: "Master move prose.",
            candidateEvals: candidateEvals,
            candidateDetails: candidateDetails,
            altAnnotations: altAnnotations
        )
    }

    private func explain(_ guessUci: String, point: ContentMove) -> WrongGuessExplainer.Explanation? {
        let evaluation = Scoring.evaluate(
            guessUci: guessUci,
            masterUci: point.uci,
            candidateEvals: point.candidateEvals
        )
        return WrongGuessExplainer.explanation(guessUci: guessUci, evaluation: evaluation, point: point)
    }

    // MARK: - When NO explanation is owed

    func testNoExplanationForMatchEngineTopOrBeatMaster() throws {
        // match
        var point = makePoint(candidateEvals: ["e2e4": 30, "d2d4": -100])
        XCTAssertNil(explain("e2e4", point: point))
        // engine-top non-match (tied with best)
        point = makePoint(candidateEvals: ["e2e4": 30, "g1f3": 25])
        XCTAssertNil(explain("g1f3", point: point))
        // beat the master
        point = makePoint(candidateEvals: ["e2e4": 10, "d2d4": 60])
        XCTAssertNil(explain("d2d4", point: point))
    }

    // MARK: - Content priority

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

    func testGuessSanFallsBackToUciWithoutEnrichment() throws {
        let point = makePoint(candidateEvals: ["e2e4": 30, "a2a3": -90])
        let explanation = try XCTUnwrap(explain("a2a3", point: point))
        XCTAssertEqual(explanation.guessSan, "a2a3")
    }

    // MARK: - Mate-aware phrasing (clamped evals, no absurd pawn counts)

    func testTemplateWhenGuessGetsMated() throws {
        // mated in 2 -> clamped to -mateBase + 200
        let mated = -ContentStore.mateBaseCp + 200
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
