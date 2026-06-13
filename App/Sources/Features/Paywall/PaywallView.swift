import SwiftUI
import StoreKit

/// S8 — the paywall (UI_FLOW §3, TECH_SPEC §6). Custom tier list rather than
/// SubscriptionStoreView because the wireframe puts the lifetime non-consumable in
/// the same picker as the two subscriptions; StoreKit 2 purchase flow underneath.
/// Terms/Privacy links land with App Store submission prep (M6).
struct PaywallView: View {
    @Environment(EntitlementStore.self) private var entitlements
    let trigger: PaywallTrigger
    var onClose: () -> Void

    @State private var selectedID = PremiumProducts.annual
    @State private var purchaseFailed = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: Theme.Space.lg) {
                HStack {
                    Button { onClose() } label: {
                        Image(systemName: "xmark")
                            .font(.headline).foregroundStyle(Theme.textSecondary)
                    }
                    .accessibilityIdentifier("paywallCloseButton")
                    Spacer()
                }

                Text(headline)
                    .font(.system(size: 26, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)

                Text(subcopy)
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)

                VStack(alignment: .leading, spacing: Theme.Space.xs) {
                    benefitRow("Every master game in the library")
                    benefitRow("AI insights: why each move works \u{2014} and why yours fell short")
                    benefitRow("Guess rating, strengths & weaknesses")
                }

                if entitlements.products.isEmpty {
                    Spacer()
                    ProgressView()
                        .tint(Theme.gold)
                    Text("Loading plans\u{2026}")
                        .font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                    Spacer()
                } else {
                    VStack(spacing: Theme.Space.sm) {
                        ForEach(entitlements.products, id: \.id) { product in
                            productRow(product)
                        }
                    }
                    Spacer(minLength: 0)
                    purchaseButton
                }

                Button("Restore purchases") {
                    Task { await entitlements.restorePurchases() }
                }
                .font(.system(size: 13))
                .foregroundStyle(Theme.textSecondary)
            }
            .padding(Theme.Space.md)
        }
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("paywallView")
        .task {
            // Triggers from a fresh launch path may arrive before products loaded.
            if entitlements.products.isEmpty { await entitlements.loadProducts() }
        }
        .onChange(of: entitlements.isPremium) { _, premium in
            if premium { onClose() }
        }
        .alert("That didn't go through", isPresented: $purchaseFailed) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("The purchase couldn't be completed and you weren't charged. Please try again.")
        }
    }

    // MARK: - Trigger-specific copy (TECH_SPEC §6)

    /// Headline framed by where the paywall was summoned from, so the pitch matches
    /// the user's intent rather than a single generic line. The benefit list below
    /// stays constant.
    private var headline: String {
        switch trigger {
        case .postDaily:       return "Want the full breakdown?"
        case .lockedGame:      return "Train these patterns in full"
        case .lockedProgress:  return "See your chess sense grow"
        case .lockedArchive:   return "Replay every daily"
        }
    }

    private var subcopy: String {
        switch trigger {
        case .postDaily:
            return "See the engine line and coach explanation for every move \u{2014} and play the full library of master games."
        case .lockedGame:
            return "Unlock every master game in the library, each with AI insight on why the move works."
        case .lockedProgress:
            return "Unlock your guess-rating history and strengths & weaknesses by theme."
        case .lockedArchive:
            return "Unlock the full archive of past daily challenges, plus the master library."
        }
    }

    // MARK: - Pieces

    private func benefitRow(_ text: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Space.xs) {
            Image(systemName: "checkmark")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.gold)
                .padding(.top, 2)
            Text(text)
                .font(.system(size: 15))
                .foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func productRow(_ product: Product) -> some View {
        let selected = product.id == selectedID
        return Button { selectedID = product.id } label: {
            HStack(spacing: Theme.Space.sm) {
                Image(systemName: selected ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(selected ? Theme.gold : Theme.textSecondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(product.displayName)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(Theme.textPrimary)
                    if let badge = badge(for: product) {
                        Text(badge)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(Theme.gold)
                    }
                }
                Spacer()
                Text(product.displayPrice)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(Theme.textPrimary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .cardSurface(padding: Theme.Space.sm)
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.card)
                    .stroke(selected ? Theme.gold : .clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func badge(for product: Product) -> String? {
        switch product.id {
        case PremiumProducts.annual:
            return product.subscription?.introductoryOffer != nil
                ? "Best value \u{00B7} 7-day free trial" : "Best value"
        case PremiumProducts.lifetime:
            return "Pay once, yours forever"
        default:
            return nil
        }
    }

    private var purchaseButton: some View {
        let selected = entitlements.products.first { $0.id == selectedID }
        let hasTrial = selected?.subscription?.introductoryOffer != nil
        return Button(hasTrial ? "Start free trial" : "Continue") {
            guard let selected else { return }
            Task {
                do {
                    _ = try await entitlements.purchase(selected)
                } catch {
                    purchaseFailed = true
                }
            }
        }
        .buttonStyle(GoldButtonStyle())
        .disabled(selected == nil || entitlements.purchaseInFlight)
        .accessibilityIdentifier("paywallPurchaseButton")
    }
}
