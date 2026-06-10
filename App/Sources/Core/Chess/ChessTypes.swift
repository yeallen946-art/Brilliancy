import Foundation

// MARK: - Engine-independent board model
//
// These value types are how the rest of the app (BoardView, scoring, tests) talks
// about a position. They deliberately do NOT depend on ChessKit so that the engine
// stays swappable and the UI never imports it directly (TECH_SPEC §3, "move gen wrapper").

/// A board square in 0-indexed file/rank coordinates.
/// `file`: 0 = a … 7 = h.  `rank`: 0 = rank 1 … 7 = rank 8.
struct Sq: Hashable {
    let file: Int
    let rank: Int

    init(file: Int, rank: Int) {
        self.file = file
        self.rank = rank
    }

    /// Algebraic name, e.g. "e4". Used as the bridge to/from the engine wrapper.
    var name: String {
        let fileChar = Character(UnicodeScalar(UInt8(97 + file)))
        return "\(fileChar)\(rank + 1)"
    }

    /// Parse algebraic notation like "e4". Returns nil if out of range / malformed.
    init?(name: String) {
        let chars = Array(name.lowercased())
        guard chars.count == 2,
              let fileScalar = chars[0].asciiValue, fileScalar >= 97, fileScalar <= 104,
              let rankDigit = chars[1].wholeNumberValue, rankDigit >= 1, rankDigit <= 8
        else { return nil }
        self.file = Int(fileScalar) - 97
        self.rank = rankDigit - 1
    }

    var isLight: Bool { (file + rank) % 2 == 1 }
}

enum PieceColor: Hashable {
    case white, black
    var opposite: PieceColor { self == .white ? .black : .white }
}

enum PieceKind: Hashable {
    case pawn, knight, bishop, rook, queen, king
}

/// A piece sitting on a specific square.
struct PlacedPiece: Hashable {
    let kind: PieceKind
    let color: PieceColor
    let square: Sq

    /// Unicode glyph for rendering without bundled art (good enough for M0).
    var glyph: String {
        switch (color, kind) {
        case (.white, .king):   return "\u{2654}"
        case (.white, .queen):  return "\u{2655}"
        case (.white, .rook):   return "\u{2656}"
        case (.white, .bishop): return "\u{2657}"
        case (.white, .knight): return "\u{2658}"
        case (.white, .pawn):   return "\u{2659}"
        case (.black, .king):   return "\u{265A}"
        case (.black, .queen):  return "\u{265B}"
        case (.black, .rook):   return "\u{265C}"
        case (.black, .bishop): return "\u{265D}"
        case (.black, .knight): return "\u{265E}"
        case (.black, .pawn):   return "\u{265F}"
        }
    }

    /// Filled silhouette glyph (always the solid set). Fallback if the cburnett asset
    /// is unavailable; tinted + outlined by color at render time.
    var silhouette: String {
        switch kind {
        case .king:   return "\u{265A}"
        case .queen:  return "\u{265B}"
        case .rook:   return "\u{265C}"
        case .bishop: return "\u{265D}"
        case .knight: return "\u{265E}"
        case .pawn:   return "\u{265F}"
        }
    }

    /// Asset-catalog name for the bundled cburnett piece, e.g. "piece_wN".
    var assetName: String {
        let colorCode = color == .white ? "w" : "b"
        let kindCode: String
        switch kind {
        case .king:   kindCode = "K"
        case .queen:  kindCode = "Q"
        case .rook:   kindCode = "R"
        case .bishop: kindCode = "B"
        case .knight: kindCode = "N"
        case .pawn:   kindCode = "P"
        }
        return "piece_\(colorCode)\(kindCode)"
    }
}

enum FEN {
    /// Standard chess starting position.
    static let start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
}
