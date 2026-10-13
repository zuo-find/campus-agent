const app = getApp();

Page({
  data: {
    messages: [],        // {role:'user'|'assistant', content, sources?}
    input: '',
    loading: false,
    scrollTop: 0,
    quickAsks: ['帮我算一下绩点', '请假3天怎么走流程', '挂科了怎么重修', '奖学金怎么评']
  },

  onLoad() {
    this.setData({
      messages: [{ role: 'assistant', content: '你好！我是校园助手 👋 可以问我制度流程，也能帮你算绩点、查成绩、写请假条。' }]
    });
  },

  onInput(e) { this.setData({ input: e.detail.value }); },

  onQuick(e) { this.setData({ input: e.currentTarget.dataset.q }, () => this.send()); },

  send() {
    const text = (this.data.input || '').trim();
    if (!text || this.data.loading) return;

    const history = this.data.messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }));

    const messages = this.data.messages.concat([{ role: 'user', content: text }]);
    this.setData({ messages, input: '', loading: true }, this.scrollToBottom);

    wx.request({
      url: app.globalData.apiBase + '/chat',
      method: 'POST',
      data: {
        message: text,
        history: history,
        courses: app.getCourses(),
        ddls: app.getDdls(),
        user_name: app.globalData.userName
      },
      timeout: 30000,
      success: (res) => {
        const d = res.data || {};
        if (d.ok) {
          const srcs = (d.sources || []).map(s => s.source);
          this.appendAssistant(d.reply || '（没有返回内容）', [...new Set(srcs)]);
        } else {
          this.appendAssistant('出错了：' + (d.error || '未知错误'));
        }
      },
      fail: () => this.appendAssistant('连接后端失败，请确认后端已启动、域名已配置。'),
      complete: () => this.setData({ loading: false }, this.scrollToBottom)
    });
  },

  appendAssistant(content, sources) {
    const messages = this.data.messages.concat([{ role: 'assistant', content, sources }]);
    this.setData({ messages }, this.scrollToBottom);
  },

  scrollToBottom() {
    this.setData({ scrollTop: this.data.messages.length * 100000 });
  }
});
