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
        let entries = isGuessPoint ? evalEntries(fromJson: row["legal_evals"]) : [:]
        return ContentMove(
            ply: row["ply"],
            uci: row["uci"],
            san: row["san"],
            fenBefore: fenBefore,
            mover: mover(fromFen: fenBefore),
            isGuessPoint: isGuessPoint,
            tags: tags(fromJson: row["tags"]),
            annotation: row["annotation"],
            candidateEvals: clampedEvals(entries),
            candidateDetails: candidateDetails(entries),
            altAnnotations: isGuessPoint ? stringMap(fromJson: row["alt_annotations"]) : [:],
            difficulty: row["difficulty"] ?? 1200
        )
    }

    /// Side to move from the FEN's second field ("w"/"b").
    static func mover(fromFen fen: String) -> PieceColor {
        fen.split(separator: " ").dropFirst().first == "b" ? .black : .white
    }

    /// Decode a legal_evals JSON blob ({uci: {cp, mate, refutation_pv, san, ...}}).
    /// Snake-case strategy for the field names; UCI dictionary keys contain no
    /// underscores so they pass through unchanged (same trick as DailyChallenge).
    static func evalEntries(fromJson json: String?) -> [String: EvalEntry] {
        guard let data = json?.data(using: .utf8) else { return [:] }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return (try? decoder.decode([String: EvalEntry].self, from: data)) ?? [:]
    }

    /// legal_evals JSON ({uci: {cp, mate, ...}}) -> candidateEvals [uci: clamped cp].
    static func candidateEvals(fromJson json: String?) -> [String: Int] {
        clampedEvals(evalEntries(fromJson: json))
    }

    /// Display-only per-candidate info from decoded entries (shared with the daily path).
    static func candidateDetails(_ entries: [String: EvalEntry]) -> [String: CandidateDetail] {
        entries.mapValues { entry in
            CandidateDetail(
                san: entry.san,
                refutationSan: entry.refutationSan ?? [],
                motif: entry.motif
            )
        }
    }

    /// Generic {string: string} JSON (alt_annotations). [:] on garbage.
    static func stringMap(fromJson json: String?) -> [String: String] {
        guard let data = json?.data(using: .utf8),
              let map = try? JSONDecoder().decode([String: String].self, from: data)
        else { return [:] }
        return map
    }

    /// Mate-clamp a decoded legal_evals map. Shared by the DB path and the daily-JSON
    /// path so a mating move always outranks any cp move, identically.
    static func clampedEvals(_ entries: [String: EvalEntry]) -> [String: Int] {
        entries.mapValues { entry in
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

    /// One legal_evals entry. refutation_pv (raw UCI) is intentionally NOT decoded —
    /// the app displays the precomputed refutation_san instead (no SAN gen on device).
    /// Decoded with .convertFromSnakeCase on BOTH the DB and daily-JSON paths.
    struct EvalEntry: Decodable {
        let cp: Int?
        let mate: Int?
        let san: String?
        let refutationSan: [String]?
        let motif: String?
    }
}
