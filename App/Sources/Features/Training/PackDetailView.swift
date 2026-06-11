import SwiftUI

/// S6 — games inside one pack (UI_FLOW §3): header with count + unlock note,
/// rows with done/lock marks; tapping a locked game summons the paywall.
struct PackDetailView: View {
    let pack: ContentPack
    let games: [GameContent]
    let userStore: UserStore?

    @Environment(EntitlementStore.self) private var entitlements
    @State private var playing: GameContent?
    @State private var paywall: PaywallTrigger?

    private var unlockedIDs: Set<String> {
        // Same per-game rule as everywhere: FreeTier slice is computed over the
        // FULL library order, so a pack never accidentally widens the free tier.
        entitlements.isPremium
            ? Set(games.map(\.id))
            : FreeTier.unlockedGameIDs(in: ContentStore.bundledGames())
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Space.sm) {
                    Text(pack.description)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.textSecondary)
                        .padding(.top, Theme.Space.sm)

                    Text(headerLine)
                        .font(.system(size: 11, weight: .medium))
                        .kerning(0.8)
                        .foregroundStyle(Theme.textSecondary)

                    ForEach(games) { game in
                        GameRowButton(
                            game: game,
                            unlocked: unlockedIDs.contains(game.id),
                            completed: userStore?.completedGameIds().contains(game.id) == true,
                            onPlay: { playing = game },
                            onLocked: { paywall = .lockedGame }
                        )
                    }
                }
                .padding(Theme.Space.md)
                .frame(maxWidth: Theme.contentMaxWidth)
                .frame(maxWidth: .infinity)
            }
        }
        .navigationTitle(pack.name)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .fullScreenCover(item: $playing) { game in
            GuessSessionView(game: game, userStore: userStore) { playing = nil }
        }
        .sheet(item: $paywall) { trigger in
            PaywallView(trigger: trigger) { paywall = nil }
        }
    }

    private var headerLine: String {
        let count = "\(games.count) GAME\(games.count == 1 ? "" : "S")"
        return entitlements.isPremium ? count : "\(count) \u{00B7} SUBSCRIPTION UNLOCKS ALL"
    }
}
