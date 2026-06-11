import XCTest
import GRDB
@testable import Brilliancy

/// UserStore against an in-memory DB — schema, writes, rating continuity, streak
/// persistence across re-init (same queue = same storage).
final class UserStoreTests: XCTestCase {

    private let calendar: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        return c
    }()

    private func day(_ y: Int, _ m: Int, _ d: Int) -> Date {
        calendar.date(from: DateComponents(year: y, month: m, day: d, hour: 12))!
    }

    private func outcome(score: Int = 80, rating: Double = 1234) -> GameOutcome {
        GameOutcome(
            gameId: "g1",
            totalScore: score,
            finalRating: rating,
            guesses: [(ply: 22, uci: "b6a4", score: 100, band: .green),
                      (ply: 26, uci: "a7a6", score: 0, band: .red)]
        )
    }

    func testLatestResultReturnsScoreAndBandsInPlayOrder() throws {
        let store = try UserStore(dbQueue: DatabaseQueue())
        XCTAssertNil(store.latestResult(for: "g1"))

        store.record(outcome(score: 50), isDaily: false, calendar: calendar, now: day(2026, 6, 10))
        store.record(outcome(score: 80), isDaily: false, calendar: calendar, now: day(2026, 6, 11))

        let result = try XCTUnwrap(store.latestResult(for: "g1"))
        XCTAssertEqual(result.score, 80)                  // latest session wins
        XCTAssertEqual(result.bands, [.green, .red])      // play order, from raw values
        XCTAssertNil(store.latestResult(for: "other"))
    }

    func testRecordWritesAllTables() throws {
        let dbQueue = try DatabaseQueue()
        let store = try UserStore(dbQueue: dbQueue)
        store.record(outcome(), isDaily: false, calendar: calendar, now: day(2026, 6, 10))

        let counts = try dbQueue.read { db in
            (guesses: try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM guesses") ?? -1,
             results: try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM game_results") ?? -1,
             ratings: try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM rating_history") ?? -1)
        }
        XCTAssertEqual(counts.guesses, 2)
        XCTAssertEqual(counts.results, 1)
        XCTAssertEqual(counts.ratings, 1)
        XCTAssertEqual(store.completedGameIds(), ["g1"])
    }

    func testLatestRatingContinuity() throws {
        let store = try UserStore(dbQueue: DatabaseQueue())
        XCTAssertEqual(store.latestRating(default: 1200), 1200) // empty -> fallback
        store.record(outcome(rating: 1234), isDaily: false, calendar: calendar, now: day(2026, 6, 10))
        store.record(outcome(rating: 1250), isDaily: false, calendar: calendar, now: day(2026, 6, 11))
        XCTAssertEqual(store.latestRating(default: 1200), 1250) // most recent wins
    }

    func testDailyAdvancesStreakAndPersists() throws {
        let dbQueue = try DatabaseQueue()
        let store = try UserStore(dbQueue: dbQueue)
        store.record(outcome(), isDaily: true, calendar: calendar, now: day(2026, 6, 10))
        store.record(outcome(), isDaily: true, calendar: calendar, now: day(2026, 6, 11))
        XCTAssertEqual(store.streak.current, 2)

        // Re-open over the same storage: streak must come back from the DB.
        let reopened = try UserStore(dbQueue: dbQueue)
        XCTAssertEqual(reopened.streak.current, 2)
        XCTAssertEqual(reopened.streak.longest, 2)
        XCTAssertNotNil(reopened.streak.lastCompletedDay)
    }

    func testLibraryGameDoesNotTouchStreak() throws {
        let store = try UserStore(dbQueue: DatabaseQueue())
        store.record(outcome(), isDaily: false, calendar: calendar, now: day(2026, 6, 10))
        XCTAssertEqual(store.streak, .initial)
    }
}
