import Foundation

/// Daily challenge — CDN JSON decode layer (TECH_SPEC §4 "Daily challenge JSON").
/// The shape mirrors pipeline `build.daily_payload` exactly. M3's remaining pieces
/// (URLSession fetch, today+tomorrow cache, S1 wiring) build on this; keeping the
/// decode pure makes it testable without networking.
enum DailyChallenge {

    // MARK: - Wire format (snake_case via .convertFromSnakeCase)

    struct Payload: Decodable {
        let dailyId: String
        let game: Game
    }

    struct Game: Decodable {
        let id: String
        let white: String
        let black: String
        let event: String?
        let year: Int?
        let result: String?
        let heroColor: String?
        let title: String?
        let narrativeIntro: String?
        let moves: [Move]
    }

    struct Move: Decodable {
        let ply: Int
        let san: String
        let uci: String
        let fenBefore: String
        let isGuessPoint: Bool
        let difficulty: Double?
        let tags: [String]?
        // UCI keys ("e2e4") contain no underscores, so .convertFromSnakeCase
        // leaves them intact; only the field names are converted.
        let legalEvals: [String: ContentStore.EvalEntry]?
        let annotation: String?
    }

    // MARK: - CDN location

    /// Content CDN (GitHub Pages, repo yeallen946-art/brilliancy-content). Swapping
    /// CDN later = change this one constant (TECH_SPEC §2: Cloudflare is the upgrade
    /// path if/when a custom domain or cache control is wanted).
    static let baseURL = URL(string: "https://yeallen946-art.github.io/brilliancy-content/daily/")!

    /// "2026-06-10.json" — keyed by the user's LOCAL calendar date.
    static func fileName(for date: Date, calendar: Calendar = .current) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d.json", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    static func url(for date: Date, calendar: Calendar = .current) -> URL {
        baseURL.appendingPathComponent(fileName(for: date, calendar: calendar))
    }

    // MARK: - Decode

    /// Decode a daily-challenge JSON payload into the runtime model.
    /// Returns nil on malformed data (caller falls back / retries).
    static func gameContent(fromJson data: Data) -> GameContent? {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        guard let payload = try? decoder.decode(Payload.self, from: data) else { return nil }
        let game = payload.game

        let moves = game.moves.map { move in
            ContentMove(
                ply: move.ply,
                uci: move.uci,
                san: move.san,
                fenBefore: move.fenBefore,
                mover: ContentStore.mover(fromFen: move.fenBefore),
                isGuessPoint: move.isGuessPoint,
                tags: (move.tags ?? []).compactMap(GuessTag.init(rawValue:)),
                annotation: move.annotation,
                candidateEvals: move.isGuessPoint
                    ? ContentStore.clampedEvals(move.legalEvals ?? [:])
                    : [:],
                difficulty: move.difficulty ?? 1200
            )
        }

        return GameContent(
            id: game.id,
            white: game.white,
            black: game.black,
            event: game.event ?? "",
            year: game.year ?? 0,
            result: game.result ?? "*",
            heroColor: game.heroColor == "black" ? .black : .white,
            title: game.title ?? game.id,
            narrativeIntro: game.narrativeIntro ?? "",
            startFen: moves.first?.fenBefore ?? FEN.start,
            moves: moves
        )
    }
}
