import SwiftUI

/// Central visual design system (UI_FLOW §4.1). Hex values are the agreed anchors;
/// tune in the simulator, but the relationships (dark shell + Chess.com green/white
/// board + gold CTA + softened 3-tier feedback) stay fixed.
enum Theme {

    // MARK: Shell (dark theme)
    static let background    = Color(hex: 0x0F141A)
    static let surface       = Color(hex: 0x1B222B)
    static let border        = Color(hex: 0x28313B)
    static let textPrimary   = Color(hex: 0xECF0F4)
    static let textSecondary = Color(hex: 0x94A1AE)

    // MARK: Brand (gold — only CTA + streak)
    static let gold   = Color(hex: 0xE6B450)
    static let onGold = Color(hex: 0x2E2103)

    // MARK: Feedback (softened; red not harsh)
    static let feedbackGreen  = Color(hex: 0x57B98A)
    static let feedbackYellow = Color(hex: 0xE0B84A)
    static let feedbackRed    = Color(hex: 0xE07A6A)

    // MARK: Board (Chess.com green/white)
    static let boardLight     = Color(hex: 0xEBECD0)
    static let boardDark      = Color(hex: 0x769656)
    static let highlightLight = Color(hex: 0xF5F682)   // full-square overlay, light square
    static let highlightDark  = Color(hex: 0xB9CA43)   // full-square overlay, dark square

    // MARK: Pieces (placeholder fill/outline until the cburnett SVG set is bundled)
    static let pieceLightFill    = Color(hex: 0xF3F3EE)
    static let pieceLightOutline = Color(hex: 0x14140F)
    static let pieceDarkFill     = Color(hex: 0x191B17)
    static let pieceDarkOutline  = Color(hex: 0xE9EAE0)

    // MARK: Spacing / radius (8-multiple grid)
    enum Space {
        static let xs: CGFloat = 8
        static let sm: CGFloat = 12
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
    }
    enum Radius {
        static let card: CGFloat = 12
        static let button: CGFloat = 12
        static let board: CGFloat = 6
    }
}

extension Color {
    /// 0xRRGGBB convenience.
    init(hex: Int) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: 1.0
        )
    }
}

/// Primary gold CTA (UI_FLOW §4.1 — gold reserved for the main action).
struct GoldButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 17, weight: .medium))
            .foregroundStyle(Theme.onGold)
            .padding(.vertical, 14)
            .padding(.horizontal, Theme.Space.lg)
            .frame(maxWidth: .infinity)
            .background(
                Theme.gold.opacity(configuration.isPressed ? 0.85 : 1.0),
                in: RoundedRectangle(cornerRadius: Theme.Radius.button)
            )
    }
}

extension View {
    /// Card surface: dark panel with a hairline border and 12pt radius.
    func cardSurface(padding: CGFloat = Theme.Space.md) -> some View {
        self
            .padding(padding)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.card)
                    .strokeBorder(Theme.border, lineWidth: 1)
            )
    }

    /// Fill the safe area with the app's dark background.
    func screenBackground() -> some View {
        self.background(Theme.background.ignoresSafeArea())
    }
}
