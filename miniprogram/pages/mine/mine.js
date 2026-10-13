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

  // 打开协议页（登录卡片里的链接：data-type 传中文标题）
  openDoc(e) {
    const t = e.currentTarget.dataset.type;
    this.goAgreement({ currentTarget: { dataset: { type: t === '隐私政策' ? 'privacy' : 'service' } } });
  },

  // 打开协议页（底部链接：data-type 传 service | privacy）
  goAgreement(e) {
    const type = e && e.currentTarget && e.currentTarget.dataset.type === 'privacy' ? 'privacy' : 'service';
    wx.navigateTo({ url: '/pages/agreement/agreement?type=' + type });
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
