import XCTest

/// Automates the reveal-card walkthrough from issue #10: open a known game from the
/// Train tab, wait through autoplay to the first guess point, play a deliberately
/// weaker legal move by tapping board squares, and assert the reveal shows the
/// points banner, the "You played ..." explanation card, and the master annotation.
///
/// Board taps use normalized coordinates on the single "boardView" accessibility
/// element (8x8 grid, white at the bottom in the Opera game): square center =
/// ((file + 0.5) / 8, (7 - rank + 0.5) / 8).
final class GuessRevealUITests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    private func tapSquare(_ board: XCUIElement, file: Int, rank: Int) {
        let offset = CGVector(dx: (CGFloat(file) + 0.5) / 8.0,
                              dy: (CGFloat(7 - rank) + 0.5) / 8.0)
        board.coordinate(withNormalizedOffset: offset).tap()
    }

    private func tapTrainTab(in app: XCUIApplication) {
        let tabBarButton = app.tabBars.buttons["Train"]
        if tabBarButton.waitForExistence(timeout: 2) {
            tabBarButton.tap()
            return
        }

        let globalButton = app.buttons["Train"].firstMatch
        if globalButton.waitForExistence(timeout: 2) {
            globalButton.tap()
            return
        }

        // iPadOS 26 exposes SwiftUI tabs as floating-tab cells, not a classic tab bar.
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.94)).tap()
    }

    func testWrongGuessShowsExplanationCardAndPointsBanner() {
        let app = XCUIApplication()
        app.launchArguments += ["-skipOnboarding"]
        app.launch()

        // Train tab -> the Opera game (deterministic content, first guess point at
        // move 9 with White to move, white side at the bottom).
        tapTrainTab(in: app)
        let operaRow = app.buttons
            .containing(NSPredicate(format: "label CONTAINS 'Opera'")).firstMatch
        XCTAssertTrue(operaRow.waitForExistence(timeout: 10), "Opera game row should be listed")
        operaRow.tap()

        let begin = app.buttons["beginSessionButton"]
        XCTAssertTrue(begin.waitForExistence(timeout: 10), "context screen should offer Begin")
        begin.tap()

        // Autoplay walks 16 plies (~320ms each); wait for the first guess prompt.
        let prompt = app.staticTexts
            .containing(NSPredicate(format: "label CONTAINS 'What did'")).firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout: 30), "first guess point should arrive")

        // Play a2-a3 (legal everywhere in this position, far below the best move,
        // and not the master move) via tap-select then tap-destination.
        let board = app.descendants(matching: .any)["boardView"]
        XCTAssertTrue(board.waitForExistence(timeout: 10))
        tapSquare(board, file: 0, rank: 1)   // a2
        tapSquare(board, file: 0, rank: 2)   // a3

        // Reveal: points banner + "your move" card + master annotation card.
        let banner = app.descendants(matching: .any)["feedbackPanel"]
        XCTAssertTrue(banner.waitForExistence(timeout: 10), "feedback banner should appear")

        XCTAssertTrue(app.staticTexts["You played a3"].waitForExistence(timeout: 5),
                      "explanation card should name the guess in SAN")
        XCTAssertTrue(app.descendants(matching: .any)["guessExplanationCard"].exists,
                      "weaker guess must get an explanation card")

        let points = app.staticTexts
            .containing(NSPredicate(format: "label ENDSWITH '/100'")).firstMatch
        XCTAssertTrue(points.exists, "banner should show the score, 'NN/100'")

        let master = app.staticTexts
            .containing(NSPredicate(format: "label BEGINSWITH 'Master played'")).firstMatch
        XCTAssertTrue(master.exists, "master annotation card should be shown")
    }

    /// Gap-2 coverage (Jerry 2026-06-11): an engine-EQUAL non-master guess must get
    /// the POSITIVE card. Real curated content never has such a move (the master is
    /// always clearly best), so this uses the DEBUG-only fixture game injected via
    /// launch argument: master e4 (+0.30) with Nf3 tied at +0.25.
    func testEngineEqualGuessShowsPositiveCard() {
        let app = XCUIApplication()
        app.launchArguments += ["-uiTestEqualGuessFixture", "-skipOnboarding"]
        app.launch()

        tapTrainTab(in: app)
        let fixtureRow = app.buttons
            .containing(NSPredicate(format: "label CONTAINS 'Equal Guess'")).firstMatch
        XCTAssertTrue(fixtureRow.waitForExistence(timeout: 10), "fixture game should be listed")
        fixtureRow.tap()

        let begin = app.buttons["beginSessionButton"]
        XCTAssertTrue(begin.waitForExistence(timeout: 10))
        begin.tap()

        // Ply 1 IS the guess point — no autoplay wait.
        let prompt = app.staticTexts
            .containing(NSPredicate(format: "label CONTAINS 'What did'")).firstMatch
        XCTAssertTrue(prompt.waitForExistence(timeout: 10), "guess prompt should appear immediately")

        let board = app.descendants(matching: .any)["boardView"]
        XCTAssertTrue(board.waitForExistence(timeout: 10))
        tapSquare(board, file: 6, rank: 0)   // g1
        tapSquare(board, file: 5, rank: 2)   // f3 — engine-equal, not the master move

        let banner = app.descendants(matching: .any)["feedbackPanel"]
        XCTAssertTrue(banner.waitForExistence(timeout: 10), "feedback banner should appear")

        XCTAssertTrue(app.staticTexts["You played Nf3"].waitForExistence(timeout: 5),
                      "positive card should name the guess in SAN")
        let praise = app.staticTexts
            .containing(NSPredicate(format: "label CONTAINS 'just as strong'")).firstMatch
        XCTAssertTrue(praise.exists, "engine-equal guess must be praised, not criticized")
        XCTAssertTrue(app.staticTexts["100/100"].exists,
                      "engine-equal guess earns full points in the banner")
    }
}
