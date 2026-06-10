import Foundation

/// Daily-challenge streak math (TECH_SPEC §4 user.sqlite `streak` row; PRD §4).
/// Pure value type — `Calendar` is injected so tests pin the timezone. Persistence
/// (GRDB user DB) wires up with the rest of M3.
struct Streak: Equatable {
    var current: Int
    var longest: Int
    /// Any instant within the day of the last completed daily challenge.
    var lastCompletedDay: Date?

    static let initial = Streak(current: 0, longest: 0, lastCompletedDay: nil)

    /// The streak after completing the daily challenge at `now`.
    /// Same calendar day twice → unchanged. Consecutive day → +1. Gap → reset to 1.
    /// `now` earlier than the last completion (clock skew) → unchanged, never punish.
    func completing(on now: Date, calendar: Calendar = .current) -> Streak {
        if let last = lastCompletedDay {
            if calendar.isDate(last, inSameDayAs: now) {
                return self // today already counted
            }
            let days = calendar.dateComponents(
                [.day],
                from: calendar.startOfDay(for: last),
                to: calendar.startOfDay(for: now)
            ).day ?? Int.max
            if days < 0 {
                return self // clock went backwards — ignore
            }
            if days == 1 {
                let next = current + 1
                return Streak(current: next, longest: max(longest, next), lastCompletedDay: now)
            }
        }
        return Streak(current: 1, longest: max(longest, 1), lastCompletedDay: now)
    }
}
