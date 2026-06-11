import Foundation
import StoreKit
import SwiftUI
import UserNotifications

/// S9 Settings (UI_FLOW §3): account (subscription status + restore), daily reminder
/// (the M3 "local notification" item), about. Preference rows (board theme, piece
/// set) arrive when there is more than one option to prefer — no dead toggles in V1.
struct SettingsView: View {
    @Environment(EntitlementStore.self) private var entitlements
    @Environment(\.dismiss) private var dismiss

    @AppStorage("dailyReminderEnabled") private var reminderEnabled = false
    @AppStorage("dailyReminderMinuteOfDay") private var reminderMinuteOfDay
        = DailyReminder.defaultMinuteOfDay
    @State private var notificationsDenied = false

    var body: some View {
        NavigationStack {
            List {
                accountSection
                reminderSection
                aboutSection
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                        .foregroundStyle(Theme.gold)
                }
            }
        }
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("settingsView")
        .alert("Notifications are off", isPresented: $notificationsDenied) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("Enable notifications for Brilliancy in iOS Settings to get the daily reminder.")
        }
        .onChange(of: reminderEnabled) { _, enabled in
            Task { await updateReminder(enabled: enabled) }
        }
        .onChange(of: reminderMinuteOfDay) { _, _ in
            guard reminderEnabled else { return }
            Task { await updateReminder(enabled: true) }
        }
    }

    // MARK: - Sections

    private var accountSection: some View {
        Section("Account") {
            HStack {
                Text("Plan")
                Spacer()
                Text(entitlements.isPremium ? "Premium" : "Free")
                    .foregroundStyle(entitlements.isPremium ? Theme.gold : Theme.textSecondary)
            }
            Button("Restore purchases") {
                Task { await entitlements.restorePurchases() }
            }
            .foregroundStyle(Theme.gold)
            .accessibilityIdentifier("restorePurchasesButton")
        }
        .listRowBackground(Theme.surface)
    }

    private var reminderSection: some View {
        Section {
            Toggle("Daily reminder", isOn: $reminderEnabled)
                .tint(Theme.gold)
                .accessibilityIdentifier("dailyReminderToggle")
            if reminderEnabled {
                DatePicker(
                    "Time",
                    selection: Binding(
                        get: { DailyReminder.date(fromMinuteOfDay: reminderMinuteOfDay) },
                        set: { reminderMinuteOfDay = DailyReminder.minuteOfDay(from: $0) }
                    ),
                    displayedComponents: .hourAndMinute
                )
            }
        } header: {
            Text("Notifications")
        } footer: {
            Text("One local notification a day when a new challenge is ready. Nothing leaves your device.")
        }
        .listRowBackground(Theme.surface)
    }

    private var aboutSection: some View {
        Section("About") {
            HStack {
                Text("Version")
                Spacer()
                Text(Self.versionString).foregroundStyle(Theme.textSecondary)
            }
            Text("Pieces: cburnett by Colin M.L. Burnett \u{00B7} CC BY-SA 3.0")
                .font(.footnote)
                .foregroundStyle(Theme.textSecondary)
        }
        .listRowBackground(Theme.surface)
    }

    static var versionString: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let build = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(build))"
    }

    // MARK: - Reminder plumbing

    private func updateReminder(enabled: Bool) async {
        guard enabled else {
            DailyReminder.cancel()
            return
        }
        let scheduled = await DailyReminder.schedule(minuteOfDay: reminderMinuteOfDay)
        if !scheduled {
            reminderEnabled = false
            notificationsDenied = true
        }
    }
}

/// Daily local notification (PRD §8 retention; TECH_SPEC §10 — V1 is local-only,
/// no remote push, no server). Pure time math is separated for unit tests.
enum DailyReminder {
    static let identifier = "daily-reminder"
    /// 09:00 — late enough to be polite, early enough to start a streak day.
    static let defaultMinuteOfDay = 9 * 60

    // MARK: Pure time math (unit-tested)

    static func components(fromMinuteOfDay minuteOfDay: Int) -> DateComponents {
        var components = DateComponents()
        components.hour = (minuteOfDay / 60) % 24
        components.minute = minuteOfDay % 60
        return components
    }

    static func minuteOfDay(from date: Date, calendar: Calendar = .current) -> Int {
        let parts = calendar.dateComponents([.hour, .minute], from: date)
        return (parts.hour ?? 0) * 60 + (parts.minute ?? 0)
    }

    static func date(fromMinuteOfDay minuteOfDay: Int, calendar: Calendar = .current) -> Date {
        calendar.date(
            bySettingHour: (minuteOfDay / 60) % 24,
            minute: minuteOfDay % 60,
            second: 0,
            of: Date()
        ) ?? Date()
    }

    // MARK: Scheduling

    /// Returns false when notification permission is denied (caller surfaces it).
    static func schedule(minuteOfDay: Int) async -> Bool {
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        guard granted else { return false }

        let content = UNMutableNotificationContent()
        content.title = "Today's game is ready"
        content.body = "A new master game is waiting. Keep your streak alive."
        content.sound = .default

        let trigger = UNCalendarNotificationTrigger(
            dateMatching: components(fromMinuteOfDay: minuteOfDay),
            repeats: true
        )
        center.removePendingNotificationRequests(withIdentifiers: [identifier])
        do {
            try await center.add(UNNotificationRequest(
                identifier: identifier, content: content, trigger: trigger))
            return true
        } catch {
            return false
        }
    }

    static func cancel() {
        UNUserNotificationCenter.current()
            .removePendingNotificationRequests(withIdentifiers: [identifier])
    }
}
