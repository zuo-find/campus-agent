const app = getApp();
let API = app.globalData.apiBase;   // 在 onShow 里刷新，改地址后无需重启

// 昵称还是微信的默认值 = 没设过
function needsNick(u) {
  return !u || !u.nickname || u.nickname === '微信用户';
}

Page({
  data: {
    user: null,             // { token, openid, nickname, avatar }
    logged: false,
    logging: false,
    agreed: false,          // 是否勾选用户协议
    shortId: '',
    justLogged: false,      // 登录成功横幅
    profileHint: '',        // 头像/昵称的引导文案（没填完才显示）
    nickFocus: false,       // 选完头像后自动聚焦昵称输入框
    // 数据概览
    stat: { courses: 0, market: 0, lost: 0, doc: 0 },
    // 我生成的材料
    docShow: false, docs: [],
    // 服务器地址（真机 / 体验版用）
    srvShow: false, srvUrl: '', srvMsg: '', srvOk: false, srvTesting: false,
    apiShort: ''
  },

  onUnload() {
    if (this._okTimer) clearTimeout(this._okTimer);
    if (this._nickTimer) clearTimeout(this._nickTimer);
  },

  onShow() {
    API = app.globalData.apiBase;
    const u = app.getUser();
    const courses = app.getCourses();
    this.setData({
      user: u,
      logged: app.isLoggedIn(),
      shortId: u && u.openid ? u.openid.slice(0, 12) + '…' : '',
      profileHint: this.hintFor(u),
      apiShort: (app.globalData.apiBase || '').replace(/^https?:\/\//, ''),
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
                justLogged: true, profileHint: this.hintFor(user)
              });
              if (this._okTimer) clearTimeout(this._okTimer);
              this._okTimer = setTimeout(() => this.setData({ justLogged: false }), 2600);
            } else {
              this.fail('登录失败：' + (d.error || ''));
            }
          },
          fail: () => this.fail(app.netFailHint()),
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
  // 微信不允许静默拿头像昵称（2022 年 10 月起），只能用这两个控件。
  // 所以这里做成"一次点击接着一次点击"：点头像 → 选完头像后自动把焦点交给昵称输入框，
  // 键盘上方的「微信昵称」会跟着弹出来，用户点一下就完事，不用自己去找输入框。
  onChooseAvatar(e) {
    const user = { ...app.getUser(), avatar: e.detail.avatarUrl };
    app.setUser(user);
    this.setData({ user, profileHint: this.hintFor(user) });
    this.saveProfile();
    if (needsNick(user)) {
      // 等选择器收起、卡片渲染完再聚焦，太快会被吞掉
      setTimeout(() => this.setData({ nickFocus: true }), 350);
    }
  },
  // 点「用微信昵称」时是**先失焦、后填充**，立刻读 e.detail.value 拿到的是旧值，
  // 所以延迟一下再从输入框本身取值（官方文档给的就是这个绕法）
  onNickBlur() {
    clearTimeout(this._nickTimer);
    this._nickTimer = setTimeout(() => {
      this.createSelectorQuery().select('#nick')
        .fields({ properties: ['value'] }, res => this.applyNick(res && res.value))
        .exec();
    }, 300);
  },
  applyNick(v) {
    const nickname = (v || '').trim() || '微信用户';
    if (nickname === ((this.data.user || {}).nickname || '')) {
      this.setData({ nickFocus: false });   // 没变就别白跑一次请求
      return;
    }
    const user = { ...app.getUser(), nickname };
    app.setUser(user);
    this.setData({ user, nickFocus: false, profileHint: this.hintFor(user) });
    this.saveProfile();
  },

  // 提示文案本身也能点：有头像时去聚焦昵称框（自动聚焦在某些机型会被吞，
  // 这里留个手动兜底），还没头像时提醒去点头像
  onHintTap() {
    const u = this.data.user;
    if (!u || !u.avatar) {
      wx.showToast({ title: '点上面的头像', icon: 'none' });
      return;
    }
    // 先置 false 再置 true，否则值没变化不会重新触发聚焦
    this.setData({ nickFocus: false }, () => {
      setTimeout(() => this.setData({ nickFocus: true }), 60);
    });
  },

  // 没填完时给一句话指路，填完就不显示了
  hintFor(u) {
    if (!u || !u.avatar) return '点上面的头像，一次把微信头像和昵称都用上';
    if (needsNick(u)) return '头像好了，点下面的昵称，把微信昵称也用上';
    return '';
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

  // 服务器地址：开发者工具用 127.0.0.1，真机/体验版要改成电脑的局域网 IP
  openServer() {
    const cur = app.globalData.apiBase || '';
    this.setData({ srvShow: true, srvUrl: cur, srvMsg: '', srvOk: false });
  },
  closeServer() { this.setData({ srvShow: false }); },
  onSrvUrl(e) { this.setData({ srvUrl: e.detail.value, srvMsg: '', srvOk: false }); },

  testServer() {
    const url = (this.data.srvUrl || '').trim().replace(/\/+$/, '');
    if (!/^https?:\/\//i.test(url)) {
      this.setData({ srvMsg: '要填 http:// 或 https:// 开头的完整地址', srvOk: false });
      return;
    }
    this.setData({ srvTesting: true, srvMsg: '' });
    wx.request({
      url: url + '/health', timeout: 8000,
      success: r => {
        const d = r.data || {};
        this.setData({
          srvTesting: false, srvOk: !!d.ok,
          srvMsg: d.ok ? '连上了 · 知识库 ' + (d.docs_indexed || 0) + ' 个片段'
                       : '连上了，但返回的内容不对，确认这是后端地址'
        });
      },
      fail: () => this.setData({
        srvTesting: false, srvOk: false,
        srvMsg: '连不上。确认后端已启动、手机和电脑在同一个 WiFi，地址里的 IP 没写错'
      })
    });
  },

  saveServer() {
    const url = (this.data.srvUrl || '').trim();
    if (url && !/^https?:\/\//i.test(url)) {
      wx.showToast({ title: '地址要以 http:// 开头', icon: 'none' });
      return;
    }
    app.setApiBase(url);
    this.setData({
      srvShow: false,
      apiShort: app.globalData.apiBase.replace(/^https?:\/\//, '')
    });
    wx.showToast({ title: url ? '已保存' : '已恢复默认地址', icon: 'none' });
    // 各页面在下次 onShow 时会读到新地址，不用重启小程序
  },
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
