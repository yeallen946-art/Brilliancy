// 内容获取(TECH_SPEC §11):按日期拉每日挑战 JSON,本地缓存兜底。
// 大陆生产环境必须用境内备案域名(PRD §12.5);GitHub Pages 仅供开发
// (开发者工具勾选"不校验合法域名"即可访问)。上线前改 BASE_URL 一处即可。
const BASE_URL = 'https://yeallen946-art.github.io/brilliancy-content/daily/';
// TODO(上线前): 'https://<境内备案域名>/daily/'

function fileName(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}.json`;
}

/** 拉取某日的每日挑战 payload(与 pipeline build.daily_payload 同构)。
 *  网络优先,成功后写入本地缓存;失败回退缓存。resolve(payload|null)。 */
function fetchDaily(date) {
  const name = fileName(date || new Date());
  const cacheKey = `daily:${name}`;
  return new Promise((resolve) => {
    wx.request({
      url: BASE_URL + name,
      success(res) {
        if (res.statusCode === 200 && res.data && res.data.game) {
          try { wx.setStorageSync(cacheKey, res.data); } catch (e) { /* 缓存满则放过 */ }
          resolve(res.data);
        } else {
          resolve(wx.getStorageSync(cacheKey) || null);
        }
      },
      fail() {
        resolve(wx.getStorageSync(cacheKey) || null);
      }
    });
  });
}

/** 中文优先取字段:annotation_zh 缺失时回退英文(内容尚未双语化的旧 payload)。 */
function zh(move, key) {
  return move[`${key}_zh`] || move[key] || '';
}

module.exports = { fetchDaily, zh, BASE_URL };
