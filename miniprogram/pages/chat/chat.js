const app = getApp();
const API = app.globalData.apiBase;

// 判定哪些字段应该用多行输入（长文本）
const MULTI_KEYS = ['理由', '流程', '目的', '宗旨', '成员', '计划', '预算', '预案', '说明', '描述', '内容'];

Page({
  data: {
    messages: [],        // {role:'user'|'assistant', content, sources?}
    input: '',
    loading: false,
    scrollTop: 0,
    modelLabel: '默认模型',
    docEdit: { show: false, idx: -1, docType: '', title: '', fields: [] },
    quickAsks: ['帮我算一下绩点', '帮我写一份请假条：感冒发烧请2天', '挂科了怎么重修', '奖学金怎么评']
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
          // 若本轮调用了 gen_document，则附带一份可编辑、可导出的材料
          const call = (d.tool_calls || []).find(t => t.name === 'gen_document' && t.result && t.result.ok);
          this.appendAssistant(d.reply || '（没有返回内容）', [...new Set(srcs)], call ? call.result : null);
        } else {
          this.appendAssistant('出错了：' + (d.error || '未知错误'));
        }
      },
      fail: () => this.appendAssistant('连接后端失败，请确认后端已启动、域名已配置。'),
      complete: () => this.setData({ loading: false }, this.scrollToBottom)
    });
  },

  appendAssistant(content, sources, doc) {
    const messages = this.data.messages.concat([{ role: 'assistant', content, sources, doc: doc || null }]);
    this.setData({ messages }, this.scrollToBottom);
  },

  // ---------- 材料生成：字段编辑 + 导出 ----------
  noop() {},

  editDoc(e) {
    const idx = e.currentTarget.dataset.idx;
    const doc = this.data.messages[idx].doc;
    if (!doc) return;
    const fields = doc.fields.map(f => ({
      ...f,
      multi: MULTI_KEYS.some(k => f.label.indexOf(k) >= 0)
    }));
    this.setData({ docEdit: { show: true, idx, docType: doc.doc_type, title: doc.title, fields } });
  },
  closeDocEdit() { this.setData({ 'docEdit.show': false }); },
  onFieldInput(e) {
    const i = e.currentTarget.dataset.i;
    this.setData({ ['docEdit.fields[' + i + '].value']: e.detail.value });
  },
  saveDocEdit() {
    const { idx, docType, fields } = this.data.docEdit;
    const payload = {};
    fields.forEach(f => { payload[f.label] = f.value; });
    wx.showLoading({ title: '更新中…' });
    wx.request({
      url: API + '/doc/render', method: 'POST', timeout: 15000,
      data: { doc_type: docType, fields: payload },
      success: r => {
        const d = r.data || {};
        wx.hideLoading();
        if (d.ok) {
          this.setData({
            ['messages[' + idx + '].doc.text']: d.text,
            ['messages[' + idx + '].doc.fields']: d.fields,
            'docEdit.show': false
          });
          wx.showToast({ title: '已更新' });
        } else {
          wx.showToast({ title: d.msg || '更新失败', icon: 'none' });
        }
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '连接失败', icon: 'none' }); }
    });
  },
  exportDoc(e) {
    const idx = e.currentTarget.dataset.idx;
    const doc = this.data.messages[idx].doc;
    if (!doc) return;
    wx.showLoading({ title: '生成文档…' });
    wx.request({
      url: API + '/doc/export', method: 'POST', timeout: 20000,
      data: { title: doc.title, text: doc.text },
      success: r => {
        const d = r.data || {};
        if (!d.ok) { wx.hideLoading(); wx.showToast({ title: d.msg || '导出失败', icon: 'none' }); return; }
        wx.downloadFile({
          url: API + d.url,
          success: res => {
            wx.hideLoading();
            wx.openDocument({
              filePath: res.tempFilePath, fileType: 'docx', showMenu: true,
              fail: () => wx.showToast({ title: '打开失败，请重试', icon: 'none' })
            });
          },
          fail: () => { wx.hideLoading(); wx.showToast({ title: '下载失败', icon: 'none' }); }
        });
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '连接失败', icon: 'none' }); }
    });
  },

  scrollToBottom() {
    this.setData({ scrollTop: this.data.messages.length * 100000 });
  }
});
