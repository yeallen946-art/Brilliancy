import Foundation

/// UCI helpers for driving a game forward (used by GuessSession autoplay + guess submission).
/// Kept separate from ChessGame.swift so the ChessKit-bridge file stays focused.
extension ChessGame {

    /// Apply a move in UCI form ("e2e4", "e7e8q"). Returns true iff legal and applied.
    @discardableResult
    mutating func apply(uci: String) -> Bool {
        guard let parsed = Self.parse(uci: uci) else { return false }
        return move(from: parsed.from, to: parsed.to, promotion: parsed.promotion)
    }

    /// Build the UCI string for a move, auto-appending queen promotion when a pawn
    /// reaches the last rank (M1 promotes to queen by default; full UI is later).
    func uci(from: Sq, to: Sq) -> String {
        var s = from.name + to.name
        if let piece = pieces.first(where: { $0.square == from }),
           piece.kind == .pawn, to.rank == 0 || to.rank == 7 {
            s += "q"
        }
        return s
    }

    static func parse(uci: String) -> (from: Sq, to: Sq, promotion: PieceKind?)? {
        let chars = Array(uci)
        guard chars.count == 4 || chars.count == 5,
              let from = Sq(name: String(chars[0...1])),
              let to = Sq(name: String(chars[2...3])) else { return nil }
        let promotion = chars.count == 5 ? promotionKind(chars[4]) : nil
        return (from, to, promotion)
    }

    private static func promotionKind(_ c: Character) -> PieceKind? {
        switch c {
        case "q": return .queen
        case "r": return .rook
        case "b": return .bishop
        case "n": return .knight
        default:  return nil
        }
    }
}
