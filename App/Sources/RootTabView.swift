import SwiftUI

/// Root navigation (UI_FLOW §1): three tabs, V1-restrained — Today / Train / Progress.
/// One shared UserStore instance for the whole app (single connection to user.sqlite).
struct RootTabView: View {
    @State private var userStore = UserStore.onDisk()

    var body: some View {
        TabView {
            HomeView(userStore: userStore)
                .tabItem { Label("Today", systemImage: "calendar") }
            TrainView(userStore: userStore)
                .tabItem { Label("Train", systemImage: "square.grid.2x2") }
            ProgressTabView(userStore: userStore)
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
        }
        .preferredColorScheme(.dark)
        .tint(Theme.gold)
    }
}
