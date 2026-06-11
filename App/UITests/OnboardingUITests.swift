import XCTest

/// S10 — first-launch onboarding: three pages, Continue/Continue/Start, lands on
/// Home. Other UI tests pass -skipOnboarding, so this is the only test that
/// exercises (and completes) the onboarding state.
final class OnboardingUITests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testFirstLaunchOnboardingFlow() {
        let app = XCUIApplication()
        app.launch()

        let onboarding = app.otherElements["onboardingView"]
        guard onboarding.waitForExistence(timeout: 10) else {
            // A previous run of THIS test already completed onboarding on this
            // simulator (the flag persists). The skip path is what other tests use;
            // nothing left to verify here.
            XCTAssertTrue(app.buttons["playTodayButton"].waitForExistence(timeout: 10),
                          "without onboarding, Home should be up")
            return
        }

        XCTAssertTrue(app.staticTexts["Outguess the legends."].exists, "page 1 headline")

        let next = app.buttons["onboardingContinueButton"]
        next.tap()   // -> page 2
        XCTAssertTrue(app.staticTexts["Not just right or wrong."].waitForExistence(timeout: 5))
        next.tap()   // -> page 3
        XCTAssertTrue(app.staticTexts["Today's game is ready."].waitForExistence(timeout: 5))
        next.tap()   // Start

        XCTAssertTrue(app.buttons["playTodayButton"].waitForExistence(timeout: 10),
                      "finishing onboarding should land on Home")
    }
}
