import SwiftUI

/// App entry point — boots the three-tab root (UI_FLOW §1: Today / Train / Progress).
/// The M0 board sandbox is still reachable from Home for debugging.
@main
struct BrilliancyApp: App {
    var body: some Scene {
        WindowGroup {
            RootTabView()
        }
    }
}
