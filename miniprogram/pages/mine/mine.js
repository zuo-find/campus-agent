const app = getApp();
const API = app.globalData.apiBase;

Page({
  data: {
    user: null,             // { token, openid, nickname, avatar }
    logged: false,
    logging: false,
    agreed: false,          // 是否勾选用户协议
    shortId: '',
    justLogged: false,      // 登录成功横幅
    pendingAvatar: false    // 登录后提示去设置头像昵称
  },

  onUnload() { if (this._okTimer) clearTimeout(this._okTimer); },

  onShow() {
    const u = app.getUser();
    this.setData({
      user: u,
      logged: app.isLoggedIn(),
      shortId: u && u.openid ? u.openid.slice(0, 12) + '…' : ''
    });
  },

  toggleAgree() { this.setData({ agreed: !this.data.agreed }); },

  // 未登录时点头像 = 一键登录
  tapAvatar() {
    if (this.data.logged) return;
    this.wxLogin();
  },

  openDoc(e) {
    const type = e.currentTarget.dataset.type;
    wx.showModal({
      title: type,
      content: type === '用户协议'
        ? '本作品为校园服务智能体（T4 参赛作品）。登录仅用于识别身份、同步你录入的成绩与使用数据，不会收集或上传你的隐私信息。成绩数据保存在你的手机本地。'
        : '我们仅在小程序内保存你的登录标识（openid）、昵称与头像，用于展示个人信息。不会向任何第三方共享，你可随时退出登录清除本地数据。',
      showCancel: false, confirmText: '我知道了'
    });
  },

  // ---- 微信登录：wx.login → 后端换 openid → 存 token ----
  wxLogin() {
    if (this.data.logging) return;
    if (!this.data.agreed) {
      wx.showToast({ title: '请先阅读并同意用户协议', icon: 'none' });
      return;
    }
    this.setData({ logging: true });
    wx.login({
      success: (res) => {
        if (!res.code) { this.fail('获取登录凭证失败'); return; }
        wx.request({
          url: API + '/auth/login', method: 'POST', timeout: 15000,
          data: { code: res.code },
          success: (r) => {
            const d = r.data || {};
            if (d.ok) {
              const prev = this.data.user || {};
              const user = {
                token: d.token, openid: d.openid,
                nickname: prev.nickname || '微信用户', avatar: prev.avatar || ''
              };
              app.setUser(user);
              this.setData({
                user, logged: true, shortId: d.openid.slice(0, 12) + '…',
                justLogged: true, pendingAvatar: !user.avatar
              });
              // 横幅自动隐藏
              if (this._okTimer) clearTimeout(this._okTimer);
              this._okTimer = setTimeout(() => this.setData({ justLogged: false }), 2600);
            } else {
              this.fail('登录失败：' + (d.error || ''));
            }
          },
          fail: () => this.fail('连接后端失败，请确认后端已启动'),
          complete: () => this.setData({ logging: false })
        });
      },
      fail: () => this.fail('微信登录失败')
    });
  },

  fail(msg) {
    this.setData({ logging: false });
    wx.showToast({ title: msg, icon: 'none' });
  },

  // ---- 头像/昵称授权（微信新版能力）----
  onChooseAvatar(e) {
    const avatar = e.detail.avatarUrl;
    const user = { ...app.getUser(), avatar };
    app.setUser(user);
    this.setData({ user, pendingAvatar: false });
    this.saveProfile({ avatar });
  },

  onNickBlur(e) {
    const nickname = e.detail.value.trim() || '微信用户';
    const user = { ...app.getUser(), nickname };
    app.setUser(user);
    this.setData({ user });
    this.saveProfile({ nickname });
  },

  saveProfile(patch) {
    if (!app.isLoggedIn()) return;
    const u = app.getUser();
    wx.request({
      url: API + '/auth/profile', method: 'POST',
      data: { token: u.token, nickname: u.nickname || '', avatar: u.avatar || '' }
    });
  },

  logout() {
    wx.showModal({
      title: '退出登录', content: '确定退出当前账号？',
      success: (r) => {
        if (r.confirm) {
          app.clearUser();
          this.setData({ user: null, logged: false, agreed: false, shortId: '' });
        }
      }
    });
  },

  goScores() { wx.switchTab({ url: '/pages/scores/scores' }); }
});
