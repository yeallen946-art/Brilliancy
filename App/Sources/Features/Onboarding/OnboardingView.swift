import SwiftUI

/// S10 — first-launch onboarding, 3 light screens (UI_FLOW §3). No account, no
/// permission prompts (notifications are asked for in Settings, never here).
/// Page 2 uses a stylized mock (banner chip + skeleton lines), NOT real chess
/// prose — annotations only ever come from the pipeline (hard rule #1).
struct OnboardingView: View {
    var onFinish: () -> Void

    @State private var page = 0
    @State private var demoBoard = ChessGame(fen: FEN.start)!

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: Theme.Space.lg) {
                TabView(selection: $page) {
                    pageOne.tag(0)
                    pageTwo.tag(1)
                    pageThree.tag(2)
                }
                .tabViewStyle(.page(indexDisplayMode: .always))

                Button(page < 2 ? "Continue" : "Start") {
                    if page < 2 {
                        withAnimation { page += 1 }
                    } else {
                        onFinish()
                    }
                }
                .buttonStyle(GoldButtonStyle())
                .padding(.horizontal, Theme.Space.lg)
                .padding(.bottom, Theme.Space.lg)
                .accessibilityIdentifier("onboardingContinueButton")
            }
            .frame(maxWidth: Theme.contentMaxWidth)
        }
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("onboardingView")
    }

    // MARK: - Pages

    private var pageOne: some View {
        VStack(spacing: Theme.Space.lg) {
            Spacer(minLength: 0)
            BoardView(game: $demoBoard, isInteractive: false)
                .frame(maxWidth: 320)
                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.board))
            Text("Outguess the legends.")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
            Text("Play one master game a day and guess the next move yourself.")
                .font(.system(size: 15))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Theme.Space.lg)
            Spacer(minLength: 0)
        }
        .padding(Theme.Space.md)
    }

    private var pageTwo: some View {
        VStack(spacing: Theme.Space.lg) {
            Spacer(minLength: 0)

            // Stylized guess -> reveal mock: feedback chip + skeleton prose lines.
            VStack(alignment: .leading, spacing: Theme.Space.sm) {
                HStack(spacing: Theme.Space.xs) {
                    Text("\u{2713}").font(.title3.weight(.medium))
                    Text("Match!").font(.system(size: 15, weight: .medium))
                    Text("+100").font(.system(size: 13, weight: .medium))
                }
                .padding(.vertical, Theme.Space.xs)
                .padding(.horizontal, Theme.Space.md)
                .background(Theme.feedbackGreen.opacity(0.18), in: Capsule())
                .foregroundStyle(Theme.feedbackGreen)

                VStack(alignment: .leading, spacing: 6) {
                    ForEach(0..<3, id: \.self) { index in
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Theme.border)
                            .frame(width: index == 2 ? 140 : 220, height: 8)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .cardSurface()
            }
            .frame(maxWidth: 320)

            Text("Not just right or wrong.")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
            Text("An AI coach explains why the master's move works \u{2014} and why yours falls short.")
                .font(.system(size: 15))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Theme.Space.lg)
            Spacer(minLength: 0)
        }
        .padding(Theme.Space.md)
    }

    private var pageThree: some View {
        VStack(spacing: Theme.Space.lg) {
            Spacer(minLength: 0)
            Text("\u{1F525}")
                .font(.system(size: 64))
            Text("Today's game is ready.")
                .font(.system(size: 28, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
            Text("Start your streak \u{2014} one brilliant game a day.")
                .font(.system(size: 15))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Theme.Space.lg)
            Spacer(minLength: 0)
        }
        .padding(Theme.Space.md)
    }
}
