import XCTest
@testable import Brilliancy

/// Integration tests for the GuessSession state machine over the hardcoded sample game.
/// Exercises ChessGame (ChessKit) move application as a side effect, so a desync in the
/// move loop fails here — guess-point gating + autoplay correctness (TECH_SPEC §3.1).
final class GuessSessionTests: XCTestCase {

    private func makeModel() -> GuessSessionModel {
        GuessSessionModel(game: SampleGames.gameOfTheCentury)
    }

    func testStartsInContextAtStartingPosition() {
        let model = makeModel()
        XCTAssertEqual(model.phase, .context)
        XCTAssertEqual(model.index, 0)
        XCTAssertEqual(model.board.sideToMove, .white)
    }

    func testBeginAutoplaysToFirstGuessPoint() {
        let model = makeModel()
        model.begin()
        XCTAssertEqual(model.phase, .awaitingGuess)
        XCTAssertEqual(model.currentMove?.ply, 22)
        XCTAssertEqual(model.currentMove?.san, "Na4")
        // Hero is Black, so it's Black to move at the guess point.
        XCTAssertEqual(model.board.sideToMove, .black)
    }

    func testCorrectGuessScoresMatchAndReveals() throws {
        let model = makeModel()
        model.begin()
        let from = try XCTUnwrap(Sq(name: "b6"))
        let to = try XCTUnwrap(Sq(name: "a4"))

        model.submitGuess(from: from, to: to)

        XCTAssertEqual(model.phase, .revealed)
        XCTAssertEqual(model.results.count, 1)
        XCTAssertEqual(model.lastEvaluation?.displayPoints, 100)
        XCTAssertEqual(model.lastEvaluation?.isMatch, true)
        XCTAssertGreaterThan(model.rating, model.startRating) // rating went up
    }

    func testWrongLegalGuessScoresLowAndDropsRating() throws {
        let model = makeModel()
        model.begin()
        // a7-a6 is legal here but not Fischer's Na4, and not in candidateEvals -> blunder.
        let from = try XCTUnwrap(Sq(name: "a7"))
        let to = try XCTUnwrap(Sq(name: "a6"))

        model.submitGuess(from: from, to: to)

        XCTAssertEqual(model.results.first?.evaluation.displayPoints, 0)
        XCTAssertEqual(model.results.first?.evaluation.band, .red)
        XCTAssertLessThan(model.rating, model.startRating)
    }

    func testProceedAdvancesToNextGuessPoint() throws {
        let model = makeModel()
        model.begin()
        model.submitGuess(from: try XCTUnwrap(Sq(name: "b6")), to: try XCTUnwrap(Sq(name: "a4")))
        model.proceed()
        XCTAssertEqual(model.phase, .awaitingGuess)
        XCTAssertEqual(model.currentMove?.san, "Nxe4") // ply 26, the next guess point
    }

    func testPlayingAllMasterMovesReachesPerfectSummary() {
        let model = makeModel()
        model.begin()

        var safety = 0
        while model.phase != .summary && safety < 100 {
            safety += 1
            switch model.phase {
            case .awaitingGuess:
                guard let move = model.currentMove,
                      let parsed = ChessGame.parse(uci: move.uci) else {
                    return XCTFail("missing current move / uci")
                }
                model.submitGuess(from: parsed.from, to: parsed.to)
            case .revealed:
                model.proceed()
            default:
                break
            }
        }

        XCTAssertEqual(model.phase, .summary)
        XCTAssertEqual(model.results.count, model.game.guessPointCount)
        XCTAssertEqual(model.results.count, 7)
        XCTAssertTrue(model.results.allSatisfy { $0.evaluation.displayPoints == 100 })
        XCTAssertEqual(model.totalScore, 100)
        XCTAssertGreaterThan(model.rating, model.startRating)
    }
}
