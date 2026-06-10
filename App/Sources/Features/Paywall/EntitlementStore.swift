import Foundation
import Observation
import StoreKit

/// Product catalog and the pure gating rule (TECH_SPEC §6, PRD §7).
/// Kept outside the store class so unit tests cover it without StoreKit.
enum PremiumProducts {
    static let monthly = "sub.monthly"   // $4.99/mo
    static let annual = "sub.annual"     // $29.99/yr, 7-day trial
    static let lifetime = "lifetime"     // $49.99 non-consumable
    /// Display order for the paywall (S8 wireframe: monthly, annual, lifetime).
    static let all: [String] = [monthly, annual, lifetime]

    /// Owning any one of the known products unlocks premium.
    static func grantsPremium(_ ownedProductIDs: Set<String>) -> Bool {
        !ownedProductIDs.isDisjoint(with: Set(all))
    }
}

/// Single source of truth for premium access (TECH_SPEC §6). ALL feature gating
/// reads `isPremium`; feature code never touches StoreKit transactions directly
/// (CLAUDE.md hard rule). Injected once at the root via `.environment(...)`.
///
/// ── MACOS-FIXME (StoreKit 2 assumptions, verify on first compile) ──────────────
/// Written blind on Windows. Standard documented API only: `Transaction.updates`,
/// `Transaction.currentEntitlements`, `Product.products(for:)`, `product.purchase()`,
/// `AppStore.sync()`. Simulator testing uses App/Brilliancy.storekit (wired into the
/// scheme via project.yml `storeKitConfiguration`).
/// ────────────────────────────────────────────────────────────────────────────────
@MainActor
@Observable
final class EntitlementStore {
    private(set) var isPremium = false
    private(set) var products: [Product] = []
    private(set) var purchaseInFlight = false

    private var updatesTask: Task<Void, Never>?

    /// Launch path: start the transaction listener, then read current entitlements
    /// and the product catalog. Safe to call again (listener starts once).
    func start() async {
        if updatesTask == nil {
            updatesTask = Task { [weak self] in
                for await update in Transaction.updates {
                    if case .verified(let transaction) = update {
                        await transaction.finish()
                    }
                    await self?.refreshEntitlements()
                }
            }
        }
        await refreshEntitlements()
        if products.isEmpty { await loadProducts() }
    }

    func refreshEntitlements() async {
        var owned: Set<String> = []
        for await entitlement in Transaction.currentEntitlements {
            guard case .verified(let transaction) = entitlement,
                  transaction.revocationDate == nil else { continue }
            owned.insert(transaction.productID)
        }
        isPremium = PremiumProducts.grantsPremium(owned)
    }

    func loadProducts() async {
        let loaded = (try? await Product.products(for: PremiumProducts.all)) ?? []
        // Stable catalog order regardless of what StoreKit returns.
        products = PremiumProducts.all.compactMap { id in loaded.first { $0.id == id } }
    }

    /// True when the purchase ended in an entitlement (not cancelled / not pending).
    func purchase(_ product: Product) async throws -> Bool {
        purchaseInFlight = true
        defer { purchaseInFlight = false }
        switch try await product.purchase() {
        case .success(let verification):
            if case .verified(let transaction) = verification {
                await transaction.finish()
            }
            await refreshEntitlements()
            return isPremium
        case .userCancelled, .pending:
            return false
        @unknown default:
            return false
        }
    }

    func restorePurchases() async {
        try? await AppStore.sync()
        await refreshEntitlements()
    }
}
