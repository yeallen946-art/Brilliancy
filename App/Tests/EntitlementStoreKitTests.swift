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

    func testLifetimePurchaseUnlocksPremiumAndClearingRevokesIt() async throws {
        let store = EntitlementStore()

        await store.refreshEntitlements()
        XCTAssertFalse(store.isPremium, "fresh session must start free")

        _ = try await session.buyProduct(productIdentifier: "lifetime")
        await store.refreshEntitlements()
        XCTAssertTrue(store.isPremium, "lifetime purchase must unlock premium")

        try session.clearTransactions()
        await store.refreshEntitlements()
        XCTAssertFalse(store.isPremium, "clearing transactions must return to free")
    }

    func testAnnualSubscriptionUnlocksPremium() async throws {
        let store = EntitlementStore()

        _ = try await session.buyProduct(productIdentifier: "sub.annual")
        await store.refreshEntitlements()
        XCTAssertTrue(store.isPremium, "annual subscription must unlock premium")
    }

    func testProductCatalogLoads() async throws {
        let store = EntitlementStore()
        await store.loadProducts()
        XCTAssertEqual(store.products.map(\.id), PremiumProducts.all,
                       "all three products should load from the local catalog, in paywall order")
    }
}
