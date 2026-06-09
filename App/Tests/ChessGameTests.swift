import XCTest
@testable import Brilliancy

/// Seed of the FEN/move round-trip suite mandated by CLAUDE.md hard rule #5:
/// any board/move-gen change must keep these green. Expanded with the SAN suite in M1.
final class ChessGameTests: XCTestCase {

    func testLoadsStartingPositionAndRoundTripsFEN() throws {
        let game = try XCTUnwrap(ChessGame(fen: FEN.start))
        XCTAssertEqual(game.fen, FEN.start)
        XCTAssertEqual(game.sideToMove, .white)
        XCTAssertEqual(game.pieces.count, 32)
    }

    func testInvalidFENReturnsNil() {
        XCTAssertNil(ChessGame(fen: "not a fen"))
        XCTAssertNil(ChessGame(fen: ""))
    }

    func testStartingPositionHasTwentyLegalFirstMoves() throws {
        let game = try XCTUnwrap(ChessGame(fen: FEN.start))
        // 8 pawns × 2 + 2 knights × 2 = 20 legal moves from the start.
        var total = 0
        for file in 0..<8 {
            for rank in 0..<8 {
                total += game.legalDestinations(from: Sq(file: file, rank: rank)).count
            }
        }
        XCTAssertEqual(total, 20)
    }

    func testLegalMoveAdvancesSideToMove() throws {
        var game = try XCTUnwrap(ChessGame(fen: FEN.start))
        let e2 = try XCTUnwrap(Sq(name: "e2"))
        let e4 = try XCTUnwrap(Sq(name: "e4"))
        XCTAssertTrue(game.legalDestinations(from: e2).contains(e4))

        XCTAssertTrue(game.move(from: e2, to: e4))
        XCTAssertEqual(game.sideToMove, .black)
        XCTAssertFalse(game.pieces.contains { $0.square == e2 })
        XCTAssertTrue(game.pieces.contains { $0.square == e4 && $0.kind == .pawn })
    }

    func testIllegalMoveIsRejected() throws {
        var game = try XCTUnwrap(ChessGame(fen: FEN.start))
        let e2 = try XCTUnwrap(Sq(name: "e2"))
        let e5 = try XCTUnwrap(Sq(name: "e5")) // two-square jump to an illegal target
        XCTAssertFalse(game.move(from: e2, to: e5))
        XCTAssertEqual(game.sideToMove, .white) // unchanged
    }

    func testSquareNameRoundTrip() {
        for file in 0..<8 {
            for rank in 0..<8 {
                let sq = Sq(file: file, rank: rank)
                XCTAssertEqual(Sq(name: sq.name), sq)
            }
        }
    }
}
