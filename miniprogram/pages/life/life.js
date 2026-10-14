const app = getApp();
let API = app.globalData.apiBase;   // 在 onShow 里刷新，改地址后无需重启

// 校历/作息为静态数据，可按学校实际修改
const SCHEDULE = [
  { period: '第一大节', time: '08:00 - 09:40' },
  { period: '第二大节', time: '10:00 - 11:40' },
  { period: '午休', time: '11:40 - 14:00' },
  { period: '第三大节', time: '14:00 - 15:40' },
  { period: '第四大节', time: '16:00 - 17:40' },
  { period: '晚自习', time: '19:00 - 21:00' }
];
const CALENDAR = [
  { label: '开学', date: '2026-09-01' },
  { label: '国庆假期', date: '2026-10-01 ~ 10-07' },
  { label: '期中考试', date: '2026-11-09 ~ 11-13' },
  { label: '期末考试', date: '2027-01-05 ~ 01-16' },
  { label: '寒假', date: '2027-01-18 起' }
];

// 把 ISO 时间串(如 2026-10-13T11:26)转成"今天 11:26 / 昨天 / 3天前 / 10月13日"
function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(String(iso).replace('T', ' ').replace(/-/g, '/'));
  if (isNaN(d.getTime())) return String(iso);
  const pad = n => (n < 10 ? '0' + n : '' + n);
  const hm = pad(d.getHours()) + ':' + pad(d.getMinutes());
  const today = new Date();
  const d0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const diff = Math.round((d0 - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  if (diff <= 0) return '今天 ' + hm;
  if (diff === 1) return '昨天 ' + hm;
  if (diff < 7) return diff + '天前';
  return (d.getMonth() + 1) + '月' + d.getDate() + '日';
}

Page({
  data: {
    tab: 'home',               // home | lost | market
    weather: null, advice: '', wLoading: true,
    // 二手市场
    cats: ['全部', '教材书籍', '数码电子', '生活用品', '服饰鞋包', '运动户外', '其他'],
    cat: '全部',
    goods: [], goodsLoading: false,
    sellShow: false,           // 发布表单
    cur: null,                 // 当前查看的商品（详情弹层）
    gTitle: '', gPrice: '', gOrig: '', gCatIdx: 0, gDetail: '', gContact: '',
    gImages: [], uploading: false,
    // 失物招领
    lfKind: 'lost', lfList: [], lfLoading: false,
    showForm: false, fTitle: '', fLocation: '', fContact: '', fDetail: '',
    // 校历作息
    schedule: SCHEDULE, calendar: CALENDAR,
    // 官网同步
    school: { 校历: [], 作息: [], 通知公告: [] },
    schoolTime: {},
    syncCats: ['校历', '作息', '通知公告'],
    srcShow: false, srcCat: '校历', srcUrl: '', srcUrls: {}, syncing: false,
    // 同步完成后的学校 logo 过场动画
    logoAnim: { show: false, logo: '', name: '', light: false }
  },

  onLoad() {
    this.loadWeather();
    this.loadSchool();
  },

  // 从「我的」页跳过来时，按全局变量打开指定栏
  onShow() {
    API = app.globalData.apiBase;
    const want = app.globalData.lifeTab;
    if (want) {
      app.globalData.lifeTab = '';
      this.setData({ tab: want });
      if (want === 'lost') this.loadLost();
      if (want === 'market') this.loadMarket();
    }
  },

  onUnload() { if (this._logoTimer) clearTimeout(this._logoTimer); },

  noop() {},

  closeLogoAnim() {
    if (this._logoTimer) clearTimeout(this._logoTimer);
    this.setData({ 'logoAnim.show': false });
  },

  // logo 图片加载失败 → 退回"校"字方块，避免出现空白
  onLogoErr() { this.setData({ 'logoAnim.logo': '' }); },

  // ---------- 学校官网同步 ----------
  loadSchool() {
    wx.request({
      url: API + '/school/items', timeout: 15000,
      success: res => {
        const items = (res.data || {}).items || [];
        const school = { 校历: [], 作息: [], 通知公告: [] };
        items.forEach(it => {
          if (!school[it.category]) school[it.category] = [];
          school[it.category].push(it);
        });
        this.setData({ school });
      }
    });
    wx.request({
      url: API + '/school/sources', timeout: 15000,
      success: res => {
        const srcs = (res.data || {}).sources || [];
        const urls = {}, time = {};
        srcs.forEach(s => { urls[s.category] = s.url; if (s.synced_at) time[s.category] = s.synced_at; });
        this.setData({ srcUrls: urls, schoolTime: time });
      }
    });
  },

  openSync(e) {
    const cat = e.currentTarget.dataset.cat || '校历';
    this.setData({ srcShow: true, srcCat: cat, srcUrl: this.data.srcUrls[cat] || '' });
  },
  closeSync() { this.setData({ srcShow: false }); },
  pickSyncCat(e) {
    const cat = e.currentTarget.dataset.cat;
    this.setData({ srcCat: cat, srcUrl: this.data.srcUrls[cat] || '' });
  },
  onSrcUrl(e) { this.setData({ srcUrl: e.detail.value }); },

  doSync() {
    const { srcCat, srcUrl } = this.data;
    if (!srcUrl || !/^https?:\/\//i.test(srcUrl.trim())) {
      wx.showToast({ title: '请填写 http(s):// 开头的网址', icon: 'none' });
      return;
    }
    this.setData({ syncing: true });
    wx.showLoading({ title: '抓取并抽取中…', mask: true });
    wx.request({
      url: API + '/school/source', method: 'POST', timeout: 15000,
      data: { category: srcCat, url: srcUrl.trim() },
      success: () => {
        wx.request({
          url: API + '/school/sync', method: 'POST', timeout: 120000,
          data: { category: srcCat },
          success: r => {
            wx.hideLoading();
            this.setData({ syncing: false });
            const d = r.data || {};
            const done = (d.synced || [])[0];
            const bad = (d.failed || [])[0];
            if (bad) {
              wx.showModal({ title: '同步失败', content: bad.msg, showCancel: false });
            } else if (done) {
              // 关掉设置弹层，播学校 logo 过场动画
              this.setData({
                srcShow: false,
                logoAnim: {
                  show: true,
                  logo: done.logo ? API + done.logo : '',
                  name: done.name || '学校官网',
                  light: !!done.logo_light   // 白色 logo 要垫深色底，否则白底白图看不见
                }
              });
              this.loadSchool();
              if (this._logoTimer) clearTimeout(this._logoTimer);
              this._logoTimer = setTimeout(() => this.setData({ 'logoAnim.show': false }), 2300);
            }
          },
          fail: () => { wx.hideLoading(); this.setData({ syncing: false }); wx.showToast({ title: '同步失败，检查后端', icon: 'none' }); }
        });
      },
      fail: () => { wx.hideLoading(); this.setData({ syncing: false }); wx.showToast({ title: '保存失败，检查后端', icon: 'none' }); }
    });
  },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({ tab });
    if (tab === 'lost') this.loadLost();
    if (tab === 'market') this.loadMarket();
  },

  // ================= 二手市场 =================
  // 把后端返回的 /uploads/xxx 拼成完整地址
  _fixItem(it) {
    const imgs = (it.images || []).map(p => API + p);
    return { ...it, imgUrls: imgs, coverUrl: imgs[0] || '', timeText: fmtTime(it.created_at) };
  },

  noop() {},

  loadMarket() {
    this.setData({ goodsLoading: true });
    const cat = this.data.cat === '全部' ? '' : this.data.cat;
    wx.request({
      url: API + '/life/market?category=' + encodeURIComponent(cat), timeout: 15000,
      success: res => {
        const d = res.data || {};
        this.setData({ goods: (d.items || []).map(it => this._fixItem(it)) });
      },
      fail: () => wx.showToast({ title: '加载失败', icon: 'none' }),
      complete: () => this.setData({ goodsLoading: false })
    });
  },

  pickCat(e) {
    const cat = e.currentTarget.dataset.cat;
    this.setData({ cat }, this.loadMarket);
  },

  openItem(e) {
    const id = e.currentTarget.dataset.id;
    const cur = this.data.goods.find(g => g.id === id) || null;
    this.setData({ cur });
  },
  closeItem() { this.setData({ cur: null }); },

  callContact(e) {
    const c = (this.data.cur && this.data.cur.contact) || '';
    if (!c) { wx.showToast({ title: '卖家未留联系方式', icon: 'none' }); return; }
    wx.setClipboardData({ data: c, success: () => wx.showToast({ title: '联系方式已复制', icon: 'none' }) });
  },

  markSold() {
    const cur = this.data.cur;
    if (!cur) return;
    wx.showModal({
      title: '标记已售出', content: '确认这件宝贝已卖出？',
      success: r => {
        if (!r.confirm) return;
        wx.request({
          url: API + '/life/market/' + cur.id + '/sold', method: 'POST',
          success: () => { this.setData({ cur: null }, this.loadMarket); }
        });
      }
    });
  },

  // ---- 发布表单 ----
  toggleSell() { this.setData({ sellShow: !this.data.sellShow }); },
  onGTitle(e) { this.setData({ gTitle: e.detail.value }); },
  onGPrice(e) { this.setData({ gPrice: e.detail.value }); },
  onGOrig(e) { this.setData({ gOrig: e.detail.value }); },
  onGDetail(e) { this.setData({ gDetail: e.detail.value }); },
  onGContact(e) { this.setData({ gContact: e.detail.value }); },
  onGCat(e) { this.setData({ gCatIdx: Number(e.detail.value) }); },

  chooseImages() {
    const left = 3 - this.data.gImages.length;
    if (left <= 0) { wx.showToast({ title: '最多 3 张', icon: 'none' }); return; }
    wx.chooseMedia({
      count: left, mediaType: ['image'], sizeType: ['compressed'],
      success: r => {
        const add = r.tempFiles.map(f => f.tempFilePath);
        this.setData({ gImages: this.data.gImages.concat(add) });
      }
    });
  },
  removeImage(e) {
    const i = e.currentTarget.dataset.i;
    const gImages = this.data.gImages.slice();
    gImages.splice(i, 1);
    this.setData({ gImages });
  },

  // 上传一张图片，返回 Promise<url>
  _uploadOne(path) {
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: API + '/life/market/upload', filePath: path, name: 'file',
        success: r => {
          try { const d = JSON.parse(r.data); d.ok ? resolve(d.url) : reject(d.msg); }
          catch (e) { reject('上传失败'); }
        },
        fail: () => reject('上传失败')
      });
    });
  },

  submitItem() {
    const { gTitle, gPrice, gOrig, gImages } = this.data;
    if (!gTitle.trim()) { wx.showToast({ title: '请填宝贝标题', icon: 'none' }); return; }
    if (!gPrice) { wx.showToast({ title: '请填价格', icon: 'none' }); return; }
    this.setData({ uploading: true });
    wx.showLoading({ title: '发布中…' });

    Promise.all(gImages.map(p => this._uploadOne(p)))
      .then(urls => {
        wx.request({
          url: API + '/life/market', method: 'POST', timeout: 20000,
          data: {
            title: gTitle.trim(),
            price: Number(gPrice),
            orig_price: gOrig ? Number(gOrig) : null,
            category: this.data.cats[this.data.gCatIdx + 1] || '其他',
            detail: this.data.gDetail,
            images: urls,
            contact: this.data.gContact
          },
          success: r => {
            if ((r.data || {}).ok) {
              wx.hideLoading();
              // 记到本地「我发布的」
              app.addMine('market', { title: gTitle.trim(), price: Number(gPrice) });
              wx.showToast({ title: '发布成功' });
              this.setData({
                sellShow: false, uploading: false,
                gTitle: '', gPrice: '', gOrig: '', gDetail: '', gContact: '', gImages: [], gCatIdx: 0
              }, this.loadMarket);
            } else {
              wx.hideLoading();
              this.setData({ uploading: false });
              wx.showToast({ title: (r.data || {}).msg || '发布失败', icon: 'none' });
            }
          },
          fail: () => { wx.hideLoading(); this.setData({ uploading: false }); wx.showToast({ title: '发布失败', icon: 'none' }); }
        });
      })
      .catch(() => { wx.hideLoading(); this.setData({ uploading: false }); wx.showToast({ title: '图片上传失败', icon: 'none' }); });
  },

  // ---- 天气
  loadWeather() {
    this.setData({ wLoading: true });
    wx.request({
      url: API + '/life/weather', timeout: 15000,
      success: res => {
        const d = res.data || {};
        if (d.ok) this.setData({ weather: d.weather, advice: d.advice });
        else this.setData({ advice: '天气加载失败：' + (d.error || '') });
      },
      fail: () => this.setData({ advice: '连接后端失败，请确认后端已启动' }),
      complete: () => this.setData({ wLoading: false })
    });
  },

  // ---- 失物招领
  switchLfKind(e){ this.setData({ lfKind: e.currentTarget.dataset.k }, this.loadLost); },
  loadLost() {
    this.setData({ lfLoading: true });
    wx.request({
      url: API + '/life/lostfound?kind=' + this.data.lfKind, timeout: 15000,
      success: res => {
        const d = res.data || {};
        const list = (d.items || []).map(it => ({
          ...it,
          isLost: it.kind === 'lost',
          timeText: fmtTime(it.created_at)
        }));
        this.setData({ lfList: list });
      },
      fail: () => wx.showToast({ title:'加载失败', icon:'none' }),
      complete: () => this.setData({ lfLoading: false })
    });
  },
  toggleForm(){ this.setData({ showForm: !this.data.showForm }); },
  onFTitle(e){ this.setData({ fTitle: e.detail.value }); },
  onFLoc(e){ this.setData({ fLocation: e.detail.value }); },
  onFContact(e){ this.setData({ fContact: e.detail.value }); },
  onFDetail(e){ this.setData({ fDetail: e.detail.value }); },
  submitLf() {
    if (!this.data.fTitle) { wx.showToast({ title:'请填物品', icon:'none' }); return; }
    wx.request({
      url: API + '/life/lostfound', method: 'POST',
      data: { kind: this.data.lfKind, title: this.data.fTitle, location: this.data.fLocation, contact: this.data.fContact, detail: this.data.fDetail },
      success: res => {
        if ((res.data||{}).ok) {
          app.addMine('lost', { title: this.data.fTitle, kind: this.data.lfKind });
          wx.showToast({ title:'发布成功' });
          this.setData({ showForm:false, fTitle:'', fLocation:'', fContact:'', fDetail:'' }, this.loadLost);
        } else wx.showToast({ title:'发布失败', icon:'none' });
      },
      fail: () => wx.showToast({ title:'连接失败', icon:'none' })
    });
  },
  closeLf(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title:'确认', content:'标记为已解决并下架？',
      success: r => {
        if (!r.confirm) return;
        wx.request({
          url: API + '/life/lostfound/' + id + '/close', method: 'POST',
          success: () => this.loadLost()
        });
      }
    });
  }
});
