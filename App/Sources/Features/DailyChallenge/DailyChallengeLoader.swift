import Foundation

/// Fetch + cache for the daily challenge (TECH_SPEC §4: app caches today + tomorrow).
/// Network-first with cache fallback, so the daily survives offline launches and CDN
/// hiccups. Cache lives in Application Support/daily/.
struct DailyChallengeLoader {
    var calendar: Calendar = .current

    /// Today's game, or nil if neither network nor cache can produce one.
    /// Also warms tomorrow's cache in the background (fire-and-forget).
    func todaysGame(now: Date = Date()) async -> GameContent? {
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now) {
            let warmLoader = self
            Task.detached(priority: .background) {
                _ = await warmLoader.data(for: tomorrow)
            }
        }
        guard let data = await data(for: now) else { return nil }
        return DailyChallenge.gameContent(fromJson: data)
    }

    /// Raw payload for a date: try the CDN, cache on success; fall back to cache.
    func data(for date: Date) async -> Data? {
        let name = DailyChallenge.fileName(for: date, calendar: calendar)
        let cacheFile = cacheDirectory.appendingPathComponent(name)

        let url = DailyChallenge.url(for: date, calendar: calendar)
        if let (data, response) = try? await URLSession.shared.data(from: url),
           (response as? HTTPURLResponse)?.statusCode == 200 {
            try? FileManager.default.createDirectory(
                at: cacheDirectory, withIntermediateDirectories: true)
            try? data.write(to: cacheFile)
            return data
        }
        return try? Data(contentsOf: cacheFile)
    }

    private var cacheDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("daily", isDirectory: true)
    }
}
