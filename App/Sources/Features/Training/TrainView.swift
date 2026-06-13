import SwiftUI

/// S5 "Train" — pack browsing on top (UI_FLOW §3: browse free, play gated), the flat
/// all-games list below. Freemium split (PRD §7): free users play the FreeTier
/// sample slice; locked rows show a lock and summon the paywall (S8).
struct TrainView: View {
    let userStore: UserStore?
    @Environment(EntitlementStore.self) private var entitlements
    @State private var playing: GameContent?
    @State private var paywall: PaywallTrigger?

    private let games: [GameContent] = {
        var games = ContentStore.bundledGames()
        #if DEBUG
        // UI-test-only fixture (positive reveal card needs an engine-equal guess,
        // which curated content never contains). Inert without the launch argument.
        if UITestFixtures.isEqualGuessFixtureEnabled {
            games.append(UITestFixtures.equalGuessGame)
        }
        #endif
        return games
    }()
    private let packs: [ContentPack] = ContentStore.bundledPacks()

    private var unlockedIDs: Set<String> {
        entitlements.isPremium ? Set(games.map(\.id)) : FreeTier.unlockedGameIDs(in: games)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Space.sm) {
                        if !packs.isEmpty {
                            Text("PACKS")
                                .font(.system(size: 11, weight: .medium))
                                .kerning(0.8)
                                .foregroundStyle(Theme.textSecondary)
                                .padding(.top, Theme.Space.md)

                            ForEach(packs) { pack in
                                NavigationLink {
                                    PackDetailView(
                                        pack: pack,
                                        games: games.filter { $0.packId == pack.id },
                                        userStore: userStore
                                    )
                                } label: {
                                    packCard(pack)
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        Text("ALL GAMES")
                            .font(.system(size: 11, weight: .medium))
                            .kerning(0.8)
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.top, Theme.Space.md)

                        if games.isEmpty {
                            Text("No games available.")
                                .font(.system(size: 13))
                                .foregroundStyle(Theme.textSecondary)
                        }

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
            .navigationTitle("Train")
            .toolbarColorScheme(.dark, for: .navigationBar)
            .fullScreenCover(item: $playing) { game in
                GuessSessionView(game: game, userStore: userStore) { playing = nil }
            }
            .sheet(item: $paywall) { trigger in
                PaywallView(trigger: trigger) { paywall = nil }
            }
        }
    }

    private func packCard(_ pack: ContentPack) -> some View {
        let count = games.filter { $0.packId == pack.id }.count
        return HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(pack.name)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                Text("\(count) game\(count == 1 ? "" : "s") \u{00B7} \(pack.description)")
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.textSecondary)
                    .lineLimit(2)
                // Skill promise (TECH_SPEC §6): sell what they get better at, not the
                // game list. Shown only when curation supplies one.
                if !pack.promise.isEmpty {
                    Text(pack.promise)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(Theme.gold)
                        .lineLimit(2)
                        .padding(.top, 1)
                }
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface(padding: Theme.Space.sm)
    }
}

/// One game row, shared by the Train list and pack detail (S5/S6): lock for gated
/// games, checkmark for completed ones.
struct GameRowButton: View {
    let game: GameContent
    let unlocked: Bool
    let completed: Bool
    let onPlay: () -> Void
    let onLocked: () -> Void

    var body: some View {
        Button {
            if unlocked { onPlay() } else { onLocked() }
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
                } else if completed {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Theme.feedbackGreen)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .cardSurface(padding: Theme.Space.sm)
        }
        .buttonStyle(.plain)
    }
}
