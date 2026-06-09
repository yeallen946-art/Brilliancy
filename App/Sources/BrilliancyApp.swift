import SwiftUI

/// App entry point. M1 boots into HomeView, which launches the sample game's
/// GuessSession. The M0 board sandbox is still reachable from Home for debugging.
@main
struct BrilliancyApp: App {
    var body: some Scene {
        WindowGroup {
            HomeView()
        }
    }
}
