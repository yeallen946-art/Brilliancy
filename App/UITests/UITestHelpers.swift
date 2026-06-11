import XCTest

extension XCTestCase {
    func waitForHome(in app: XCUIApplication, timeout: TimeInterval = 10) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if app.buttons["playTodayButton"].exists ||
                app.buttons["Review"].exists ||
                app.descendants(matching: .any)["archiveLink"].exists ||
                app.buttons["settingsButton"].exists {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.2))
        }
        return false
    }

    func startTodayOrReview(in app: XCUIApplication) {
        let play = app.buttons["playTodayButton"]
        if play.waitForExistence(timeout: 5) {
            play.tap()
            return
        }

        let review = app.buttons["Review"]
        if review.waitForExistence(timeout: 5) {
            review.tap()
            return
        }

        XCTFail("Home should offer Play today's game or Review")
    }
}
