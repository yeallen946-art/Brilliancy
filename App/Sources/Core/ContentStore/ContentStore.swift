import Foundation
import GRDB

/// Read-only access to the bundled content.sqlite built by the pipeline (TECH_SPEC §3/§4).
/// This replaces the generated Swift literals as the way pipeline content reaches the app:
/// rebuild the DB (7_build.py), re-copy, and new games appear — no code generation.
///
/// ── MACOS-FIXME (GRDB API assumptions, verify on first compile) ────────────────
/// Written blind on Windows. Assumptions about GRDB (all standard, documented API):
///   1. `var config = Configuration(); config.readonly = true;
///      DatabaseQueue(path:configuration:)` opens an on-disk DB read-only.
///   2. `try dbQueue.read { db in ... }`, `try Row.fetchAll(db, sql:arguments:)`.
///   3. `row["col"]` infers types: `let s: String = row["white"]`,
///      optionals via `let i: Int? = row["eval_cp"]`.
/// If any differ, fix HERE — the public surface (bundledGames/games(in:)) stays stable.
/// ────────────────────────────────────────────────────────────────────────────────
enum ContentStore {

    /// Mate scores clamped to a large cp so a mating move outranks any cp eval
    /// (TECH_SPEC §3.2 "clamped at mate scores"; mirrors pipeline gen_app_game.py).
    static let mateBaseCp = 30000

    /// Load every game from the content DB bundled in the app, ordered by id.
    /// Returns [] if the bundle has no DB or it can't be read (callers fall back).
    static func bundledGames() -> [GameContent] {
        guard let url = Bundle.main.url(forResource: "content", withExtension: "sqlite") else {
            return []
        }
        do {
            var config = Configuration()
            config.readonly = true
            let dbQueue = try DatabaseQueue(path: url.path, configuration: config)
            return try dbQueue.read { db in try games(in: db) }
        } catch {
            return []
        }
    }

    /// Core reader, separated from the bundle lookup so tests can run it against an
    /// in-memory database with the same schema.
    static func games(in db: Database) throws -> [GameContent] {
        let gameRows = try Row.fetchAll(db, sql: "SELECT * FROM games ORDER BY id")
        return try gameRows.map { gameRow in
            let id: String = gameRow["id"]
            let moveRows = try Row.fetchAll(
                db,
                sql: "SELECT * FROM moves WHERE game_id = ? ORDER BY ply",
                arguments: [id]
            )
            let moves = moveRows.map(contentMove(from:))
            let heroColor: String? = gameRow["hero_color"]
            return GameContent(
                id: id,
                white: gameRow["white"] ?? "Unknown",
                black: gameRow["black"] ?? "Unknown",
                event: gameRow["event"] ?? "",
                year: gameRow["year"] ?? 0,
                result: gameRow["result"] ?? "*",
                heroColor: heroColor == "black" ? .black : .white,
                title: gameRow["title"] ?? id,
                narrativeIntro: gameRow["narrative_intro"] ?? "",
                startFen: moves.first?.fenBefore ?? FEN.start,
                moves: moves
            )
        }
    }

    // MARK: - Row mapping

    private static func contentMove(from row: Row) -> ContentMove {
        let fenBefore: String = row["fen_before"]
        let isGuessPoint = (row["is_guess_point"] as Int? ?? 0) == 1
        return ContentMove(
            ply: row["ply"],
            uci: row["uci"],
            san: row["san"],
            fenBefore: fenBefore,
            mover: mover(fromFen: fenBefore),
            isGuessPoint: isGuessPoint,
            tags: tags(fromJson: row["tags"]),
            annotation: row["annotation"],
            candidateEvals: isGuessPoint ? candidateEvals(fromJson: row["legal_evals"]) : [:],
            difficulty: row["difficulty"] ?? 1200
        )
    }

    /// Side to move from the FEN's second field ("w"/"b").
    static func mover(fromFen fen: String) -> PieceColor {
        fen.split(separator: " ").dropFirst().first == "b" ? .black : .white
    }

    /// legal_evals JSON ({uci: {cp, mate, ...}}) -> candidateEvals [uci: clamped cp].
    static func candidateEvals(fromJson json: String?) -> [String: Int] {
        guard let data = json?.data(using: .utf8),
              let entries = try? JSONDecoder().decode([String: EvalEntry].self, from: data)
        else { return [:] }
        return entries.mapValues { entry in
            if let mate = entry.mate {
                return mate > 0 ? mateBaseCp - mate * 100 : -mateBaseCp - mate * 100
            }
            return entry.cp ?? 0
        }
    }

    static func tags(fromJson json: String?) -> [GuessTag] {
        guard let data = json?.data(using: .utf8),
              let raw = try? JSONDecoder().decode([String].self, from: data)
        else { return [] }
        return raw.compactMap(GuessTag.init(rawValue:))
    }

    /// Only the fields we consume; extra keys (refutation_pv, motif) are ignored.
    struct EvalEntry: Decodable {
        let cp: Int?
        let mate: Int?
    }
}
