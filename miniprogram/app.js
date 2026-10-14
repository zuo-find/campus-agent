// 全局：后端地址 + 本地存储的成绩/ddl + 登录态
App({
  globalData: {
    // 本地调试：微信开发者工具里关闭「校验合法域名」。上线需换 https 域名并在后台配置。
    apiBase: 'http://127.0.0.1:8000',
    userName: '同学'
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
