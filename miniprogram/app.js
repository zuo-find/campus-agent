// 后端地址：默认本机。
// 开发者工具里用它即可；真机 / 体验版要改成电脑的局域网 IP（形如 http://192.168.1.5:8000），
// 在「我的 → 服务器地址」里改，改完存本地，换 WiFi 也不用重新传代码。
const DEFAULT_API = 'http://127.0.0.1:8000';

// 全局：后端地址 + 本地存储的成绩/ddl + 登录态
App({
  globalData: {
    apiBase: DEFAULT_API,
    userName: '同学'
  },

  onLaunch() {
    const saved = wx.getStorageSync('apiBase');
    if (saved) this.globalData.apiBase = saved;
  },

  // 后端地址随时可改；各页面在 onShow 里重新读取，所以不用重启小程序
  setApiBase(url) {
    const u = (url || '').trim().replace(/\/+$/, '');
    this.globalData.apiBase = u || DEFAULT_API;
    if (u) wx.setStorageSync('apiBase', u);
    else wx.removeStorageSync('apiBase');
    return this.globalData.apiBase;
  },

  getCourses() {
    return wx.getStorageSync('courses') || [];
  },
  getDdls() {
    return wx.getStorageSync('ddls') || [];
  },

  // ---- 「我发布的 / 我生成的」本地记录（后端没有账号绑定，先记在本机）----
  getMine(type) {
    return wx.getStorageSync('mine_' + type) || [];
  },
  addMine(type, item) {
    const k = 'mine_' + type;
    const arr = wx.getStorageSync(k) || [];
    arr.unshift(Object.assign({ at: Date.now() }, item));
    wx.setStorageSync(k, arr.slice(0, 50));   // 最多留 50 条
  },
  removeMine(type, index) {
    const k = 'mine_' + type;
    const arr = wx.getStorageSync(k) || [];
    arr.splice(index, 1);
    wx.setStorageSync(k, arr);
  },
  clearMine() {
    ['market', 'lost', 'doc'].forEach(t => wx.removeStorageSync('mine_' + t));
  },

  // ---- 登录态（存本地）----
  getUser() {
    return wx.getStorageSync('user') || null;
  },
  setUser(user) {
    wx.setStorageSync('user', user);
  },
  clearUser() {
    wx.removeStorageSync('user');
  },
  isLoggedIn() {
    const u = this.getUser();
    return !!(u && u.token);
  }
});
