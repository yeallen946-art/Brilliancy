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

    func testWrongGuessShowsExplanationCardAndPointsBanner() {
        let app = XCUIApplication()
        app.launch()

        // Train tab -> the Opera game (deterministic content, first guess point at
        // move 9 with White to move, white side at the bottom).
        app.tabBars.buttons["Train"].tap()
        let operaRow = app.buttons
            .containing(NSPredicate(format: "label CONTAINS 'Opera'")).firstMatch
        XCTAssertTrue(operaRow.waitForExistence(timeout: 10), "Opera game row should be listed")
        operaRow.tap()

        let begin = app.buttons["Begin"]
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
            .containing(NSPredicate(format: "label BEGINSWITH '+'")).firstMatch
        XCTAssertTrue(points.exists, "banner should show points earned, '+NN'")

        let master = app.staticTexts
            .containing(NSPredicate(format: "label BEGINSWITH 'Master played'")).firstMatch
        XCTAssertTrue(master.exists, "master annotation card should be shown")
    }
}
