const app = getApp();

Page({
  data: {
    messages: [],        // {role:'user'|'assistant', content, sources?}
    input: '',
    loading: false,
    scrollTop: 0,
    modelLabel: '默认模型',
    quickAsks: ['帮我算一下绩点', '请假3天怎么走流程', '挂科了怎么重修', '奖学金怎么评']
  },

  onLoad() {
    this.setData({
      messages: [{ role: 'assistant', content: '你好！我是校园助手 👋 可以问我制度流程，也能帮你算绩点、查成绩、写请假条。\n\n点上方可切换大模型、填自己的 API Key。' }]
    });
  },

  onShow() {
    // 从「选择大模型」页返回时刷新当前模型显示
    const llm = wx.getStorageSync('llm');
    const label = llm && llm.apiKey
      ? (llm.name || llm.provider) + ' · ' + (llm.model || '')
      : '默认模型';
    this.setData({ modelLabel: label });
  },

  goModel() { wx.navigateTo({ url: '/pages/model/model' }); },

  onInput(e) { this.setData({ input: e.detail.value }); },

  onQuick(e) { this.setData({ input: e.currentTarget.dataset.q }, () => this.send()); },

  send() {
    const text = (this.data.input || '').trim();
    if (!text || this.data.loading) return;

    const history = this.data.messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }));

    // 用户自选的大模型（存本地，随请求发给后端；服务端不落库）
    const llm = wx.getStorageSync('llm');
    const llmPayload = llm && llm.apiKey
      ? { provider: llm.provider, api_key: llm.apiKey, model: llm.model }
      : null;

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
        user_name: app.globalData.userName,
        llm: llmPayload
      },
      timeout: 60000,
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
