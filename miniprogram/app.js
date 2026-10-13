// 全局：后端地址 + 本地存储的成绩/ddl（随对话发给后端做工具调用）
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
  }
});
