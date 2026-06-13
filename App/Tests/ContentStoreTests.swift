import XCTest
import GRDB
@testable import Brilliancy

/// ContentStore against an in-memory DB using the exact pipeline schema (build.py).
final class ContentStoreTests: XCTestCase {

    /// Schema mirror of pipeline/build.py SCHEMA — keep in sync.
    private func makeDb() throws -> DatabaseQueue {
        let dbQueue = try DatabaseQueue()
        try dbQueue.write { db in
            try db.execute(sql: """
                CREATE TABLE games (
                    id TEXT PRIMARY KEY,
                    white TEXT, black TEXT, event TEXT, year INTEGER, result TEXT, eco TEXT,
                    hero_color TEXT, title TEXT, narrative_intro TEXT, pack_id TEXT, ply_count INTEGER,
                    title_zh TEXT, narrative_intro_zh TEXT, is_sample INTEGER
                );
                CREATE TABLE moves (
                    game_id TEXT, ply INTEGER, san TEXT, uci TEXT, fen_before TEXT,
                    is_guess_point INTEGER, difficulty REAL, tags TEXT,
                    eval_cp INTEGER, eval_mate INTEGER,
                    legal_evals TEXT, annotation TEXT, alt_annotations TEXT,
                    annotation_zh TEXT, alt_annotations_zh TEXT,
                    PRIMARY KEY (game_id, ply)
                );
                CREATE TABLE packs (
                    id TEXT PRIMARY KEY, name TEXT, kind TEXT, description TEXT,
                    price_tier TEXT, sort_order INTEGER, promise TEXT
                );
                """)
            try db.execute(
                sql: """
                INSERT INTO games VALUES
                ('g1', 'White, W.', 'Black, B.', 'Test', 1910, '1-0', 'B15',
                 'white', 'Test Game', 'An intro.', 'p1', 2, NULL, NULL, 1)
                """)
            try db.execute(
                sql: """
                INSERT INTO packs VALUES
                ('p1', 'Test Pack', 'theme', 'A pack.', 'premium', 0, 'Sharpen your tactics.')
                """)
            try db.execute(
                sql: """
                INSERT INTO moves VALUES
                ('g1', 1, 'e4', 'e2e4',
                 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
                 0, 1200.0, '[]', NULL, NULL, '{}', NULL, '{}', NULL, '{}'),
                ('g1', 2, 'e5', 'e7e5',
                 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
                 1, 1450.0, '["tactical"]', 30, NULL,
                 '{"e7e5": {"cp": 30, "mate": null, "refutation_pv": [], "motif": "best"},
                   "f7f5": {"cp": null, "mate": -2, "refutation_pv": ["d1h5", "g7g6"], "motif": "blunder",
                            "san": "f5", "refutation_san": ["Qh5+", "g6"]},
                   "d7d5": {"cp": null, "mate": 3, "refutation_pv": [], "motif": "best"}}',
                 'A fine move.', '{"f7f5": "This walks into a quick king hunt."}',
                 NULL, '{}')
                """)
        }
        return dbQueue
    }

    func testLoadsGameWithMovesAndGuessPoints() throws {
        let games = try makeDb().read { try ContentStore.games(in: $0) }
        XCTAssertEqual(games.count, 1)
        let game = try XCTUnwrap(games.first)
        XCTAssertEqual(game.id, "g1")
        XCTAssertEqual(game.title, "Test Game")
        XCTAssertEqual(game.heroColor, .white)
        XCTAssertEqual(game.heroDisplayName, "White")
        XCTAssertEqual(game.packId, "p1")
        XCTAssertTrue(game.isSample)               // is_sample = 1 in the fixture
        XCTAssertEqual(game.moves.count, 2)
        XCTAssertEqual(game.startFen, "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
        XCTAssertEqual(game.guessPointCount, 1)

        let opening = game.moves[0]
        XCTAssertFalse(opening.isGuessPoint)
        XCTAssertEqual(opening.mover, .white)
        XCTAssertTrue(opening.candidateEvals.isEmpty)

        let guess = game.moves[1]
        XCTAssertTrue(guess.isGuessPoint)
        XCTAssertEqual(guess.mover, .black)        // fen_before says "b"
        XCTAssertEqual(guess.annotation, "A fine move.")
        XCTAssertEqual(guess.tags, [.tactical])
        XCTAssertEqual(guess.difficulty, 1450.0, accuracy: 0.01)
    }

    func testCandidateEvalsClampMateScores() throws {
        let games = try makeDb().read { try ContentStore.games(in: $0) }
        let evals = try XCTUnwrap(games.first?.moves[1].candidateEvals)
        XCTAssertEqual(evals["e7e5"], 30)                                  // plain cp
        XCTAssertEqual(evals["d7d5"], ContentStore.mateBaseCp - 300)       // mate in 3 (for mover)
        XCTAssertEqual(evals["f7f5"], -ContentStore.mateBaseCp + 200)      // mated in 2
        // The mating move must outrank any cp move (TECH_SPEC §3.2 clamp).
        XCTAssertGreaterThan(evals["d7d5"]!, evals["e7e5"]!)
    }

    func testCandidateDetailsAndAltAnnotations() throws {
        let games = try makeDb().read { try ContentStore.games(in: $0) }
        let guess = try XCTUnwrap(games.first?.moves[1])

        // Enriched entry: SAN + refutation SAN + motif surface for display.
        XCTAssertEqual(
            guess.candidateDetails["f7f5"],
            CandidateDetail(san: "f5", refutationSan: ["Qh5+", "g6"], motif: "blunder"))
        // Unenriched entry (older DB): present, with nil san and empty refutation.
        XCTAssertEqual(
            guess.candidateDetails["e7e5"],
            CandidateDetail(san: nil, refutationSan: [], motif: "best"))

        XCTAssertEqual(guess.altAnnotations, ["f7f5": "This walks into a quick king hunt."])
        // Non-guess-point rows carry no candidate data.
        XCTAssertTrue(games.first!.moves[0].altAnnotations.isEmpty)
        XCTAssertTrue(games.first!.moves[0].candidateDetails.isEmpty)
    }

    func testLoadsPacks() throws {
        let packs = try makeDb().read { try ContentStore.packs(in: $0) }
        XCTAssertEqual(packs.count, 1)
        let pack = try XCTUnwrap(packs.first)
        XCTAssertEqual(pack.id, "p1")
        XCTAssertEqual(pack.name, "Test Pack")
        XCTAssertEqual(pack.kind, "theme")
        XCTAssertEqual(pack.priceTier, "premium")
        XCTAssertEqual(pack.promise, "Sharpen your tactics.")
    }

    func testJsonHelpersTolerateGarbage() {
        XCTAssertEqual(ContentStore.candidateEvals(fromJson: nil), [:])
        XCTAssertEqual(ContentStore.candidateEvals(fromJson: "not json"), [:])
        XCTAssertEqual(ContentStore.tags(fromJson: nil), [])
        XCTAssertEqual(ContentStore.tags(fromJson: "[\"unknown_tag\"]"), [])
        XCTAssertEqual(ContentStore.mover(fromFen: "8/8/8/8/8/8/8/8 b - - 0 1"), .black)
    }

    func testHeroDisplayNameHandlesPlainNames() {
        let game = GameContent(
            id: "plain",
            white: "Paul Morphy",
            black: "Duke Karl",
            event: "Test",
            year: 1858,
            result: "1-0",
            heroColor: .white,
            title: "Plain",
            narrativeIntro: "",
            startFen: FEN.start,
            moves: []
        )
        XCTAssertEqual(game.heroDisplayName, "Morphy")
    }
}
