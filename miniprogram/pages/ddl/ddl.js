Page({
  data: {
    ddls: [],
    title: '', due: ''
  },

  onShow() {
    this.refresh();
  },

  refresh() {
    const raw = wx.getStorageSync('ddls') || [];
    const today = new Date(); today.setHours(0,0,0,0);
    const ddls = raw.map(d => {
      const due = new Date(d.due);
      const daysLeft = Math.round((due - today) / 86400000);
      return { ...d, daysLeft };
    }).sort((a,b) => a.daysLeft - b.daysLeft);
    this.setData({ ddls });
  },

  onTitle(e) { this.setData({ title: e.detail.value }); },
  onDate(e) { this.setData({ due: e.detail.value }); },

  add() {
    const { title, due } = this.data;
    if (!title || !due) { wx.showToast({ title: '请填完整', icon: 'none' }); return; }
    const raw = wx.getStorageSync('ddls') || [];
    raw.push({ title, due });
    wx.setStorageSync('ddls', raw);
    this.setData({ title: '', due: '' }, this.refresh);
  },

  remove(e) {
    const i = e.currentTarget.dataset.i;
    const raw = wx.getStorageSync('ddls') || [];
    // data 已排序，用 title+due 定位原数组
    const t = this.data.ddls[i];
    const idx = raw.findIndex(d => d.title === t.title && d.due === t.due);
    if (idx > -1) raw.splice(idx, 1);
    wx.setStorageSync('ddls', raw);
    this.refresh();
  }
});
