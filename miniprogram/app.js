// 后端地址：默认值写在 config.js 里（改地址改那个文件）。
// 单台设备想临时改，用「我的 → 服务器地址」，只存本地、不影响别人。
const { API_BASE } = require('./config.js');
const DEFAULT_API = API_BASE || 'http://127.0.0.1:8000';

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
