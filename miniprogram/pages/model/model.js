const app = getApp();
let API = app.globalData.apiBase;   // 在 onShow 里刷新，改地址后无需重启

Page({
  data: {
    tab: 'chat',            // chat 对话模型 | vision 识图模型
    guideOpen: true,        // 使用说明：第一次进来展开，看过了就收起
    keysOpen: false,        // 各家 Key 申请地址（折叠，需要时展开）
    // ---- 对话模型 ----
    providers: [], map: {},
    provider: '', providerName: '', models: [],
    modelIndex: 0, apiKey: '', keyUrl: '', note: '',
    // ---- 识图模型（拍照识别用）----
    vProviders: [], vMap: {},
    vProvider: '', vProviderName: '', vModels: [],
    vModelIndex: 0, vKey: '', vKeyUrl: '', vNote: '',
    // 拉取厂商实时模型列表 / 手动填模型名
    fetching: false, fetchMsg: '', fetchOk: false,
    customModel: '', vCustomModel: ''
  },

  onLoad() {
    API = app.globalData.apiBase;
    // 说明默认展开；看过一次就记下来，以后进来自动收起，不挡着设置
    this.setData({ guideOpen: !wx.getStorageSync('modelGuideSeen') });

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
          // 存过的模型名不在内置列表里（比如上次拉的最新款），放进手填框，别让它悄悄丢了
          if (saved.model && (map[saved.provider].models || []).indexOf(saved.model) < 0) {
            this.setData({ customModel: saved.model });
          }
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
          if (savedV.model && (map[savedV.provider].models || []).indexOf(savedV.model) < 0) {
            this.setData({ vCustomModel: savedV.model });
          }
        } else if (list.length) {
          this.bindGroup(list, map, list[0].id, '', '', 'v');
        }
      }
    });
  },

  switchTab(e) { this.setData({ tab: e.currentTarget.dataset.tab }); },

  toggleGuide() {
    const guideOpen = !this.data.guideOpen;
    this.setData({ guideOpen });
    if (!guideOpen) wx.setStorageSync('modelGuideSeen', 1);   // 收起过就算看过了
  },

  toggleKeys() { this.setData({ keysOpen: !this.data.keysOpen }); },

  // 地址清单里点一行就复制那家的网址
  copyKeyRow(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: (e.currentTarget.dataset.name || '') + ' 地址已复制', icon: 'none' })
    });
  },

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
  onModel(e) { this.setData({ modelIndex: Number(e.detail.value), customModel: '' }); },
  onVModel(e) { this.setData({ vModelIndex: Number(e.detail.value), vCustomModel: '' }); },
  onCustomModel(e) { this.setData({ customModel: e.detail.value }); },
  onVCustomModel(e) { this.setData({ vCustomModel: e.detail.value }); },

  // 用你自己的 Key 去厂商拉一份当前真正可用的型号（内置列表更新不及厂商快）
  fetchModels(e) {
    const isV = e.currentTarget.dataset.v === 'v';
    const provider = isV ? this.data.vProvider : this.data.provider;
    const apiKey = (isV ? this.data.vKey : this.data.apiKey) || '';
    if (!provider) return;
    if (!apiKey.trim()) {
      this.setData({
        fetchMsg: '拉取要用你的 Key（填在下面的「API Key」栏）。'
                  + '不想填也没关系，直接从上面的列表里选一个就行。',
        fetchOk: false
      });
      return;
    }
    this.setData({ fetching: true, fetchMsg: '', fetchOk: false });
    wx.request({
      url: API + '/providers/models', method: 'POST', timeout: 25000,
      data: { provider, api_key: apiKey.trim() },
      success: r => {
        const d = r.data || {};
        this.setData({ fetching: false });
        if (!d.ok) {
          // 后端还是旧版时这个接口根本不存在，会返回 404，
          // 而 404 的响应体里没有 error 字段——别退化成一句没用的"拉取失败"
          let msg = d.error;
          if (!msg) {
            msg = r.statusCode === 404
              ? '后端还没更新，没有这个接口——把后端的黑窗口关掉重新双击「启动后端.bat」'
              : '拉取失败（HTTP ' + r.statusCode + '）';
          }
          this.setData({ fetchMsg: msg, fetchOk: false });
          return;
        }
        // 把当前选中的型号尽量保留住
        const cur = isV ? this.data.vCustomModel || this.data.vModels[this.data.vModelIndex]
                        : this.data.customModel || this.data.models[this.data.modelIndex];
        const idx = Math.max(0, (d.models || []).indexOf(cur));
        this.setData(isV
          ? { vModels: d.models, vModelIndex: idx, vCustomModel: '', fetchOk: true,
              fetchMsg: '拉到 ' + d.count + ' 个型号，在列表里挑' }
          : { models: d.models, modelIndex: idx, customModel: '', fetchOk: true,
              fetchMsg: '拉到 ' + d.count + ' 个型号，在列表里挑' });
      },
      fail: () => this.setData({
        fetching: false, fetchOk: false,
        fetchMsg: '连不上后端，确认后端在运行'
      })
    });
  },

  copyKeyUrl() { if (this.data.keyUrl) wx.setClipboardData({ data: this.data.keyUrl }); },
  copyVKeyUrl() { if (this.data.vKeyUrl) wx.setClipboardData({ data: this.data.vKeyUrl }); },

  save() {
    const isV = this.data.tab === 'vision';
    const d = this.data;
    const provider = isV ? d.vProvider : d.provider;
    const model = isV
      ? (d.vCustomModel || '').trim() || d.vModels[d.vModelIndex] || ''
      : (d.customModel || '').trim() || d.models[d.modelIndex] || '';
    const apiKey = ((isV ? d.vKey : d.apiKey) || '').trim();
    if (!provider) return;
    if (!model) { wx.showToast({ title: '请选择或填写模型名', icon: 'none' }); return; }

    // 只选了型号没填 Key 的话，实际仍会用内置默认模型——说清楚再保存，
    // 免得用户以为自己选的型号生效了
    if (!apiKey) {
      wx.showModal({
        title: '还没填 API Key',
        content: '没有 Key 就用不了这家的服务，实际仍会走小程序内置的默认模型，'
               + '你选的「' + model + '」不会生效。',
        confirmText: '仍然保存', cancelText: '回去填 Key',
        success: r => { if (r.confirm) this.doSave(isV, provider, model, apiKey); }
      });
      return;
    }
    this.doSave(isV, provider, model, apiKey);
  },

  doSave(isV, provider, model, apiKey) {
    const name = isV ? this.data.vProviderName : this.data.providerName;
    wx.setStorageSync(isV ? 'visionLlm' : 'llm', { provider, name, model, apiKey });
    wx.showToast({ title: isV ? '识图模型已保存' : '已保存', icon: 'success' });
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
