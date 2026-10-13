const app = getApp();
const API = app.globalData.apiBase;

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

// ====== 快递/外卖 跳转配置（按需自行增删条目）======
// 每个条目两种跳转方式：
//   mode:'appid'   有对方小程序的 AppID，一键跳转（wx.navigateToMiniProgram）
//   mode:'qrcode'  没有 AppID，弹出小程序码大图，用户长按识别进入
// 例如要加"快递代取"，在这里加一条：
//   express_take: { mode: 'appid', appId: '对方的AppID', name: '快递代取' }
// 页面会自动为每条生成一个入口卡片，无需改 wxml。
const JUMP = {
  takeout: { mode: 'appid', appId: 'wxde8ac0a21135c07d', path: '', name: '外卖(美团)' }
};

Page({
  data: {
    tab: 'home',               // home | errand | lost
    weather: null, advice: '', wLoading: true,
    // 失物招领
    lfKind: 'lost', lfList: [], lfLoading: false,
    showForm: false, fTitle: '', fLocation: '', fContact: '', fDetail: '',
    // 校历作息
    schedule: SCHEDULE, calendar: CALENDAR,
    // 快递/外卖入口（由 JUMP 配置自动生成）
    jumps: Object.keys(JUMP).map((k, i) => {
      const c = JUMP[k];
      return {
        key: k,
        name: c.name,
        sub: c.mode === 'qrcode' ? '长按识别进入' : '点击进入小程序',
        initial: (c.name || '?').slice(0, 1),
        tone: i % 4
      };
    }),
    // 小程序码弹层
    qrShow: false, qrSrc: '', qrName: ''
  },

  onLoad() { this.loadWeather(); },

  // 跳转到快递/外卖小程序
  jumpTo(e) {
    const key = e.currentTarget.dataset.key;
    const cfg = JUMP[key];
    if (!cfg) return;

    // 备选方案：弹出小程序码大图，用户长按识别进入
    if (cfg.mode === 'qrcode') {
      this.setData({ qrShow: true, qrSrc: cfg.qr, qrName: cfg.name });
      return;
    }

    // 一键跳转
    if (!cfg.appId) {
      wx.showModal({ title: cfg.name, showCancel: false, content: '尚未配置 AppID。' });
      return;
    }
    wx.navigateToMiniProgram({
      appId: cfg.appId,
      path: cfg.path || '',
      fail: (err) => {
        wx.showToast({ title: '跳转失败，检查 AppID 与关联', icon: 'none' });
        console.error('navigateToMiniProgram fail:', err);
      }
    });
  },

  closeQr() { this.setData({ qrShow: false }); },
  // 点大图可全屏预览（也可长按识别）
  previewQr() { if (this.data.qrSrc) wx.previewImage({ urls: [this.data.qrSrc] }); },

  switchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({ tab });
    if (tab === 'lost') this.loadLost();
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
