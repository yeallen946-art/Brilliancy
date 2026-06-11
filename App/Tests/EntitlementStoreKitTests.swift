import StoreKit
import StoreKitTest
import XCTest
@testable import Brilliancy

/// Automates the purchase half of issue #9 with a local StoreKitTest session:
/// buy -> isPremium flips on; clear transactions -> back to free. Runs headless on
/// the CI macOS runner — no scheme storeKitConfiguration needed because the catalog
/// is bundled into THIS test target (see project.yml).
///
/// ── MACOS-FIXME (StoreKitTest API assumptions, verify on first compile) ────────
/// Written blind on Windows. Assumed API (all documented):
///   1. `SKTestSession(contentsOf: URL)` throwing init.
///   2. `session.disableDialogs = true`, `try session.clearTransactions()`.
///   3. `try await session.buyProduct(productIdentifier: "lifetime")` (iOS 15.2+
///      async variant returning a StoreKit.Transaction).
/// If a signature differs, fix HERE; the assertions stay the same.
/// ────────────────────────────────────────────────────────────────────────────────
@MainActor
final class EntitlementStoreKitTests: XCTestCase {

    private var session: SKTestSession!

    override func setUpWithError() throws {
        let url = try XCTUnwrap(
            Bundle(for: EntitlementStoreKitTests.self)
                .url(forResource: "Brilliancy", withExtension: "storekit"),
            "Brilliancy.storekit must be bundled into the test target (project.yml)")
        session = try SKTestSession(contentsOf: url)
        session.disableDialogs = true
        try session.clearTransactions()
    }

    override func tearDownWithError() throws {
        try session?.clearTransactions()
    }

    /// SKTestSession transactions propagate to `Transaction.currentEntitlements`
    /// asynchronously (the first CI run proved it: the post-buy check ran too early
    /// and the post-clear check then saw the STALE purchase). Poll until the store
    /// reaches the expected state or time out.
    private func waitForPremium(
        _ store: EntitlementStore, toBe expected: Bool, timeout: TimeInterval = 15
    ) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            await store.refreshEntitlements()
            if store.isPremium == expected { return true }
            try? await Task.sleep(nanoseconds: 200_000_000)
        }
        return store.isPremium == expected
    }

    func testLifetimePurchaseUnlocksPremiumAndClearingRevokesIt() async throws {
        let store = EntitlementStore()

        let startsFree = await waitForPremium(store, toBe: false)
        XCTAssertTrue(startsFree, "fresh session must start free")

        _ = try await session.buyProduct(productIdentifier: "lifetime")
        let unlocked = await waitForPremium(store, toBe: true)
        XCTAssertTrue(unlocked, "lifetime purchase must unlock premium")

        try session.clearTransactions()
        let revoked = await waitForPremium(store, toBe: false)
        XCTAssertTrue(revoked, "clearing transactions must return to free")
    }

    func testAnnualSubscriptionUnlocksPremium() async throws {
        let store = EntitlementStore()

        _ = try await session.buyProduct(productIdentifier: "sub.annual")
        let unlocked = await waitForPremium(store, toBe: true)
        XCTAssertTrue(unlocked, "annual subscription must unlock premium")
    }

    func testProductCatalogLoads() async throws {
        let store = EntitlementStore()
        await store.loadProducts()
        XCTAssertEqual(store.products.map(\.id), PremiumProducts.all,
                       "all three products should load from the local catalog, in paywall order")
    }
}
