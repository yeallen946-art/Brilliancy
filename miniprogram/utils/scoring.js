// 计分(TECH_SPEC §3.2 的纯函数移植)。
// 常量必须与 App/Sources/Core/Scoring/ScoringConfig 保持一致 —— 两端的
// 单一事实来源是 TECH_SPEC §3.2 的表;任何调参两边同步改。
const CONFIG = {
  bucketBest: 10,
  bucketExcellent: 40,
  bucketGood: 80,
  bucketInaccuracy: 150,
  bucketMistake: 300,
  pointsBest: 100,
  pointsExcellent: 90,
  pointsGood: 70,
  pointsInaccuracy: 45,
  pointsMistake: 20,
  pointsBlunder: 0,
  engineTopToleranceCp: 10,
  missingMoveDeltaCp: 1000,
  mateBaseCp: 30000
};

/** legal_evals 条目 -> 钳制后的 cp(将杀压到 ±mateBaseCp 附近,同 iOS clampedEvals)。 */
function clampedEval(entry) {
  if (entry.mate !== null && entry.mate !== undefined) {
    return entry.mate > 0
      ? CONFIG.mateBaseCp - entry.mate * 100
      : -CONFIG.mateBaseCp - entry.mate * 100;
  }
  return entry.cp != null ? entry.cp : 0;
}

function qualityScore(delta) {
  const d = Math.max(0, delta);
  if (d <= CONFIG.bucketBest) return CONFIG.pointsBest;
  if (d <= CONFIG.bucketExcellent) return CONFIG.pointsExcellent;
  if (d <= CONFIG.bucketGood) return CONFIG.pointsGood;
  if (d <= CONFIG.bucketInaccuracy) return CONFIG.pointsInaccuracy;
  if (d <= CONFIG.bucketMistake) return CONFIG.pointsMistake;
  return CONFIG.pointsBlunder;
}

/** 与 iOS Scoring.evaluate 同构:客观分 + 大师着法保底,旗标驱动色带。 */
function evaluate(guessUci, masterUci, legalEvals) {
  const evals = {};
  for (const uci in legalEvals) evals[uci] = clampedEval(legalEvals[uci]);

  const values = Object.values(evals);
  const best = values.length ? Math.max.apply(null, values) : null;
  const masterEval = masterUci in evals ? evals[masterUci] : best;
  const isMatch = guessUci === masterUci;
  const guessEval = guessUci in evals ? evals[guessUci] : null;

  let delta;
  if (best !== null && guessEval !== null) delta = Math.max(0, best - guessEval);
  else if (isMatch) delta = 0;
  else delta = CONFIG.missingMoveDeltaCp;

  const quality = qualityScore(delta);
  const display = Math.max(quality, isMatch ? CONFIG.pointsBest : 0);
  const engineTop = best !== null && guessEval !== null
    && best - guessEval <= CONFIG.engineTopToleranceCp;
  const beatMaster = !isMatch && guessEval !== null && masterEval !== null
    && guessEval > masterEval;

  let band = 'red';
  if (isMatch || beatMaster || display >= CONFIG.pointsGood) band = 'green';
  else if (display >= CONFIG.pointsInaccuracy) band = 'yellow';

  let label = '失误';
  if (beatMaster) label = '比大师还强!';
  else if (isMatch) label = '命中!';
  else if (display === CONFIG.pointsBest) label = '最佳着法!';
  else if (display >= CONFIG.pointsExcellent) label = '极佳';
  else if (display >= CONFIG.pointsGood) label = '好棋';
  else if (display >= CONFIG.pointsInaccuracy) label = '欠准确';
  else if (display >= CONFIG.pointsMistake) label = '错误';

  return { displayPoints: display, band, label, isMatch, engineTop, beatMaster, deltaCp: delta, guessEval };
}

module.exports = { CONFIG, evaluate, clampedEval };
