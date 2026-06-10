import SwiftUI

/// Root navigation (UI_FLOW §1): three tabs, V1-restrained — Today / Train / Progress.
/// One shared UserStore instance for the whole app (single connection to user.sqlite),
/// and one EntitlementStore injected into the environment — the only premium gate
/// (TECH_SPEC §6).
struct RootTabView: View {
    @State private var userStore = UserStore.onDisk()
    @State private var entitlements = EntitlementStore()

    var body: some View {
        TabView {
            HomeView(userStore: userStore)
                .tabItem { Label("Today", systemImage: "calendar") }
            TrainView(userStore: userStore)
                .tabItem { Label("Train", systemImage: "square.grid.2x2") }
            ProgressTabView(userStore: userStore)
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
        }
        .environment(entitlements)
        .task { await entitlements.start() }
        .preferredColorScheme(.dark)
        .tint(Theme.gold)
    }
}
