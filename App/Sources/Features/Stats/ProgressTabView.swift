import SwiftUI

/// S7 "Progress" — rating, streak, games completed, from the user DB. Premium screen
/// per PRD §4.3/UI_FLOW S7: free users see a blurred preview behind a lock card.
/// Rating-history chart + weakness breakdown come later; this is where they land.
struct ProgressTabView: View {
    let userStore: UserStore?
    @Environment(EntitlementStore.self) private var entitlements
    @State private var paywall: PaywallTrigger?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    statsContent
                        .blur(radius: entitlements.isPremium ? 0 : 6)
                        .allowsHitTesting(entitlements.isPremium)
                        .padding(Theme.Space.md)
                }
                if !entitlements.isPremium {
                    lockCard
                }
            }
            .navigationTitle("Progress")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .sheet(item: $paywall) { trigger in
                PaywallView(trigger: trigger) { paywall = nil }
            }
        }
    }

    private var statsContent: some View {
        VStack(spacing: Theme.Space.lg) {
            VStack(spacing: Theme.Space.xs) {
                Text("GUESS RATING")
                    .font(.system(size: 11, weight: .medium))
                    .kerning(0.8)
                    .foregroundStyle(Theme.textSecondary)
                Text("\(Int(userStore?.latestRating() ?? 1200))")
                    .font(.system(size: 52, weight: .medium, design: .rounded))
                    .foregroundStyle(Theme.gold)
            }
            .padding(.top, Theme.Space.lg)

            HStack(spacing: Theme.Space.md) {
                statCard(
                    label: "STREAK",
                    value: "\u{1F525} \(userStore?.streak.current ?? 0)")
                statCard(
                    label: "LONGEST",
                    value: "\(userStore?.streak.longest ?? 0)")
                statCard(
                    label: "GAMES",
                    value: "\(userStore?.completedGameIds().count ?? 0)")
            }

            Text("Rating history and your strengths & weaknesses by theme appear here as you play.")
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.top, Theme.Space.md)
        }
    }

    private var lockCard: some View {
        VStack(spacing: Theme.Space.sm) {
            Image(systemName: "lock.fill")
                .font(.system(size: 22))
                .foregroundStyle(Theme.gold)
            Text("See how your chess sense is growing")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
            Text("Your guess rating, streaks, and strengths & weaknesses by theme \u{2014} part of the full library.")
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button("Unlock") { paywall = .lockedProgress }
                .buttonStyle(GoldButtonStyle())
                .accessibilityIdentifier("progressUnlockButton")
        }
        .cardSurface()
        .padding(Theme.Space.lg)
    }

    private func statCard(label: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(label)
                .font(.system(size: 11, weight: .medium))
                .kerning(0.8)
                .foregroundStyle(Theme.textSecondary)
            Text(value)
                .font(.system(size: 20, weight: .medium))
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity)
        .cardSurface(padding: Theme.Space.sm)
    }
}
