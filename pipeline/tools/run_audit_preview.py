"""One-off: run the 5b claim audit over the owner-authorized preview annotations.

The agent (acting as the audit model, owner-authorized in chat 2026-06-11) extracted
the claims below from pipeline/tools/preview_annotations.json prose; this script runs
the DETERMINISTIC half (audit.check_claims) against facts.py. The extraction lists are
checked into the repo so the run is reproducible/reviewable.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store
from audit import ExtractedClaim, check_claims
from validate import _move_san


def c(cls, quote, piece=None, alt=None):
    return ExtractedClaim(claim_class=cls, quote=quote, piece=piece, alt_uci=alt)


CLAIMS = {
    ("reti-tartakower-1910-2d0490", 17): [
        c("material", "gives up the queen on an empty square - Black's king has to capture"),
        c("mate_forced", "the engine confirms a forced mate in three"),
        c("eval_verdict", "the only move that wins on the spot"),
        c("named_move", "Qd8+"),
        c("named_move", "Re1", alt="d1e1"), c("eval_verdict", "keeps a small plus", alt="d1e1"),
        c("named_move", "Nf3", alt="g1f3"),
        c("material", "even grabs a pawn on the queenside", alt="g1f3"),
        c("eval_verdict", "the line ends with Black on top", alt="g1f3"),
        c("named_move", "Bb4", alt="d2b4"), c("positional_color", "the attack never lands", alt="d2b4"),
        c("named_move", "Qe2", alt="d3e2"), c("eval_verdict", "Black stands clearly better", alt="d3e2"),
    ],
    ("reti-tartakower-1910-2d0490", 19): [
        c("positional_color", "the point of the queen sacrifice"),
        c("mate_forced", "the engine shows forced mate next move"),
        c("eval_verdict", "alternatives leave Black firmly in control"),
        c("named_move", "Bg5+"),
        c("named_move", "Nf3", alt="g1f3"),
        c("material", "gives some material back on his own terms", alt="g1f3"),
        c("named_move", "Ba5+", alt="d2a5"), c("eval_verdict", "White far behind", alt="d2a5"),
        c("named_move", "Bf4+", alt="d2f4"),
        c("material", "picks the queen back up after the check", alt="d2f4"),
        c("named_move", "Bc3+", alt="d2c3"),
        c("material", "the same regain-the-queen idea", alt="d2c3"),
    ],
    ("reti-tartakower-1910-2d0490", 21): [
        c("mate_now", "the bishop delivers mate", piece="bishop"),
        c("mate_now", "the rook covers the king's escape squares", piece="rook"),
        c("named_move", "Bd8#"),
        c("eval_verdict", "the quiet tries instead simply lose"),
        c("named_move", "Be3", alt="g5e3"), c("eval_verdict", "leaves Black clearly winning", alt="g5e3"),
        c("named_move", "Nf3", alt="g1f3"), c("material", "force a queen trade and grab the bishop", alt="g1f3"),
        c("named_move", "f4", alt="f2f4"), c("material", "the bishop falls", alt="f2f4"),
        c("named_move", "Nh3", alt="g1h3"), c("material", "the bishop falls and the game with it", alt="g1h3"),
    ],
    ("morphy-isouard-1858-f7f676", 17): [
        c("positional_color", "keeps Black tied up - the king is still in the centre and development is badly behind"),
        c("eval_verdict", "At +2.5 White is clearly better"),
        c("named_move", "Bg5"),
        c("named_move", "Be3", alt="c1e3"), c("named_move", "a4", alt="a2a4"),
        c("named_move", "O-O", alt="e1g1"), c("named_move", "g4", alt="g2g4"),
        c("eval_verdict", "the advantage dwindles", alt="g2g4"),
    ],
    ("morphy-isouard-1858-f7f676", 19): [
        c("material", "grabs a pawn and tears at the queenside"),
        c("material", "checks and a queen trade"),
        c("eval_verdict", "leaves White at +3.3 with the attack rolling"),
        c("named_move", "Nxb5"),
        c("named_move", "Bxf6", alt="g5f6"),
        c("named_move", "Bxb5", alt="c4b5"), c("material", "wins the pawn the slow way", alt="c4b5"),
        c("named_move", "Be2", alt="c4e2"),
        c("named_move", "Bd5", alt="c4d5"), c("material", "the trades leave only a tiny edge", alt="c4d5"),
    ],
    ("morphy-isouard-1858-f7f676", 23): [
        c("positional_color", "the king reaches safety and the rook enters the game"),
        c("eval_verdict", "At +5.5 every white piece is working"),
        c("named_move", "Bxf6", alt="g5f6"), c("named_move", "a3", alt="a2a3"),
        c("named_move", "O-O", alt="e1g1"),
        c("material", "a raid that costs White heavily in the line", alt="e1g1"),
    ],
    ("morphy-isouard-1858-f7f676", 25): [
        c("material", "the forcing sequence that follows wins material"),
        c("eval_verdict", "the engine reads +5.4 and climbing"),
        c("named_move", "Rxd7"),
        c("named_move", "Rd3", alt="d1d3"), c("named_move", "Ba4", alt="b5a4"),
        c("named_move", "Rd5", alt="d1d5"), c("named_move", "Kb1", alt="c1b1"),
    ],
    ("morphy-isouard-1858-f7f676", 27): [
        c("positional_color", "brings the last piece into the attack"),
        c("eval_verdict", "At +5.2 Black has no good way to untangle"),
        c("named_move", "Rd1"),
        c("named_move", "Bxf6", alt="g5f6"), c("named_move", "c3", alt="c2c3"),
        c("named_move", "Ba4", alt="b5a4"), c("named_move", "f4", alt="f2f4"),
    ],
    ("morphy-isouard-1858-f7f676", 29): [
        c("material", "the forcing line wins material"),
        c("eval_verdict", "+7.0 with the finish in sight"),
        c("named_move", "Bxd7+"),
        c("named_move", "Bxf6", alt="g5f6"), c("named_move", "Qc3", alt="b3c3"),
        c("named_move", "Rxd7", alt="d1d7"),
        c("material", "Black's queen strikes back at White's", alt="d1d7"),
        c("named_move", "Qxe6+", alt="b3e6"),
        c("material", "trades queens and wins a piece in the line", alt="b3e6"),
    ],
    ("morphy-isouard-1858-f7f676", 31): [
        c("material", "gives up the queen"),
        c("positional_color", "the knight is forced to take, and that single deflection decides"),
        c("mate_forced", "the engine confirms forced mate next move"),
        c("eval_verdict", "the quieter queen moves keep a big advantage"),
        c("named_move", "Qb8+"),
        c("named_move", "Qb7", alt="b3b7"), c("named_move", "Qc3", alt="b3c3"),
        c("named_move", "Qb5", alt="b3b5"), c("named_move", "Rd5", alt="d1d5"),
        c("eval_verdict", "the game is level again", alt="d1d5"),
    ],
    ("morphy-isouard-1858-f7f676", 33): [
        c("mate_now", "the rook delivers mate", piece="rook"),
        c("mate_now", "the bishop covers the king's escape squares", piece="bishop"),
        c("named_move", "Rd8#"),
        c("named_move", "f4", alt="f2f4"), c("named_move", "Bh4", alt="g5h4"),
        c("named_move", "Kb1", alt="c1b1"), c("named_move", "Be3", alt="g5e3"),
        c("material", "snap off a pawn", alt="g5e3"),
    ],
}


def main() -> int:
    total = 0
    for gid in ("reti-tartakower-1910-2d0490", "morphy-isouard-1858-f7f676"):
        game = store.load_game(gid)
        guess_points = [m for m in game.moves if m.is_guess_point]
        for move in guess_points:
            claims = CLAIMS.get((gid, move.ply), [])
            upcoming = [_move_san(m) for m in guess_points if m.ply > move.ply]
            errors = check_claims(gid, move, claims, upcoming)
            total += len(errors)
            for e in errors:
                print(f"[{e.code}] {e.game_id} ply {e.ply}: {e.message}")
            print(f"{gid} ply {move.ply}: {len(claims)} claim(s), {len(errors)} error(s)")
    if total:
        print(f"\nAUDIT FAIL: {total} error(s).")
        return 1
    print("\nAUDIT OK: every extracted claim verified against facts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
