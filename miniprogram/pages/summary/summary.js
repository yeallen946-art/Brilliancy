// S3 总结 + 分享(增长引擎:PRD §12.3 —— 分享卡天然契合微信群/朋友圈)。
// 分享内容只有色带表情和分数,绝不剧透着法(TECH_SPEC §7 同款规则)。
const EMOJI = { green: '🟩', yellow: '🟨', red: '🟥' };

Page({
  data: { score: 0, bandRow: '' },

  onLoad() {
    const result = getApp().globalData.lastResult || { score: 0, bands: [] };
    this.setData({
      score: result.score,
      bandRow: result.bands.map((b) => EMOJI[b] || '🟥').join('')
    });
  },

  onShareAppMessage() {
    return {
      title: `Brilliancy 每日挑战 ${this.data.score} 分 ${this.data.bandRow}`,
      path: '/pages/today/today'
    };
  },

  backToToday() {
    wx.reLaunch({ url: '/pages/today/today' });
  }
});
