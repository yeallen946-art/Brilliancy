// S1 今日挑战:拉取当日 payload,展示中文标题/引言,进入对局。
const content = require('../../utils/content');

Page({
  data: { loading: true, failed: false, title: '', subtitle: '', intro: '' },

  onShow() { this.load(); },

  load() {
    this.setData({ loading: true, failed: false });
    content.fetchDaily(new Date()).then((payload) => {
      if (!payload) {
        this.setData({ loading: false, failed: true });
        return;
      }
      const game = payload.game;
      getApp().globalData.currentGame = game;
      this.setData({
        loading: false,
        title: game.title_zh || game.title || game.id,
        subtitle: `${game.white} vs ${game.black} · ${game.event || ''} ${game.year || ''}`,
        intro: game.narrative_intro_zh || game.narrative_intro || ''
      });
    });
  },

  start() {
    if (!getApp().globalData.currentGame) return;
    wx.navigateTo({ url: '/pages/session/session' });
  },

  retry() { this.load(); }
});
