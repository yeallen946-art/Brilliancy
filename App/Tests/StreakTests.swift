import XCTest
@testable import Brilliancy

/// Table-driven tests for the streak math (TECH_SPEC §4, PRD §4). Fixed UTC calendar
/// so results don't depend on the test machine's timezone.
final class StreakTests: XCTestCase {

    private let calendar: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        return c
    }()

    private func day(_ y: Int, _ m: Int, _ d: Int, hour: Int = 12) -> Date {
        calendar.date(from: DateComponents(year: y, month: m, day: d, hour: hour))!
    }

    func testFirstCompletionStartsStreak() {
        let s = Streak.initial.completing(on: day(2026, 6, 10), calendar: calendar)
        XCTAssertEqual(s.current, 1)
        XCTAssertEqual(s.longest, 1)
        XCTAssertNotNil(s.lastCompletedDay)
    }

    func testSameDayTwiceIsIdempotent() {
        let s1 = Streak.initial.completing(on: day(2026, 6, 10, hour: 9), calendar: calendar)
        let s2 = s1.completing(on: day(2026, 6, 10, hour: 22), calendar: calendar)
        XCTAssertEqual(s2, s1)
    }

    func testConsecutiveDaysIncrement() {
        var s = Streak.initial
        s = s.completing(on: day(2026, 6, 10), calendar: calendar)
        s = s.completing(on: day(2026, 6, 11), calendar: calendar)
        s = s.completing(on: day(2026, 6, 12), calendar: calendar)
        XCTAssertEqual(s.current, 3)
        XCTAssertEqual(s.longest, 3)
    }

    func testGapResetsCurrentButKeepsLongest() {
        var s = Streak.initial
        s = s.completing(on: day(2026, 6, 10), calendar: calendar)
        s = s.completing(on: day(2026, 6, 11), calendar: calendar)
        s = s.completing(on: day(2026, 6, 14), calendar: calendar) // missed 12th + 13th
        XCTAssertEqual(s.current, 1)
        XCTAssertEqual(s.longest, 2)
    }

    func testRebuildingPastLongestUpdatesIt() {
        var s = Streak(current: 1, longest: 2, lastCompletedDay: day(2026, 6, 20))
        s = s.completing(on: day(2026, 6, 21), calendar: calendar)
        XCTAssertEqual(s.current, 2)
        XCTAssertEqual(s.longest, 2)
        s = s.completing(on: day(2026, 6, 22), calendar: calendar)
        XCTAssertEqual(s.current, 3)
        XCTAssertEqual(s.longest, 3)
    }

    func testClockGoingBackwardsIsIgnored() {
        let s1 = Streak.initial.completing(on: day(2026, 6, 10), calendar: calendar)
        let s2 = s1.completing(on: day(2026, 6, 8), calendar: calendar)
        XCTAssertEqual(s2, s1)
    }

    func testLateNightToEarlyMorningCountsAsConsecutive() {
        // 23:50 on the 10th, then 00:10 on the 11th — calendar days, not 24h windows.
        var s = Streak.initial
        s = s.completing(on: day(2026, 6, 10, hour: 23), calendar: calendar)
        s = s.completing(on: day(2026, 6, 11, hour: 0), calendar: calendar)
        XCTAssertEqual(s.current, 2)
    }
}
