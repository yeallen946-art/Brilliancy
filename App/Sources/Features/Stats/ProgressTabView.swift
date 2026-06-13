import SwiftUI

/// S7 "Progress" — rating, streak, games completed, from the user DB. Per PRD §4.3 /
/// UI_FLOW S7 (2026-06-13): free users SEE their rating, streak and games-completed
/// (a "you already have data" preview); only the rating-history chart + weakness
/// breakdown are locked. Those two come later; this is where they land.
struct ProgressTabView: View {
    let userStore: UserStore?
    @Environment(EntitlementStore.self) private var entitlements
    @State private var paywall: PaywallTrigger?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: Theme.Space.lg) {
                        headlineStats          // always visible (free preview)
                        lockedSection          // history + weakness; gated
                    }
                    .padding(Theme.Space.md)
                    .frame(maxWidth: Theme.contentMaxWidth)
                    .frame(maxWidth: .infinity)
                }
            }
            .navigationTitle("Progress")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .sheet(item: $paywall) { trigger in
                PaywallView(trigger: trigger) { paywall = nil }
            }
        }
    }

    /// Free preview: the numbers the user has already earned. Never blurred.
    private var headlineStats: some View {
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
        }
    }

    /// Rating history + strengths/weaknesses. Premium: the (placeholder) content.
    /// Free: blurred teaser with an inline unlock card scoped to THIS section, so the
    /// headline numbers above stay readable.
    @ViewBuilder
    private var lockedSection: some View {
        let locked = !entitlements.isPremium
        ZStack {
            VStack(spacing: Theme.Space.sm) {
                lockedPlaceholder(
                    title: "RATING HISTORY",
                    body: "Your guess rating over time appears here as you play.")
                lockedPlaceholder(
                    title: "STRENGTHS & WEAKNESSES",
                    body: "Hit-rate by theme \u{2014} tactics, positional, endgame, opening, defense.")
            }
            .blur(radius: locked ? 6 : 0)
            .allowsHitTesting(!locked)

            if locked { unlockCard }
        }
    }

    private func lockedPlaceholder(title: String, body: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 11, weight: .medium))
                .kerning(0.8)
                .foregroundStyle(Theme.textSecondary)
            Text(body)
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface(padding: Theme.Space.sm)
    }

    private var unlockCard: some View {
        VStack(spacing: Theme.Space.sm) {
            Image(systemName: "lock.fill")
                .font(.system(size: 22))
                .foregroundStyle(Theme.gold)
            Text("See how your chess sense is growing")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(Theme.textPrimary)
                .multilineTextAlignment(.center)
            Text("Rating history and strengths & weaknesses by theme \u{2014} part of the full library.")
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
