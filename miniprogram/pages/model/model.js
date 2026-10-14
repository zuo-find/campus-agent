const app = getApp();
let API = app.globalData.apiBase;   // 在 onShow 里刷新，改地址后无需重启

Page({
  data: {
    tab: 'chat',            // chat 对话模型 | vision 识图模型
    // ---- 对话模型 ----
    providers: [], map: {},
    provider: '', providerName: '', models: [],
    modelIndex: 0, apiKey: '', keyUrl: '', note: '',
    // ---- 识图模型（拍照识别用）----
    vProviders: [], vMap: {},
    vProvider: '', vProviderName: '', vModels: [],
    vModelIndex: 0, vKey: '', vKeyUrl: '', vNote: ''
  },

  onLoad() {
    API = app.globalData.apiBase;
    const saved = wx.getStorageSync('llm') || null;
    const savedV = wx.getStorageSync('visionLlm') || null;

    wx.request({
      url: API + '/providers', timeout: 15000,
      success: (r) => {
        const list = (r.data || {}).providers || [];
        const map = {};
        list.forEach(p => { map[p.id] = p; });
        this.setData({ providers: list, map });
        if (saved && map[saved.provider]) {
          this.bindGroup(list, map, saved.provider, saved.model, saved.apiKey, '');
        } else if (list.length) {
          this.bindGroup(list, map, list[0].id, '', '', '');
        }
      },
      fail: () => wx.showToast({ title: '加载厂商列表失败，检查后端', icon: 'none' })
    });

    wx.request({
      url: API + '/providers/vision', timeout: 15000,
      success: (r) => {
        const list = (r.data || {}).providers || [];
        const map = {};
        list.forEach(p => { map[p.id] = p; });
        this.setData({ vProviders: list, vMap: map });
        if (savedV && map[savedV.provider]) {
          this.bindGroup(list, map, savedV.provider, savedV.model, savedV.apiKey, 'v');
        } else if (list.length) {
          this.bindGroup(list, map, list[0].id, '', '', 'v');
        }
      }
    });
  },

  switchTab(e) { this.setData({ tab: e.currentTarget.dataset.tab }); },

  // 把某个厂商的配置填进对应那一组（tag='v' 为识图组）
  bindGroup(list, map, pid, model, apiKey, tag) {
    const p = map[pid];
    if (!p) return;
    const idx = Math.max(0, (p.models || []).indexOf(model));
    if (tag === 'v') {
      this.setData({
        vProvider: pid, vProviderName: p.name, vModels: p.models || [],
        vModelIndex: idx, vKey: apiKey || '',
        vKeyUrl: p.key_url || '', vNote: p.note || ''
      });
    } else {
      this.setData({
        provider: pid, providerName: p.name, models: p.models || [],
        modelIndex: idx, apiKey: apiKey || '',
        keyUrl: p.key_url || '', note: p.note || ''
      });
    }
  },

  chooseProvider(e) { this.bindGroup(this.data.providers, this.data.map, e.currentTarget.dataset.id, '', this.data.apiKey, ''); },
  chooseVProvider(e) { this.bindGroup(this.data.vProviders, this.data.vMap, e.currentTarget.dataset.id, '', this.data.vKey, 'v'); },

  onKey(e) { this.setData({ apiKey: e.detail.value }); },
  onVKey(e) { this.setData({ vKey: e.detail.value }); },
  onModel(e) { this.setData({ modelIndex: Number(e.detail.value) }); },
  onVModel(e) { this.setData({ vModelIndex: Number(e.detail.value) }); },

  copyKeyUrl() { if (this.data.keyUrl) wx.setClipboardData({ data: this.data.keyUrl }); },
  copyVKeyUrl() { if (this.data.vKeyUrl) wx.setClipboardData({ data: this.data.vKeyUrl }); },

  save() {
    if (this.data.tab === 'vision') {
      const { vProvider, vProviderName, vModels, vModelIndex, vKey } = this.data;
      if (!vProvider) return;
      wx.setStorageSync('visionLlm', {
        provider: vProvider, name: vProviderName,
        model: vModels[vModelIndex] || '', apiKey: (vKey || '').trim()
      });
      wx.showToast({ title: '识图模型已保存', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 700);
      return;
    }
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

  // chat 组：改回服务端默认模型；vision 组：清掉自填的识图配置
  useDefault() {
    if (this.data.tab === 'vision') {
      wx.removeStorageSync('visionLlm');
      wx.showToast({ title: '已清除识图配置', icon: 'none' });
      return;
    }
    wx.removeStorageSync('llm');
    wx.showToast({ title: '已切回默认模型', icon: 'none' });
    setTimeout(() => wx.navigateBack(), 600);
  }
});
