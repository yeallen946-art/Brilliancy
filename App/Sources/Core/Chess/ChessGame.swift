import Foundation
import ChessKit

/// The single bridge between our engine-independent board model (`Sq`, `PlacedPiece`)
/// and ChessKit. Everything else in the app speaks our types; only this file imports
/// ChessKit. If the ChessKit API differs from what's assumed below, THIS is the only
/// file that should need fixing.
///
/// ── MACOS-FIXME (ChessKit API assumptions, verify on first compile) ──────────────
/// Written blind on Windows. Assumptions about chesskit-app/chesskit-swift:
///   1. `Position(fen:)` is a failable init returning nil on bad FEN.
///   2. `Position.fen` -> String (current FEN).
///   3. `Position.pieces` -> [Piece]; `Position.sideToMove` -> Piece.Color (.white/.black).
///   4. `Piece` has `.kind` (Piece.Kind: .pawn/.knight/.bishop/.rook/.queen/.king),
///      `.color` (Piece.Color), `.square` (Square).
///   5. `Board(position:)` init; `Board.legalMoves(forPieceAt: Square) -> [Square]`;
///      `Board.move(pieceAt: Square, to: Square) -> Move?` (returns nil if illegal).
///   6. A ChessKit `Square` prints as its algebraic name ("e4") via String(describing:).
///      The Sq<->Square bridge below relies ONLY on this one fact, to avoid guessing
///      the File/Rank construction API. If wrong, fix `square(from:)` / `sq(from:)`.
/// If any assumption is off, adjust the mapping helpers — the public surface
/// (init?/fen/pieces/sideToMove/legalDestinations/move) should stay stable.
/// ─────────────────────────────────────────────────────────────────────────────────
struct ChessGame {
    private var board: Board

    /// Load a position from FEN. Returns nil for an invalid FEN.
    init?(fen: String) {
        guard let position = Position(fen: fen) else { return nil }
        self.board = Board(position: position)
    }

    /// Current position as FEN.
    var fen: String { board.position.fen }

    /// Side to move.
    var sideToMove: PieceColor {
        board.position.sideToMove == .white ? .white : .black
    }

    /// All pieces currently on the board.
    var pieces: [PlacedPiece] {
        board.position.pieces.compactMap { piece in
            guard let kind = Self.kind(from: piece.kind),
                  let square = Self.sq(from: piece.square) else { return nil }
            return PlacedPiece(
                kind: kind,
                color: piece.color == .white ? .white : .black,
                square: square
            )
        }
    }

    /// Legal destination squares for whatever piece sits on `from` (empty if none / not mover's).
    func legalDestinations(from square: Sq) -> [Sq] {
        let source = Self.square(from: square)
        guard let piece = board.position.piece(at: source),
              piece.color == board.position.sideToMove else { return [] }

        return board.legalMoves(forPieceAt: source)
            .compactMap(Self.sq(from:))
    }

    /// Attempt a move. Returns true iff it was legal and applied.
    /// Promotion handling is deferred to M1 (M0 just needs legal movement); ChessKit's
    /// default promotion behavior is accepted for now. See PRD/TECH_SPEC for full rules.
    @discardableResult
    mutating func move(from: Sq, to: Sq, promotion: PieceKind? = nil) -> Bool {
        let source = Self.square(from: from)
        guard let piece = board.position.piece(at: source),
              piece.color == board.position.sideToMove else { return false }

        return board.move(pieceAt: source, to: Self.square(from: to)) != nil
    }

    // MARK: - Sq <-> ChessKit.Square bridge (algebraic-name based; see MACOS-FIXME #6)

    /// Map an algebraic name ("e4") to a ChessKit Square via its all-cases table.
    private static let squareByName: [String: Square] = {
        var map: [String: Square] = [:]
        for square in Square.allCases {
            map[String(describing: square)] = square
        }
        return map
    }()

    private static func square(from sq: Sq) -> Square {
        // Force-unwrap is safe: every legal Sq has a matching algebraic name on a chessboard.
        squareByName[sq.name]!
    }

    private static func sq(from square: Square) -> Sq? {
        Sq(name: String(describing: square))
    }

    private static func kind(from kind: Piece.Kind) -> PieceKind? {
        switch kind {
        case .pawn:   return .pawn
        case .knight: return .knight
        case .bishop: return .bishop
        case .rook:   return .rook
        case .queen:  return .queen
        case .king:   return .king
        @unknown default: return nil
        }
    }
}
