import Foundation
import GRDB

/// Local user database (TECH_SPEC §4 user.sqlite): guesses, game_results,
/// rating_history, streak. Same GRDB surface as ContentStore (Mac-verified in
/// issue #3): raw SQL + Row, no record types — keep it boring.
@Observable
final class UserStore {
    private let dbQueue: DatabaseQueue
    private(set) var streak: Streak

    init(dbQueue: DatabaseQueue) throws {
        self.dbQueue = dbQueue
        try Self.migrate(dbQueue)
        self.streak = try Self.loadStreak(dbQueue)
    }

    /// On-disk store in Application Support; nil if it can't be opened (callers
    /// degrade to no persistence rather than crashing).
    static func onDisk() -> UserStore? {
        do {
            let dir = FileManager.default.urls(
                for: .applicationSupportDirectory, in: .userDomainMask)[0]
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let dbQueue = try DatabaseQueue(path: dir.appendingPathComponent("user.sqlite").path)
            return try UserStore(dbQueue: dbQueue)
        } catch {
            return nil
        }
    }

    // MARK: - Schema (TECH_SPEC §4)

    private static func migrate(_ dbQueue: DatabaseQueue) throws {
        try dbQueue.write { db in
            try db.execute(sql: """
                CREATE TABLE IF NOT EXISTS guesses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    ply INTEGER NOT NULL,
                    guessed_uci TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS game_results (
                    game_id TEXT NOT NULL,
                    total_score INTEGER NOT NULL,
                    completed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rating_history (
                    rating REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS streak (
                    current INTEGER NOT NULL,
                    longest INTEGER NOT NULL,
                    last_completed_date TEXT
                );
                """)
        }
    }

    // MARK: - Writes

    /// Persist a finished session. `isDaily` additionally advances the streak
    /// (PRD: streak counts daily challenges, not library games).
    func record(_ outcome: GameOutcome, isDaily: Bool,
                calendar: Calendar = .current, now: Date = Date()) {
        let stamp = Self.iso.string(from: now)
        try? dbQueue.write { db in
            for guess in outcome.guesses {
                try db.execute(
                    sql: """
                    INSERT INTO guesses (game_id, ply, guessed_uci, score, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    arguments: [outcome.gameId, guess.ply, guess.uci, guess.score, stamp])
            }
            try db.execute(
                sql: "INSERT INTO game_results (game_id, total_score, completed_at) VALUES (?, ?, ?)",
                arguments: [outcome.gameId, outcome.totalScore, stamp])
            try db.execute(
                sql: "INSERT INTO rating_history (rating, created_at) VALUES (?, ?)",
                arguments: [outcome.finalRating, stamp])
        }
        if isDaily {
            streak = streak.completing(on: now, calendar: calendar)
            saveStreak()
        }
    }

    // MARK: - Reads

    /// Most recent rating snapshot — the next session starts from here (TECH_SPEC §3.3).
    func latestRating(default fallback: Double = 1200) -> Double {
        let stored = try? dbQueue.read { db in
            try Double.fetchOne(
                db, sql: "SELECT rating FROM rating_history ORDER BY rowid DESC LIMIT 1")
        }
        return stored.flatMap { $0 } ?? fallback
    }

    func completedGameIds() -> Set<String> {
        let ids = try? dbQueue.read { db in
            try String.fetchAll(db, sql: "SELECT DISTINCT game_id FROM game_results")
        }
        return Set(ids ?? [])
    }

    // MARK: - Streak persistence (single row)

    private func saveStreak() {
        let last = streak.lastCompletedDay.map { Self.iso.string(from: $0) }
        try? dbQueue.write { db in
            try db.execute(sql: "DELETE FROM streak")
            try db.execute(
                sql: "INSERT INTO streak (current, longest, last_completed_date) VALUES (?, ?, ?)",
                arguments: [streak.current, streak.longest, last])
        }
    }

    private static func loadStreak(_ dbQueue: DatabaseQueue) throws -> Streak {
        try dbQueue.read { db in
            guard let row = try Row.fetchOne(db, sql: "SELECT * FROM streak") else {
                return .initial
            }
            let last: String? = row["last_completed_date"]
            return Streak(
                current: row["current"],
                longest: row["longest"],
                lastCompletedDay: last.flatMap { Self.iso.date(from: $0) }
            )
        }
    }

    private static let iso = ISO8601DateFormatter()
}
