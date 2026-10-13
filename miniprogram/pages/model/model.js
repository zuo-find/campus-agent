const app = getApp();
const API = app.globalData.apiBase;

Page({
  data: {
    providers: [],
    map: {},
    provider: '',
    providerName: '',
    models: [],
    modelIndex: 0,
    apiKey: '',
    keyUrl: '',
    note: ''
  },

  onLoad() {
    const saved = wx.getStorageSync('llm') || null;
    wx.request({
      url: API + '/providers', timeout: 15000,
      success: (r) => {
        const list = (r.data || {}).providers || [];
        const map = {};
        list.forEach(p => { map[p.id] = p; });
        this.setData({ providers: list, map });
        if (saved && map[saved.provider]) {
          this.apply(saved.provider, saved.model, saved.apiKey);
        } else if (list.length) {
          this.apply(list[0].id, '', '');
        }
      },
      fail: () => wx.showToast({ title: '加载厂商列表失败，检查后端', icon: 'none' })
    });
  },

  apply(pid, model, apiKey) {
    const p = this.data.map[pid];
    if (!p) return;
    const idx = Math.max(0, p.models.indexOf(model));
    this.setData({
      provider: pid, providerName: p.name, models: p.models,
      modelIndex: idx, apiKey: apiKey || '', keyUrl: p.key_url || '', note: p.note || ''
    });
  },

  chooseProvider(e) { this.apply(e.currentTarget.dataset.id, '', this.data.apiKey); },
  onKey(e) { this.setData({ apiKey: e.detail.value }); },
  onModel(e) { this.setData({ modelIndex: Number(e.detail.value) }); },

  copyKeyUrl() {
    if (!this.data.keyUrl) return;
    wx.setClipboardData({ data: this.data.keyUrl });
  },

  save() {
    const { provider, providerName, models, modelIndex, apiKey } = this.data;
    if (!provider) return;
    wx.setStorageSync('llm', {
      provider, name: providerName,
      model: models[modelIndex] || '',
      apiKey: (apiKey || '').trim()
    });
    wx.showToast({ title: '已保存', icon: 'success' });
    setTimeout(() => wx.navigateBack(), 600);
  },

  // 清空，改回服务端默认模型
  useDefault() {
    wx.removeStorageSync('llm');
    wx.showToast({ title: '已切回默认模型', icon: 'none' });
    setTimeout(() => wx.navigateBack(), 600);
  }
});
