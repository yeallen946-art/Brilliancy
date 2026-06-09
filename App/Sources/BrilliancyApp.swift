import SwiftUI

/// App entry point. M0 boots straight into a board sandbox so we can verify
/// "load any FEN + make legal moves" in the simulator. Real navigation
/// (DailyChallenge / Training / GuessSession) arrives in M1+.
@main
struct BrilliancyApp: App {
    var body: some Scene {
        WindowGroup {
            BoardSandboxView()
        }
    }
}
