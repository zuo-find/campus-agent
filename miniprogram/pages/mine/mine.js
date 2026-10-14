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
    pendingAvatar: false,   // 登录后提示去设置头像昵称
    // 数据概览
    stat: { courses: 0, market: 0, lost: 0, doc: 0 },
    // 我生成的材料
    docShow: false, docs: []
  },

  onUnload() { if (this._okTimer) clearTimeout(this._okTimer); },

  onShow() {
    const u = app.getUser();
    const courses = app.getCourses();
    this.setData({
      user: u,
      logged: app.isLoggedIn(),
      shortId: u && u.openid ? u.openid.slice(0, 12) + '…' : '',
      stat: {
        courses: courses.length,
        market: app.getMine('market').length,
        lost: app.getMine('lost').length,
        doc: app.getMine('doc').length
      }
    });
  },

  toggleAgree() { this.setData({ agreed: !this.data.agreed }); },

  // 未登录时点头像 = 一键登录
  tapAvatar() {
    if (this.data.logged) return;
    this.wxLogin();
  },

  openDoc(e) {
    const t = e.currentTarget.dataset.type;
    wx.navigateTo({ url: '/pages/agreement/agreement?type=' + (t === '隐私政策' ? 'privacy' : 'service') });
  },
  goAgreement(e) {
    const type = (e && e.currentTarget && e.currentTarget.dataset.type === 'privacy') ? 'privacy' : 'service';
    wx.navigateTo({ url: '/pages/agreement/agreement?type=' + type });
  },

  // ---- 微信登录 ----
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

  // ---- 头像/昵称授权 ----
  onChooseAvatar(e) {
    const avatar = e.detail.avatarUrl;
    const user = { ...app.getUser(), avatar };
    app.setUser(user);
    this.setData({ user, pendingAvatar: false });
    this.saveProfile();
  },
  onNickBlur(e) {
    const nickname = e.detail.value.trim() || '微信用户';
    const user = { ...app.getUser(), nickname };
    app.setUser(user);
    this.setData({ user });
    this.saveProfile();
  },
  saveProfile() {
    if (!app.isLoggedIn()) return;
    const u = app.getUser();
    wx.request({
      url: API + '/auth/profile', method: 'POST',
      data: { token: u.token, nickname: u.nickname || '', avatar: u.avatar || '' }
    });
  },

  // ---- 我的内容 ----
  goScores() { wx.switchTab({ url: '/pages/scores/scores' }); },
  goLife(e) {
    // switchTab 不能带参数，用全局变量告诉生活页打开哪一栏
    app.globalData.lifeTab = e.currentTarget.dataset.tab || '';
    wx.switchTab({ url: '/pages/life/life' });
  },
  openDocs() {
    this.setData({ docs: app.getMine('doc'), docShow: true });
  },
  closeDocs() { this.setData({ docShow: false }); },
  noop() {},
  copyDoc(e) {
    const t = e.currentTarget.dataset.title;
    wx.setClipboardData({ data: t, success: () => wx.showToast({ title: '标题已复制', icon: 'none' }) });
  },

  // ---- 设置 ----
  goModel() { wx.navigateTo({ url: '/pages/model/model' }); },
  clearLocal() {
    wx.showModal({
      title: '清除本地数据',
      content: '会清空本机保存的成绩、DDL 记录与「我发布的」记录，不影响已同步的官网信息。确定吗？',
      confirmColor: '#e5484d',
      success: r => {
        if (!r.confirm) return;
        wx.removeStorageSync('courses');
        wx.removeStorageSync('ddls');
        app.clearMine();
        this.onShow();
        wx.showToast({ title: '已清除', icon: 'none' });
      }
    });
  },

  // ---- 帮助与关于 ----
  openHelp() { wx.navigateTo({ url: '/pages/help/help' }); },
  openFeedback() {
    wx.showModal({
      title: '意见反馈', showCancel: false, confirmText: '复制联系方式',
      content: '使用中遇到问题或有建议，欢迎反馈：\n\n邮箱：campus-agent@example.com\n（示例地址，请替换为本团队联系邮箱）',
      success: () => wx.setClipboardData({ data: 'campus-agent@example.com' })
    });
  },
  openAbout() {
    wx.showModal({
      title: '关于本作品', showCancel: false, confirmText: '知道了',
      content: '校园服务智能体 · 微信小程序\n\n' +
        '西安思源学院电子信息工程学院\n第二届计算机综合实践挑战赛 · T4 赛道\n\n' +
        '由「校园问答 / 刷题陪练 / 材料撰写 / 日程提醒」四个智能体协同，' +
        '以 RAG 知识库检索 + 大模型 function-calling 实现；' +
        '并支持拍照识别（多模态），可拍题解题、拍通知转待办、拍成绩单导入。\n\n版本 1.0.0'
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
  }
});
