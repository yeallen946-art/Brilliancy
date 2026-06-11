import SwiftUI

/// Daily-challenge archive (PRD §4.1/§7: free users see the list, playing past
/// dailies is premium). Dates run from yesterday back to the first published
/// daily; each game is fetched from the CDN (cache-backed) on demand.
struct ArchiveView: View {
    let userStore: UserStore?

    @Environment(EntitlementStore.self) private var entitlements
    @State private var playing: GameContent?
    @State private var paywall: PaywallTrigger?
    @State private var loadingDate: Date?
    @State private var failedDate: Date?

    /// First date ever published to the CDN (RUNBOOK step 7's first rotation).
    static let archiveStart = DateComponents(
        calendar: .current, year: 2026, month: 6, day: 10).date!

    private var dates: [Date] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        var result: [Date] = []
        var cursor = calendar.date(byAdding: .day, value: -1, to: today) ?? today
        while cursor >= Self.archiveStart {
            result.append(cursor)
            guard let previous = calendar.date(byAdding: .day, value: -1, to: cursor) else { break }
            cursor = previous
        }
        return result
    }

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Space.sm) {
                    if dates.isEmpty {
                        Text("Past challenges appear here from day two.")
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.top, Theme.Space.lg)
                    }
                    ForEach(dates, id: \.self) { date in
                        archiveRow(date)
                    }
                }
                .padding(Theme.Space.md)
                .frame(maxWidth: Theme.contentMaxWidth)
                .frame(maxWidth: .infinity)
            }
        }
        .navigationTitle("Archive")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .fullScreenCover(item: $playing) { game in
            // Archive replays never touch the streak (the streak is for TODAY's
            // challenge); scores and rating still record.
            GuessSessionView(game: game, userStore: userStore, isDaily: false) { playing = nil }
        }
        .sheet(item: $paywall) { trigger in
            PaywallView(trigger: trigger) { paywall = nil }
        }
    }

    private func archiveRow(_ date: Date) -> some View {
        Button {
            if entitlements.isPremium {
                load(date)
            } else {
                paywall = .lockedArchive
            }
        } label: {
            HStack {
                Text(date.formatted(date: .abbreviated, time: .omitted))
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                Spacer()
                if loadingDate == date {
                    ProgressView().tint(Theme.gold)
                } else if failedDate == date {
                    Text("Couldn't load \u{2014} tap to retry")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.textSecondary)
                } else if !entitlements.isPremium {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.textSecondary)
                } else {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Theme.textSecondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .cardSurface(padding: Theme.Space.sm)
        }
        .buttonStyle(.plain)
        .disabled(loadingDate != nil)
    }

    private func load(_ date: Date) {
        loadingDate = date
        failedDate = nil
        Task {
            let data = await DailyChallengeLoader().data(for: date)
            let game = data.flatMap(DailyChallenge.gameContent(fromJson:))
            await MainActor.run {
                loadingDate = nil
                if let game {
                    playing = game
                } else {
                    failedDate = date
                }
            }
        }
    }
}
