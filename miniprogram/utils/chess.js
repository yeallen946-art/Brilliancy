// 零引擎棋盘模型(TECH_SPEC §11 关键设计)。
// 客户端从不做走法生成或合法性判断:
//   - 猜测点的全部合法着法 = payload legal_evals 的键(管线已穷举);
//   - 走子应用是纯机械搬子:易位/吃过路兵/升变都能从 UCI + 棋子类型确定推出。
// 这与 iOS 端"一切预计算"的硬规则同源(CLAUDE.md #2/#5:这里不产生任何
// 走法生成面,SAN 也全部由管线预计算,客户端只显示)。

const FILES = 'abcdefgh';

/** FEN 棋盘段 -> { board: {e4:'P',...}, turn:'w'|'b' }。大写白小写黑。 */
function parseFen(fen) {
  const parts = fen.split(' ');
  const board = {};
  const ranks = parts[0].split('/');
  for (let r = 0; r < 8; r++) {
    let file = 0;
    for (const ch of ranks[r]) {
      if (ch >= '1' && ch <= '8') {
        file += Number(ch);
      } else {
        board[FILES[file] + (8 - r)] = ch;
        file += 1;
      }
    }
  }
  return { board, turn: parts[1] || 'w' };
}

/** 机械应用一手 UCI(就地修改 board)。无任何合法性判断。 */
function applyUci(board, uci) {
  const from = uci.slice(0, 2);
  const to = uci.slice(2, 4);
  const promo = uci[4];
  const piece = board[from];
  if (!piece) return;

  // 吃过路兵:兵斜走到空格 -> 移除被吃的过路兵。
  if ((piece === 'P' || piece === 'p') && from[0] !== to[0] && !board[to]) {
    delete board[to[0] + from[1]];
  }
  // 易位:王横移两格 -> 同排的车跟着搬。
  if ((piece === 'K' || piece === 'k') && Math.abs(FILES.indexOf(to[0]) - FILES.indexOf(from[0])) === 2) {
    const rank = from[1];
    if (to[0] === 'g') { board['f' + rank] = board['h' + rank]; delete board['h' + rank]; }
    if (to[0] === 'c') { board['d' + rank] = board['a' + rank]; delete board['a' + rank]; }
  }
  delete board[from];
  board[to] = promo
    ? (piece === 'P' ? promo.toUpperCase() : promo.toLowerCase())
    : piece;
}

/** 渲染用 64 格数组(白方视角或黑方视角)。 */
function gridFor(board, orientation) {
  const cells = [];
  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 8; col++) {
      const file = orientation === 'b' ? 7 - col : col;
      const rank = orientation === 'b' ? row + 1 : 8 - row;
      const square = FILES[file] + rank;
      cells.push({
        square,
        piece: board[square] || '',
        light: (file + rank) % 2 === 1
      });
    }
  }
  return cells;
}

// 骨架期用 Unicode 棋子字形(零素材依赖);正式版换 cburnett PNG(注意署名)。
const GLYPHS = {
  K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟'
};

module.exports = { parseFen, applyUci, gridFor, GLYPHS };
