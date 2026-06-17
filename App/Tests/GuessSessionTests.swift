import XCTest
@testable import Brilliancy

/// Integration tests for the GuessSession state machine over the hardcoded sample game.
/// Exercises ChessGame (ChessKit) move application as a side effect, so a desync in the
/// move loop fails here — guess-point gating + stepped autoplay (TECH_SPEC §3.1, UI_FLOW §4).
final class GuessSessionTests: XCTestCase {

    private func makeModel() -> GuessSessionModel {
        GuessSessionModel(game: SampleGames.gameOfTheCentury)
    }

    /// Synchronously drain autoplay (the view does this on a timer; tests do it inline).
    private func drainAutoplay(_ model: GuessSessionModel, max: Int = 200) {
        var safety = 0
        while model.phase == .autoplaying && safety < max {
            model.stepAutoplay()
            safety += 1
        }
    }

    func testStartsInContextAtStartingPosition() {
        let model = makeModel()
        XCTAssertEqual(model.phase, .context)
        XCTAssertEqual(model.index, 0)
        XCTAssertEqual(model.board.sideToMove, .white)
    }

    func testBeginEntersAutoplayWithoutJumpCut() {
        let model = makeModel()
        model.begin()
        // UI_FLOW §4: never jump-cut — begin() must NOT have applied any moves yet.
        XCTAssertEqual(model.phase, .autoplaying)
        XCTAssertEqual(model.index, 0)
        XCTAssertEqual(model.board.sideToMove, .white)

        // One tick applies exactly one move.
        model.stepAutoplay()
        XCTAssertEqual(model.index, 1)
        XCTAssertEqual(model.board.sideToMove, .black)
    }

    func testAutoplayStopsAtFirstGuessPoint() {
        let model = makeModel()
        model.begin()
        drainAutoplay(model)
        XCTAssertEqual(model.phase, .awaitingGuess)
        XCTAssertEqual(model.currentMove?.ply, 22)
        XCTAssertEqual(model.currentMove?.san, "Na4")
        // Hero is Black, so it's Black to move at the guess point.
        XCTAssertEqual(model.board.sideToMove, .black)
    }

    func testCorrectGuessScoresMatchAndReveals() throws {
        let model = makeModel()
        model.begin()
        drainAutoplay(model)
        let from = try XCTUnwrap(Sq(name: "b6"))
        let to = try XCTUnwrap(Sq(name: "a4"))

        model.submitGuess(from: from, to: to)

        XCTAssertEqual(model.phase, .revealed)
        XCTAssertEqual(model.results.count, 1)
        XCTAssertEqual(model.lastEvaluation?.displayPoints, 100)
        XCTAssertEqual(model.lastEvaluation?.isMatch, true)
        XCTAssertGreaterThan(model.rating, model.startRating) // rating went up
        XCTAssertGreaterThan(model.lastRatingDelta ?? 0, 0)   // and the gain is shown per move
    }

    func testWrongLegalGuessScoresLowAndDropsRating() throws {
        let model = makeModel()
        model.begin()
        drainAutoplay(model)
        // a7-a6 is legal here but not Fischer's Na4, and not in candidateEvals -> blunder.
        let from = try XCTUnwrap(Sq(name: "a7"))
        let to = try XCTUnwrap(Sq(name: "a6"))

        model.submitGuess(from: from, to: to)

        XCTAssertEqual(model.results.first?.evaluation.displayPoints, 0)
        XCTAssertEqual(model.results.first?.evaluation.band, .red)
        XCTAssertLessThan(model.rating, model.startRating)
        XCTAssertLessThan(model.lastRatingDelta ?? 0, 0)      // miss visibly costs rating
    }

    func testProceedReplaysMasterMoveThenAdvances() throws {
        let model = makeModel()
        model.begin()
        drainAutoplay(model)
        model.submitGuess(from: try XCTUnwrap(Sq(name: "b6")), to: try XCTUnwrap(Sq(name: "a4")))
        model.proceed()

        // proceed() re-enters autoplay; the FIRST tick plays the master move itself.
        XCTAssertEqual(model.phase, .autoplaying)
        XCTAssertNil(model.lastRatingDelta)   // per-move delta cleared on advance
        let indexBefore = model.index
        model.stepAutoplay()
        XCTAssertEqual(model.index, indexBefore + 1)

        drainAutoplay(model)
        XCTAssertEqual(model.phase, .awaitingGuess)
        XCTAssertEqual(model.currentMove?.san, "Nxe4") // ply 26, the next guess point
    }

    func testWeakestResultAndRedCountDriveUpsell() throws {
        // One miss (ply 22) then a correct move (ply 26): the upsell should point at
        // the miss (TECH_SPEC §6 dynamic post-daily card).
        let model = makeModel()
        model.begin()
        drainAutoplay(model)
        model.submitGuess(from: try XCTUnwrap(Sq(name: "a7")), to: try XCTUnwrap(Sq(name: "a6"))) // 0 pts, red
        model.proceed()
        drainAutoplay(model)
        let next = try XCTUnwrap(model.currentMove)
        let parsed = try XCTUnwrap(ChessGame.parse(uci: next.uci))
        model.submitGuess(from: parsed.from, to: parsed.to)                                       // 100 pts

        let weakest = try XCTUnwrap(model.weakestResult)
        XCTAssertEqual(weakest.ply, 22)
        XCTAssertEqual(weakest.evaluation.displayPoints, 0)
        XCTAssertEqual(model.redMissCount, 1)
        XCTAssertEqual(model.moveNumber(forPly: 22), 11)
    }

    func testWeakestResultIsNilWithNoGuesses() {
        XCTAssertNil(makeModel().weakestResult)
        XCTAssertEqual(makeModel().redMissCount, 0)
    }

    func testPlayingAllMasterMovesReachesPerfectSummary() {
        let model = makeModel()
        model.begin()

        var safety = 0
        while model.phase != .summary && safety < 400 {
            safety += 1
            switch model.phase {
            case .autoplaying:
                model.stepAutoplay()
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
