import XCTest
@testable import Brilliancy

/// Entitlement gating logic (TECH_SPEC §9 "entitlement gating logic" is a required
/// unit-test area). Pure functions only — no StoreKit; the StoreKit plumbing itself
/// is exercised manually in the simulator via Brilliancy.storekit (sandbox flow).
final class EntitlementTests: XCTestCase {

    // MARK: - PremiumProducts.grantsPremium (table-driven)

    func testGrantsPremium() {
        let cases: [(owned: Set<String>, expected: Bool, name: String)] = [
            ([], false, "nothing owned"),
            (["sub.monthly"], true, "monthly subscription"),
            (["sub.annual"], true, "annual subscription"),
            (["lifetime"], true, "lifetime purchase"),
            (["sub.monthly", "sub.annual"], true, "both subscriptions"),
            (["com.other.app.product"], false, "unknown product id only"),
            (["com.other.app.product", "lifetime"], true, "unknown plus lifetime"),
            (["SUB.MONTHLY"], false, "ids are case-sensitive"),
        ]
        for c in cases {
            XCTAssertEqual(PremiumProducts.grantsPremium(c.owned), c.expected, c.name)
        }
    }

    func testProductCatalogMatchesSpec() {
        // TECH_SPEC §6 / PRD §7: exactly these three products, in paywall order.
        XCTAssertEqual(PremiumProducts.all, ["sub.monthly", "sub.annual", "lifetime"])
    }

    // MARK: - FreeTier

    func testFreeTierUnlocksMarkedSamples() {
        // Curated samples win regardless of library order (TECH_SPEC §6).
        let library = [
            makeGame(id: "game-1"),
            makeGame(id: "game-2", isSample: true),
            makeGame(id: "game-3"),
            makeGame(id: "game-4", isSample: true),
            makeGame(id: "game-5"),
        ]
        XCTAssertEqual(FreeTier.unlockedGameIDs(in: library), ["game-2", "game-4"])
    }

    func testFreeTierFallsBackToFirstThreeWhenNoneMarked() {
        // DB predating is_sample marking: free tier is never empty.
        let library = (1...5).map { makeGame(id: "game-\($0)") }
        let unlocked = FreeTier.unlockedGameIDs(in: library)
        XCTAssertEqual(unlocked, ["game-1", "game-2", "game-3"])
    }

    func testFreeTierWithSmallLibraryUnlocksEverything() {
        let library = [makeGame(id: "only")]
        XCTAssertEqual(FreeTier.unlockedGameIDs(in: library), ["only"])
    }

    func testFreeTierWithEmptyLibrary() {
        XCTAssertTrue(FreeTier.unlockedGameIDs(in: []).isEmpty)
    }

    // MARK: - Fixtures

    private func makeGame(id: String, isSample: Bool = false) -> GameContent {
        GameContent(
            isSample: isSample,
            id: id,
            white: "White",
            black: "Black",
            event: "Test Event",
            year: 2000,
            result: "1-0",
            heroColor: .white,
            title: id,
            narrativeIntro: "",
            startFen: FEN.start,
            moves: []
        )
    }
}
