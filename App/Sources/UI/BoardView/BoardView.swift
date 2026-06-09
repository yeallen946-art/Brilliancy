import SwiftUI

/// Interactive chess board: renders a position and lets the user move pieces by
/// tap-tap (tap source, tap destination) or by dragging. Engine-agnostic — it only
/// knows about `ChessGame`/`Sq`/`PlacedPiece`. White is at the bottom for M0;
/// orientation flipping (play the hero's color) comes with GuessSession in M1.
struct BoardView: View {
    @Binding var game: ChessGame

    /// Currently selected source square (for tap-tap moves).
    @State private var selected: Sq?
    /// Legal destinations for the selected square, highlighted.
    @State private var highlights: Set<Sq> = []

    private let lightColor = Color(red: 0.93, green: 0.85, blue: 0.71)
    private let darkColor  = Color(red: 0.55, green: 0.40, blue: 0.27)

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            let cell = side / 8

            ZStack(alignment: .topLeading) {
                squares(cell: cell)
                pieces(cell: cell)
            }
            .frame(width: side, height: side)
            // One board-level gesture handles BOTH tap-tap and drag: if the press
            // starts and ends on the same square it's a tap; otherwise it's a drag.
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onEnded { value in
                        guard let from = square(at: value.startLocation, cell: cell) else { return }
                        let to = square(at: value.location, cell: cell)
                        if let to, to != from {
                            attemptMove(from: from, to: to)
                        } else {
                            handleTap(on: from)
                        }
                    }
            )
        }
        .aspectRatio(1, contentMode: .fit)
    }

    // MARK: - Rendering

    private func squares(cell: CGFloat) -> some View {
        ForEach(0..<8, id: \.self) { row in
            ForEach(0..<8, id: \.self) { col in
                // row 0 is the TOP of the screen = rank 8 (index 7) with white at bottom.
                let sq = Sq(file: col, rank: 7 - row)
                Rectangle()
                    .fill(sq.isLight ? lightColor : darkColor)
                    .overlay(highlightOverlay(for: sq, cell: cell))
                    .overlay(selectionOverlay(for: sq))
                    .frame(width: cell, height: cell)
                    .offset(x: CGFloat(col) * cell, y: CGFloat(row) * cell)
            }
        }
    }

    @ViewBuilder
    private func highlightOverlay(for sq: Sq, cell: CGFloat) -> some View {
        if highlights.contains(sq) {
            Circle()
                .fill(Color.green.opacity(0.45))
                .frame(width: cell * 0.32, height: cell * 0.32)
        }
    }

    @ViewBuilder
    private func selectionOverlay(for sq: Sq) -> some View {
        if selected == sq {
            Rectangle().fill(Color.yellow.opacity(0.4))
        }
    }

    private func pieces(cell: CGFloat) -> some View {
        ForEach(game.pieces, id: \.self) { piece in
            Text(piece.glyph)
                .font(.system(size: cell * 0.82))
                .frame(width: cell, height: cell)
                .offset(offset(for: piece.square, cell: cell))
                .allowsHitTesting(false) // gestures are handled at the board level
        }
    }

    private func offset(for sq: Sq, cell: CGFloat) -> CGSize {
        let col = sq.file
        let row = 7 - sq.rank // flip rank back to top-origin screen row
        return CGSize(width: CGFloat(col) * cell, height: CGFloat(row) * cell)
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
        // Default promotion to queen for M0; full promotion UI is M1.
        let promotion: PieceKind? = isPromotion(from: from, to: to) ? .queen : nil
        _ = game.move(from: from, to: to, promotion: promotion)
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

    /// Map a point in the board's coordinate space to a square (white at bottom).
    private func square(at point: CGPoint, cell: CGFloat) -> Sq? {
        let col = Int(point.x / cell)
        let row = Int(point.y / cell)
        guard (0..<8).contains(col), (0..<8).contains(row) else { return nil }
        return Sq(file: col, rank: 7 - row)
    }
}
