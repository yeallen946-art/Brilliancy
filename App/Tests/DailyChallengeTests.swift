import XCTest
@testable import Brilliancy

/// Daily-challenge JSON decoding against a fixture in the exact pipeline shape
/// (build.daily_payload). Keep the fixture in sync with pipeline/build.py.
final class DailyChallengeTests: XCTestCase {

    private let fixture = """
    {
      "daily_id": "2026-06-10",
      "game": {
        "id": "test-game",
        "white": "White, W.",
        "black": "Black, B.",
        "event": "Test Event",
        "year": 1910,
        "result": "1-0",
        "eco": "B15",
        "hero_color": "black",
        "title": "A Test Game",
        "narrative_intro": "Some context.",
        "ply_count": 2,
        "moves": [
          {
            "ply": 1, "san": "e4", "uci": "e2e4",
            "fen_before": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "is_guess_point": false, "difficulty": 1200.0, "tags": [],
            "eval_cp": null, "eval_mate": null,
            "legal_evals": {}, "annotation": null, "alt_annotations": {}
          },
          {
            "ply": 2, "san": "e5", "uci": "e7e5",
            "fen_before": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            "is_guess_point": true, "difficulty": 1450.0, "tags": ["tactical"],
            "eval_cp": 30, "eval_mate": null,
            "legal_evals": {
              "e7e5": {"cp": 30, "mate": null, "refutation_pv": [], "motif": "best"},
              "d7d5": {"cp": null, "mate": 2, "refutation_pv": [], "motif": "best"}
            },
            "annotation": "A fine move.", "alt_annotations": {}
          }
        ]
      }
    }
    """

    func testDecodesPipelineShape() throws {
        let game = try XCTUnwrap(DailyChallenge.gameContent(fromJson: Data(fixture.utf8)))
        XCTAssertEqual(game.id, "test-game")
        XCTAssertEqual(game.title, "A Test Game")
        XCTAssertEqual(game.heroColor, .black)
        XCTAssertEqual(game.moves.count, 2)
        XCTAssertEqual(game.guessPointCount, 1)
        XCTAssertEqual(game.startFen, "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")

        let guess = game.moves[1]
        XCTAssertTrue(guess.isGuessPoint)
        XCTAssertEqual(guess.mover, .black)             // derived from fen_before
        XCTAssertEqual(guess.annotation, "A fine move.")
        XCTAssertEqual(guess.tags, [.tactical])
        // Same mate clamp as the DB path: mate-in-2 outranks +30cp.
        XCTAssertEqual(guess.candidateEvals["e7e5"], 30)
        XCTAssertEqual(guess.candidateEvals["d7d5"], ContentStore.mateBaseCp - 200)
    }

    func testNonGuessMoveCarriesNoEvals() throws {
        let game = try XCTUnwrap(DailyChallenge.gameContent(fromJson: Data(fixture.utf8)))
        XCTAssertTrue(game.moves[0].candidateEvals.isEmpty)
    }

    func testMalformedJsonReturnsNil() {
        XCTAssertNil(DailyChallenge.gameContent(fromJson: Data("not json".utf8)))
        XCTAssertNil(DailyChallenge.gameContent(fromJson: Data("{}".utf8)))
    }
}
