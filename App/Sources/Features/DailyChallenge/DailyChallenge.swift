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
