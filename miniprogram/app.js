// Brilliancy 小程序入口(TECH_SPEC §11)。
// 架构铁律与 iOS 端一致:客户端零棋类引擎、零 LLM 调用,一切内容预计算,
// 从 CDN 拉静态 JSON(utils/content.js)。
App({
  globalData: {
    // session 页通过 globalData 接收 today 页装载好的对局(小程序页面间
    // 传大对象的惯用做法;避免 URL 序列化 300KB 的 JSON)。
    currentGame: null,
    // 本局结果,session -> summary。
    lastResult: null
  }
});
