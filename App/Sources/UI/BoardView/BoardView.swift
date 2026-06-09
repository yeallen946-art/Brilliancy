import SwiftUI

/// Interactive chess board: renders a position and lets the user move pieces by
/// tap-tap (tap source, tap destination) or by dragging. Engine-agnostic — it only
/// knows about `ChessGame`/`Sq`/`PlacedPiece`. White is at the bottom for M0;
/// orientation flipping (play the hero's color) comes with GuessSession in M1.
///
/// Layout: the board fits a 1:1 square into whatever space it's given and centers
/// itself. Each of the 64 squares is laid out by its CENTER via `.position(...)`
/// inside a fixed `side × side` container — never with `.offset`, which is a
/// post-layout visual transform and would let the grid spill outside its bounds.
struct BoardView: View {
    @Binding var game: ChessGame

    /// When false, the board is display-only (no selection / moves). Default interactive.
    var isInteractive: Bool = true
    /// If set, a legal move is reported here INSTEAD of being applied to `game` — the owner
    /// decides what to do (e.g. score a guess). When nil, the move is applied to `game`.
    var onMove: ((_ from: Sq, _ to: Sq) -> Void)? = nil
    /// Squares to emphasize (e.g. the user's move vs the master's move on reveal).
    var emphasis: Set<Sq> = []
    /// Which color sits at the bottom of the board. Default white (M0 sandbox).
    var orientation: PieceColor = .white

    /// Currently selected source square (for tap-tap moves).
    @State private var selected: Sq?
    /// Legal destinations for the selected square, highlighted.
    @State private var highlights: Set<Sq> = []

    private let lightColor = Color(red: 0.93, green: 0.85, blue: 0.71)
    private let darkColor  = Color(red: 0.55, green: 0.40, blue: 0.27)

    /// All 64 squares (file 0…7, rank 0…7).
    private static let allSquares: [Sq] = (0..<8).flatMap { rank in
        (0..<8).map { file in Sq(file: file, rank: rank) }
    }

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            let cellSize = side / 8
            let pieceBySquare = Dictionary(
                game.pieces.map { ($0.square, $0) },
                uniquingKeysWith: { first, _ in first }
            )

            ZStack(alignment: .topLeading) {
                ForEach(Self.allSquares, id: \.self) { sq in
                    cell(sq, piece: pieceBySquare[sq], size: cellSize)
                        .position(center(of: sq, cell: cellSize))
                }
            }
            .frame(width: side, height: side)
            .contentShape(Rectangle())
            // One board-level gesture handles BOTH tap-tap and drag: if the press
            // starts and ends on the same square it's a tap; otherwise it's a drag.
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onEnded { value in
                        guard isInteractive else { return }
                        guard let from = square(at: value.startLocation, cell: cellSize) else { return }
                        let to = square(at: value.location, cell: cellSize)
                        if let to, to != from {
                            attemptMove(from: from, to: to)
                        } else {
                            handleTap(on: from)
                        }
                    }
            )
            // Center the square board within the (possibly non-square) proposed area.
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        }
        .aspectRatio(1, contentMode: .fit)
        // Queryable as a single element in UI tests.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Chess board")
        .accessibilityIdentifier("boardView")
    }

    // MARK: - Rendering

    private func cell(_ sq: Sq, piece: PlacedPiece?, size: CGFloat) -> some View {
        ZStack {
            Rectangle().fill(sq.isLight ? lightColor : darkColor)

            if selected == sq {
                Rectangle().fill(Color.yellow.opacity(0.4))
            }
            if highlights.contains(sq) {
                Circle()
                    .fill(Color.green.opacity(0.45))
                    .frame(width: size * 0.32, height: size * 0.32)
            }
            if let piece {
                Text(piece.glyph)
                    .font(.system(size: size * 0.82))
                    .minimumScaleFactor(0.5)
            }
            if emphasis.contains(sq) {
                Rectangle()
                    .strokeBorder(Color.orange, lineWidth: max(2, size * 0.07))
            }
        }
        .frame(width: size, height: size)
    }

    /// Center point of a square in board-local coordinates (top-left origin), honoring orientation.
    private func center(of sq: Sq, cell: CGFloat) -> CGPoint {
        let (col, row) = screenColRow(file: sq.file, rank: sq.rank)
        return CGPoint(x: (CGFloat(col) + 0.5) * cell,
                       y: (CGFloat(row) + 0.5) * cell)
    }

    /// Map (file, rank) -> on-screen (col, row), top-left origin. White-bottom by default;
    /// Black-bottom mirrors both axes (8th rank toward black, a-file on black's right).
    private func screenColRow(file: Int, rank: Int) -> (col: Int, row: Int) {
        switch orientation {
        case .white: return (file, 7 - rank)
        case .black: return (7 - file, rank)
        }
    }

    // MARK: - Interaction

    private func handleTap(on sq: Sq) {
        if let source = selected {
            if source == sq {
                clearSelection() // tap the selected square again to deselect
            } else if highlights.contains(sq) {
                attemptMove(from: source, to: sq)
            } else {
                select(sq) // re-target to a different piece
            }
        } else {
            select(sq)
        }
    }

    private func select(_ sq: Sq) {
        let dests = game.legalDestinations(from: sq)
        if dests.isEmpty {
            clearSelection()
        } else {
            selected = sq
            highlights = Set(dests)
        }
    }

    private func attemptMove(from: Sq, to: Sq) {
        // Only accept legal moves (the highlight path already guarantees this; the drag
        // path may not). Then either report the move to the owner or apply it locally.
        guard game.legalDestinations(from: from).contains(to) else {
            clearSelection()
            return
        }
        if let onMove {
            onMove(from, to)
        } else {
            // Default promotion to queen; full promotion UI is later.
            let promotion: PieceKind? = isPromotion(from: from, to: to) ? .queen : nil
            _ = game.move(from: from, to: to, promotion: promotion)
        }
        clearSelection()
    }

    private func isPromotion(from: Sq, to: Sq) -> Bool {
        guard let piece = game.pieces.first(where: { $0.square == from }),
              piece.kind == .pawn else { return false }
        return to.rank == 0 || to.rank == 7
    }

    private func clearSelection() {
        selected = nil
        highlights = []
    }

    /// Map a point in the board's coordinate space to a square, honoring orientation.
    private func square(at point: CGPoint, cell: CGFloat) -> Sq? {
        let col = Int(point.x / cell)
        let row = Int(point.y / cell)
        guard (0..<8).contains(col), (0..<8).contains(row) else { return nil }
        switch orientation {
        case .white: return Sq(file: col, rank: 7 - row)
        case .black: return Sq(file: 7 - col, rank: row)
        }
    }
}
