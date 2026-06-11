// S2 核心猜棋循环(TECH_SPEC §3.1 状态机的小程序版)。
// context -> autoplay(320ms/步,绝不瞬切)-> guess -> reveal -> … -> summary。
// 客户端零引擎:合法着法 = legal_evals 的键;讲解读 *_zh 字段。
const chess = require('../../utils/chess');
const scoring = require('../../utils/scoring');

const STEP_MS = 320;
const MATE_THRESHOLD = 20000;

Page({
  data: {
    phase: 'context',
    cells: [],
    glyphs: chess.GLYPHS,
    title: '', heroLine: '', intro: '',
    prompt: '',
    selected: '', dests: [], emphasis: [],
    feedback: null,        // {label, points, band}
    guessExplain: null,    // {san, text}
    masterSan: '', annotation: ''
  },

  onLoad() {
    const game = getApp().globalData.currentGame;
    if (!game) { wx.navigateBack(); return; }
    this.game = game;
    this.moves = game.moves || [];
    this.index = 0;
    this.results = [];
    const start = this.moves.length ? this.moves[0].fen_before : null;
    this.board = start ? chess.parseFen(start).board : {};
    this.orientation = game.hero_color === 'black' ? 'b' : 'w';
    this.setData({
      title: game.title_zh || game.title || '',
      heroLine: game.hero_color === 'black' ? '你执黑棋' : '你执白棋',
      intro: game.narrative_intro_zh || game.narrative_intro || '',
      cells: chess.gridFor(this.board, this.orientation)
    });
  },

  onUnload() { this.stopTimer(); },

  begin() {
    this.setData({ phase: 'autoplay' });
    this.timer = setInterval(() => this.step(), STEP_MS);
  },

  stopTimer() { if (this.timer) { clearInterval(this.timer); this.timer = null; } },

  step() {
    if (this.index >= this.moves.length) { this.finish(); return; }
    const move = this.moves[this.index];
    if (move.is_guess_point) {
      this.stopTimer();
      this.setData({
        phase: 'guess',
        prompt: `${this.orientation === 'b' ? '黑方' : '白方'}行棋——大师走了哪一步?`,
        selected: '', dests: [], emphasis: []
      });
      return;
    }
    chess.applyUci(this.board, move.uci);
    this.index += 1;
    this.setData({ cells: chess.gridFor(this.board, this.orientation) });
  },

  tapCell(e) {
    if (this.data.phase !== 'guess') return;
    const square = e.currentTarget.dataset.square;
    const move = this.moves[this.index];
    const legal = Object.keys(move.legal_evals || {});

    if (this.data.selected && this.data.dests.indexOf(square) >= 0) {
      const prefix = this.data.selected + square;
      // 升变默认成后(与 iOS 的 M1 行为一致)。
      const exact = legal.indexOf(prefix) >= 0 ? prefix
        : legal.indexOf(prefix + 'q') >= 0 ? prefix + 'q' : null;
      if (exact) { this.submit(exact, move); return; }
    }
    const dests = legal
      .filter((u) => u.slice(0, 2) === square)
      .map((u) => u.slice(2, 4));
    if (dests.length) {
      this.setData({ selected: square, dests });
    } else {
      this.setData({ selected: '', dests: [] });
    }
  },

  submit(guessUci, move) {
    const ev = scoring.evaluate(guessUci, move.uci, move.legal_evals || {});
    this.results.push({ points: ev.displayPoints, band: ev.band });
    this.setData({
      phase: 'reveal',
      feedback: { label: ev.label, points: '+' + ev.displayPoints, band: ev.band },
      guessExplain: this.explain(move, guessUci, ev),
      masterSan: move.san,
      annotation: move.annotation_zh || move.annotation || '',
      selected: '', dests: [],
      emphasis: [guessUci.slice(0, 2), guessUci.slice(2, 4),
                 move.uci.slice(0, 2), move.uci.slice(2, 4)]
    });
  },

  // GuessExplainer 的中文移植:三档——命中合并、同等好棋夸、更差解释。
  // 散文优先用管线的 alt_annotations_zh;模板只陈述引擎数字(硬规则 #1)。
  explain(move, uci, ev) {
    if (ev.isMatch) return null;
    const detail = (move.legal_evals || {})[uci] || {};
    const san = detail.san || uci;
    const prose = (move.alt_annotations_zh || {})[uci];

    if (ev.beatMaster) {
      return { san, text: `引擎其实更偏好 ${san}——比大师的 ${move.san} 还略胜一筹。` };
    }
    if (ev.engineTop) {
      return { san, text: prose || `${san} 与大师着法同样有力——引擎评估不相上下。` };
    }
    if (prose) return { san, text: prose };

    const line = (detail.refutation_san || []).slice(0, 3).join(' ');
    if (ev.guessEval !== null && ev.guessEval <= -MATE_THRESHOLD) {
      return { san, text: line
        ? `走 ${san} 之后,${line} 形成对你的强制将杀。`
        : `走 ${san} 之后,引擎找到对你的强制将杀。` };
    }
    if (ev.deltaCp >= MATE_THRESHOLD) {
      return { san, text: `${san} 放走了强制将杀——制胜手段仍在棋盘上。` };
    }
    const pawns = (ev.deltaCp / 100).toFixed(1);
    return { san, text: line
      ? `走 ${san} 之后,最强应对是 ${line},比这里的最佳着法亏约 ${pawns} 兵。`
      : `走 ${san} 之后,比这里的最佳着法亏约 ${pawns} 兵。` };
  },

  next() {
    const move = this.moves[this.index];
    chess.applyUci(this.board, move.uci);
    this.index += 1;
    this.setData({
      cells: chess.gridFor(this.board, this.orientation),
      phase: 'autoplay', feedback: null, guessExplain: null, emphasis: []
    });
    this.timer = setInterval(() => this.step(), STEP_MS);
  },

  finish() {
    this.stopTimer();
    const n = this.results.length;
    const score = n ? Math.round(this.results.reduce((s, r) => s + r.points, 0) / n) : 0;
    getApp().globalData.lastResult = { score, bands: this.results.map((r) => r.band) };
    wx.redirectTo({ url: '/pages/summary/summary' });
  },

  close() { wx.navigateBack(); }
});
