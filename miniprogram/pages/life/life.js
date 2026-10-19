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

// 课表用的节次与星期（时间取自上面的 SCHEDULE，午休不算一节课）
const DAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const PERIODS = ['第一大节', '第二大节', '第三大节', '第四大节', '晚自习'];
const PERIOD_TIME = {};
SCHEDULE.forEach(s => { if (PERIODS.indexOf(s.period) >= 0) PERIOD_TIME[s.period] = s.time; });

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
    logoAnim: { show: false, logo: '', name: '', light: false },
    // 「选择学校」：输入校名自动填官网
    uniQ: '', uniList: [],
    // 我的课表
    ttList: [], ttGroups: [],
    ttShow: false, ttSheet: false, ttCands: [], ttPickCount: 0, ttBusy: false,
    mfShow: false, mf: { name: '', place: '', weeks: '' },
    mfDay: '周一', mfPeriod: '第一大节', mfDup: '', mfPlaces: [],
    dayOptions: DAY_NAMES, periodOptions: PERIODS, periodTime: PERIOD_TIME
  },

  onLoad() {
    this.loadWeather();
    this.loadSchool();
    this.loadTimetable();
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

  onUnload() {
    if (this._logoTimer) clearTimeout(this._logoTimer);
    if (this._uniTimer) clearTimeout(this._uniTimer);
  },

  noop() {},

  // 输入校名 → 查名单 → 点一条自动填网址
  onUniInput(e) {
    const q = (e.detail.value || '').trim();
    this.setData({ uniQ: q });
    if (this._uniTimer) clearTimeout(this._uniTimer);
    if (!q) { this.setData({ uniList: [] }); return; }
    // 边打字边查会打太多请求，停 300ms 再查
    this._uniTimer = setTimeout(() => {
      wx.request({
        url: API + '/school/search', timeout: 15000,
        data: { q: q, limit: 8 },
        success: r => {
          // 只列有官网的——没官网的点了也填不了，白占位置
          const items = ((r.data || {}).items || []).filter(x => x.u);
          if (this.data.uniQ === q) this.setData({ uniList: items });
        }
      });
    }, 300);
  },

  pickUni(e) {
    const { url, n } = e.currentTarget.dataset;
    if (!url) return;
    this.setData({ srcUrl: url, uniQ: n, uniList: [] });
    wx.showToast({ title: '已填入 ' + n + ' 官网', icon: 'none' });
  },

  closeLogoAnim() {
    if (this._logoTimer) clearTimeout(this._logoTimer);
    this.setData({ 'logoAnim.show': false });
  },

  // logo 图片加载失败 → 退回"校"字方块，避免出现空白
  onLogoErr() { this.setData({ 'logoAnim.logo': '' }); },

  // ==================== 我的课表 ====================
  // 只存本地（课程属于个人数据，不上传服务器）

  loadTimetable() {
    const list = wx.getStorageSync('timetable') || [];
    this.setData({ ttList: list, ttGroups: this.groupTt(list) });
  },

  // 按星期分组，标出今天；没课的星期不显示
  groupTt(list) {
    const todayIdx = (new Date().getDay() + 6) % 7;    // 周日=0 → 我们排第 7
    const groups = [];
    DAY_NAMES.forEach((day, i) => {
      const items = list.filter(c => c.day === day)
        .sort((a, b) => PERIODS.indexOf(a.period) - PERIODS.indexOf(b.period));
      if (items.length) {
        groups.push({ day, isToday: i === todayIdx, items });
      }
    });
    return groups;
  },

  openTt() { this.setData({ ttShow: true }); },
  closeTt() { this.setData({ ttShow: false }); },

  // ---- 拍照识别导入 ----
  ttCamera() {
    this.setData({ ttShow: false });
    if (this.data.ttBusy) return;
    wx.chooseMedia({
      count: 1, mediaType: ['image'], sizeType: ['compressed'],
      sourceType: ['camera', 'album'],
      success: res => {
        const f = (res.tempFiles || [])[0];
        if (!f) return;
        this.ttSend(f.tempFilePath);
      },
      fail: () => {}
    });
  },

  ttSend(path) {
    const vl = wx.getStorageSync('visionLlm');
    const visionPayload = vl && vl.apiKey
      ? { provider: vl.provider, api_key: vl.apiKey, model: vl.model } : null;
    if (!visionPayload) {
      wx.showModal({
        title: '还没配识图模型',
        content: '拍课表识别要用多模态模型。去「我的 → 大模型设置 → 识图模型」配一个（推荐智谱 glm-4v-flash，有免费额度）。',
        showCancel: false
      });
      return;
    }
    this.setData({ ttBusy: true });
    wx.showLoading({ title: '识别课表中…', mask: true });
    wx.compressImage({
      src: path, quality: 70,
      success: r => this.ttUpload(r.tempFilePath || path, visionPayload),
      fail: () => this.ttUpload(path, visionPayload)
    });
  },

  ttUpload(file, visionPayload) {
    wx.getFileSystemManager().readFile({
      filePath: file, encoding: 'base64',
      success: res => {
        const ext = (file.split('.').pop() || 'jpg').toLowerCase();
        const mime = ext === 'png' ? 'image/png' : (ext === 'webp' ? 'image/webp' : 'image/jpeg');
        wx.request({
          url: API + '/chat/vision', method: 'POST', timeout: 120000,
          data: {
            image: 'data:' + mime + ';base64,' + res.data,
            mode: 'timetable', message: '', history: [],
            vision_llm: visionPayload
          },
          success: r => {
            const d = r.data || {};
            if (!d.ok) { wx.showToast({ title: d.error || '识别失败', icon: 'none' }); return; }
            const list = (d.courses || []).map(c => ({ ...c, on: true, tid: 'c' + Math.random() }));
            if (!list.length) {
              wx.showModal({
                title: '没识别出课程', showCancel: false,
                content: d.reply || '换一张更清晰的课表截图试试。'
              });
              return;
            }
            this.setData({ ttCands: list, ttPickCount: list.length, ttSheet: true });
          },
          fail: () => wx.showToast({ title: '识别失败，检查后端', icon: 'none' }),
          complete: () => { wx.hideLoading(); this.setData({ ttBusy: false }); }
        });
      },
      fail: () => { wx.hideLoading(); this.setData({ ttBusy: false }); wx.showToast({ title: '读取图片失败', icon: 'none' }); }
    });
  },

  toggleTtCand(e) {
    const i = e.currentTarget.dataset.i;
    const cands = this.data.ttCands.slice();
    cands[i].on = !cands[i].on;
    this.setData({ ttCands: cands, ttPickCount: cands.filter(c => c.on).length });
  },
  closeTtSheet() { this.setData({ ttSheet: false }); },

  saveTtCands() {
    const pick = this.data.ttCands.filter(c => c.on);
    if (!pick.length) { wx.showToast({ title: '至少选一门', icon: 'none' }); return; }
    const added = this.addCourses(pick.map(c => ({
      name: c.name, day: c.day, period: c.period, place: c.place
    })));
    this.setData({ ttSheet: false });
    wx.showToast({
      title: added ? '已导入 ' + added + ' 条' : '这些课程已经有了', icon: 'none'
    });
  },

  // 写进本地。去重规则：同一天 + 同一节 + 同一门课视为重复。返回实际新增条数
  addCourses(items) {
    const list = this.data.ttList.slice();
    let added = 0;
    items.forEach(c => {
      if (list.some(x => x.day === c.day && x.period === c.period && x.name === c.name)) return;
      list.push({
        id: 't' + Date.now() + Math.floor(Math.random() * 10000),
        name: c.name, day: c.day, period: c.period,
        place: c.place || '', weeks: c.weeks || '',
        time: PERIOD_TIME[c.period] || ''
      });
      added += 1;
      this.rememberPlace(c.place);
    });
    if (added) {
      wx.setStorageSync('timetable', list);
      this.setData({ ttList: list, ttGroups: this.groupTt(list) });
    }
    return added;
  },

  // 记住最近用过的上课地点，下次手动添加时可以一点就填
  rememberPlace(p) {
    p = (p || '').trim();
    if (!p) return;
    const arr = (wx.getStorageSync('tt_places') || []).filter(x => x !== p);
    arr.unshift(p);
    const top = arr.slice(0, 6);
    wx.setStorageSync('tt_places', top);
    this.setData({ mfPlaces: top });
  },

  delCourse(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '删除课程', content: '确定从课表里删掉这门课？',
      success: r => {
        if (!r.confirm) return;
        const list = this.data.ttList.filter(x => x.id !== id);
        wx.setStorageSync('timetable', list);
        this.setData({ ttList: list, ttGroups: this.groupTt(list) });
      }
    });
  },

  // ---- 手动添加 ----
  // 星期和节次做成直接点的胶囊（不走 picker），节次下面直接标出时间，
  // 不用自己记"第三大节是几点"；地点记住最近用过的几个，点一下就能填。
  ttManual() {
    this.setData({
      ttShow: false, mfShow: true,
      mf: { name: '', place: '', weeks: '' },
      mfDay: this.data.mfDay || '周一',
      mfPeriod: this.data.mfPeriod || '第一大节',
      mfDup: '',
      mfPlaces: wx.getStorageSync('tt_places') || []
    });
  },
  closeMf() { this.setData({ mfShow: false }); },

  pickMfDay(e) { this.setData({ mfDay: e.currentTarget.dataset.d, mfDup: '' }); },
  pickMfPeriod(e) { this.setData({ mfPeriod: e.currentTarget.dataset.p, mfDup: '' }); },
  pickMfPlace(e) { this.setData({ 'mf.place': e.currentTarget.dataset.p, mfDup: '' }); },
  onMfInput(e) {
    this.setData({ ['mf.' + e.currentTarget.dataset.k]: e.detail.value, mfDup: '' });
  },

  // more=1 表示「添加并继续」：只清课程名，星期/节次/地点留着，方便连着加同一天的多门课
  saveManual(e) {
    const more = e.currentTarget.dataset.more === '1';
    const name = (this.data.mf.name || '').trim();
    if (!name) { wx.showToast({ title: '先填课程名', icon: 'none' }); return; }

    const course = {
      name,
      day: this.data.mfDay,
      period: this.data.mfPeriod,
      place: (this.data.mf.place || '').trim(),
      weeks: (this.data.mf.weeks || '').trim()
    };
    const dup = this.data.ttList.some(x =>
      x.day === course.day && x.period === course.period && x.name === course.name);
    if (dup) {
      this.setData({ mfDup: course.day + ' ' + course.period + ' 已经有「' + name + '」了' });
      return;
    }

    this.addCourses([course]);

    if (more) {
      this.setData({ mf: { name: '', place: this.data.mf.place, weeks: this.data.mf.weeks }, mfDup: '' });
      wx.showToast({ title: '已添加，继续加下一门', icon: 'none' });
    } else {
      this.setData({ mfShow: false });
      wx.showToast({ title: '已添加', icon: 'none' });
    }
  },

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
    this.setData({ srcShow: true, srcCat: cat, srcUrl: this.data.srcUrls[cat] || '',
                   uniQ: '', uniList: [] });
  },
  closeSync() { this.setData({ srcShow: false, uniList: [] }); },
  pickSyncCat(e) {
    const cat = e.currentTarget.dataset.cat;
    this.setData({ srcCat: cat, srcUrl: this.data.srcUrls[cat] || '', uniQ: '', uniList: [] });
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
