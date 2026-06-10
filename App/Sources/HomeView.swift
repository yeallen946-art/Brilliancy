import SwiftUI

/// S1 "Today" (first real version). Featured slot = today's daily challenge from the
/// CDN (cache-backed), falling back to the first bundled game while offline/loading.
/// Visual system per UI_FLOW §4.1: dark shell, gold CTA (and streak), surface cards.
struct HomeView: View {
    /// Shared app-wide store, owned by RootTabView (one user.sqlite connection).
    let userStore: UserStore?
    @Environment(EntitlementStore.self) private var entitlements

    @State private var playing: GameContent?
    @State private var dailyGame: GameContent?
    @State private var paywall: PaywallTrigger?

    /// Pipeline content from the bundled content.sqlite (GRDB path Mac-verified,
    /// issue #3). User-visible content comes from the DB; the M1 sample remains only
    /// as a test fixture for the guess-session state machine.
    private let library: [GameContent] = ContentStore.bundledGames()

    /// nil when the DB is missing/unreadable AND the daily hasn't loaded —
    /// ContentStore degrades to [] by contract, so never index into the library.
    private var featured: GameContent? { dailyGame ?? library.first }

    /// Freemium split (PRD §7): the daily challenge is always free; library rows
    /// follow the same FreeTier rule as the Train tab.
    private var unlockedIDs: Set<String> {
        entitlements.isPremium ? Set(library.map(\.id)) : FreeTier.unlockedGameIDs(in: library)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(spacing: Theme.Space.lg) {
                        featuredSection
                        if featured != nil {
                            Button("Play today's game") { playing = featured }
                                .buttonStyle(GoldButtonStyle())
                                .accessibilityIdentifier("playTodayButton")
                        }
                        librarySection
                        NavigationLink("Board sandbox (debug)") { BoardSandboxView() }
                            .font(.footnote)
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.top, Theme.Space.xs)
                        Text("Pieces: cburnett by Colin M.L. Burnett · CC BY-SA 3.0")
                            .font(.system(size: 11))
                            .foregroundStyle(Theme.textSecondary.opacity(0.7))
                            .multilineTextAlignment(.center)
                            .padding(.top, Theme.Space.lg)
                    }
                    .padding(Theme.Space.md)
                }
            }
            .navigationTitle("Brilliancy")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .fullScreenCover(item: $playing) { game in
                GuessSessionView(
                    game: game,
                    userStore: userStore,
                    isDaily: game.id == dailyGame?.id
                ) { playing = nil }
            }
            .sheet(item: $paywall) { trigger in
                PaywallView(trigger: trigger) { paywall = nil }
            }
            .task {
                dailyGame = await DailyChallengeLoader().todaysGame()
            }
        }
        .preferredColorScheme(.dark)
        .tint(Theme.gold)
    }

    private var featuredSection: some View {
        VStack(spacing: Theme.Space.xs) {
            HStack(spacing: Theme.Space.xs) {
                Text(dailyGame != nil ? "TODAY'S GAME" : "FEATURED")
                    .font(.system(size: 11, weight: .medium))
                    .kerning(0.8)
                    .foregroundStyle(Theme.textSecondary)
                if let streak = userStore?.streak, streak.current > 0 {
                    Text("\u{1F525} \(streak.current)")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(Theme.gold)
                }
            }
            .padding(.top, Theme.Space.lg)
            if let featured {
                Text(featured.title)
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)
                Text(featured.subtitle)
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.textSecondary)
            } else {
                Text("No games available — check your connection.")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
    }

    private var librarySection: some View {
        VStack(alignment: .leading, spacing: Theme.Space.sm) {
            Text("LIBRARY")
                .font(.system(size: 11, weight: .medium))
                .kerning(0.8)
                .foregroundStyle(Theme.textSecondary)
            ForEach(library) { game in
                let unlocked = unlockedIDs.contains(game.id)
                Button {
                    if unlocked { playing = game } else { paywall = .lockedGame }
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(game.title)
                                .font(.system(size: 15, weight: .medium))
                                .foregroundStyle(Theme.textPrimary)
                            Text(game.subtitle)
                                .font(.system(size: 11))
                                .foregroundStyle(Theme.textSecondary)
                        }
                        Spacer()
                        if !unlocked {
                            Image(systemName: "lock.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(Theme.textSecondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardSurface(padding: Theme.Space.sm)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

#Preview {
    HomeView(userStore: UserStore.onDisk())
        .environment(EntitlementStore())
}
