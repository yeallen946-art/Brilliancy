import Foundation

#if DEBUG
/// Fixtures injected into the Train list via launch arguments — UI tests only.
/// Needed because curated brilliancies never contain an engine-EQUAL non-master
/// move (the master move is always clearly best), so the positive reveal card
/// can't be exercised end-to-end against real content.
enum UITestFixtures {
    static let equalGuessArgument = "-uiTestEqualGuessFixture"

    /// One guess point at ply 1: master e4 (+0.30), Nf3 tied within the engine-top
    /// tolerance (+0.25) -> guessing Nf3 must show the POSITIVE explanation card.
    static let equalGuessGame = GameContent(
        id: "uitest-equal-guess",
        white: "Fixture White",
        black: "Fixture Black",
        event: "UI Test",
        year: 2026,
        result: "*",
        heroColor: .white,
        title: "UI Fixture: Equal Guess",
        narrativeIntro: "Test fixture. The first move is the guess point.",
        startFen: FEN.start,
        moves: [
            ContentMove(
                ply: 1,
                uci: "e2e4",
                san: "e4",
                fenBefore: FEN.start,
                mover: .white,
                isGuessPoint: true,
                tags: [.positional],
                annotation: "Fixture: the master takes the center.",
                candidateEvals: ["e2e4": 30, "g1f3": 25, "a2a3": -50],
                candidateDetails: [
                    "g1f3": CandidateDetail(san: "Nf3", refutationSan: [], motif: "best"),
                    "a2a3": CandidateDetail(san: "a3", refutationSan: [], motif: "mistake"),
                ]
            )
        ]
    )

    static var isEqualGuessFixtureEnabled: Bool {
        ProcessInfo.processInfo.arguments.contains(equalGuessArgument)
    }
}
#endif
