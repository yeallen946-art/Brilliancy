import XCTest
@testable import Brilliancy

/// DailyReminder pure time math (the UNUserNotificationCenter plumbing is exercised
/// manually in the simulator; scheduling correctness rides on these conversions).
final class SettingsTests: XCTestCase {

    func testComponentsFromMinuteOfDay() {
        let nine = DailyReminder.components(fromMinuteOfDay: 9 * 60)
        XCTAssertEqual(nine.hour, 9)
        XCTAssertEqual(nine.minute, 0)

        let lateEvening = DailyReminder.components(fromMinuteOfDay: 21 * 60 + 45)
        XCTAssertEqual(lateEvening.hour, 21)
        XCTAssertEqual(lateEvening.minute, 45)

        // Out-of-range input wraps instead of producing an invalid trigger.
        let wrapped = DailyReminder.components(fromMinuteOfDay: 25 * 60 + 5)
        XCTAssertEqual(wrapped.hour, 1)
        XCTAssertEqual(wrapped.minute, 5)
    }

    func testMinuteOfDayDateRoundTrip() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!

        for minuteOfDay in [0, 9 * 60, 13 * 60 + 30, 23 * 60 + 59] {
            let date = DailyReminder.date(fromMinuteOfDay: minuteOfDay, calendar: calendar)
            XCTAssertEqual(
                DailyReminder.minuteOfDay(from: date, calendar: calendar),
                minuteOfDay,
                "round trip for \(minuteOfDay)")
        }
    }

    func testDefaultReminderIsNineAM() {
        XCTAssertEqual(DailyReminder.defaultMinuteOfDay, 540)
    }
}
