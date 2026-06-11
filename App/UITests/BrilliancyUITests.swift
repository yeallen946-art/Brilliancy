import XCTest

/// Minimal UI smoke test: launch → home → start the sample game → land on the board.
/// Verifies the core navigation wiring end-to-end in the simulator (the part XCTest
/// unit tests can't cover). Element ids are set via `.accessibilityIdentifier(...)`:
///   playTodayButton (HomeView), guessSessionView + feedbackPanel (GuessSessionView),
///   boardView (BoardView).
final class BrilliancyUITests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testLaunchToGuessSession() {
        let app = XCUIApplication()
        app.launchArguments += ["-skipOnboarding"]
        app.launch()

        // Home screen: the primary CTA exists.
        let playButton = app.buttons["playTodayButton"]
        XCTAssertTrue(playButton.waitForExistence(timeout: 10), "Play button should be on Home")

        playButton.tap()

        // We're now in the modal GuessSession with the board visible.
        let session = app.otherElements["guessSessionView"]
        XCTAssertTrue(session.waitForExistence(timeout: 10), "GuessSession should present")

        let board = app.descendants(matching: .any)["boardView"]
        XCTAssertTrue(board.waitForExistence(timeout: 10), "Board should be visible")
    }
}
