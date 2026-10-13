const app = getApp();
const API = app.globalData.apiBase;

Page({
  data: {
    user: null,             // { token, openid, nickname, avatar }
    logged: false,
    logging: false,
    // 微信新版头像昵称填写能力
    hasAvatar: false, hasNick: false,
    tapCount: 0
  },

  onShow() {
    const u = app.getUser();
    this.setData({ user: u, logged: app.isLoggedIn() });
  },

  // ---- 微信登录：wx.login → 后端换 openid → 存 token ----
  wxLogin() {
    if (this.data.logging) return;
    this.setData({ logging: true });
    wx.login({
      success: (res) => {
        if (!res.code) { this.fail('获取 code 失败'); return; }
        wx.request({
          url: API + '/auth/login', method: 'POST', timeout: 15000,
          data: { code: res.code },
          success: (r) => {
            const d = r.data || {};
            if (d.ok) {
              const user = { token: d.token, openid: d.openid, nickname: this.data.user?.nickname || '同学', avatar: this.data.user?.avatar || '' };
              app.setUser(user);
              this.setData({ user, logged: true });
              wx.showToast({ title: d.is_real ? '登录成功' : '登录成功(演示模式)', icon: 'none' });
            } else {
              this.fail('登录失败：' + (d.error || ''));
            }
          },
          fail: () => this.fail('连接后端失败'),
          complete: () => this.setData({ logging: false })
        });
      },
      fail: () => this.fail('wx.login 失败')
    });
  },

  // ---- 头像选择（新版能力）----
  onChooseAvatar(e) {
    const avatar = e.detail.avatarUrl;
    this.setData({ 'user.avatar': avatar, hasAvatar: true });
    // 临时路径需上传到服务器才能长期使用；演示阶段先存本地
    this.saveProfile({ avatar });
  },

  onNickInput(e) {
    this.setData({ nickInput: e.detail.value });
  },
  onNickBlur(e) { this.setData({ 'user.nickname': e.detail.value, hasNick: true }); this.saveProfile({ nickname: e.detail.value }); },

  // 长按头像时兜底（部分机型没有 chooseAvatar）
  onChooseAvatarTap(e) {
    // 用 getUserProfile 兜底
    if (wx.getUserProfile) {
      wx.getUserProfile({
        desc: '用于完善会员资料',
        success: (res) => {
          const { nickName, avatarUrl } = res.userInfo;
          app.setUser({ ...this.data.user, nickname: nickName, avatar: avatarUrl });
          this.setData({ user: app.getUser(), hasAvatar: true, hasNick: true });
          this.saveProfile({ nickname: nickName, avatar: avatarUrl });
        }
      });
    }
  },

  saveProfile(patch) {
    if (!app.isLoggedIn()) return;
    const user = app.getUser();
    const merged = { ...user, ...patch };
    app.setUser(merged);
    wx.request({
      url: API + '/auth/profile', method: 'POST',
      data: { token: merged.token, nickname: merged.nickname || '', avatar: merged.avatar || '' }
    });
  },

  logout() {
    wx.showModal({
      title: '退出登录', content: '确定退出当前账号？',
      success: (r) => {
        if (r.confirm) {
          app.clearUser();
          this.setData({ user: null, logged: false, hasAvatar: false, hasNick: false });
        }
      }
    });
  },

  fail(msg) {
    this.setData({ logging: false });
    wx.showToast({ title: msg, icon: 'none' });
  },

  goScores() { wx.switchTab({ url: '/pages/scores/scores' }); },
  goDdl() { wx.switchTab({ url: '/pages/ddl/ddl' }); }
});
