Page({
  data: {
    courses: [],
    name: '', credit: '', score: '',
    gpa: null, avg: null
  },

  onShow() {
    const courses = wx.getStorageSync('courses') || [];
    this.setData({ courses }, this.recalc);
  },

  onName(e) { this.setData({ name: e.detail.value }); },
  onCredit(e) { this.setData({ credit: e.detail.value }); },
  onScore(e) { this.setData({ score: e.detail.value }); },

  add() {
    const { name, credit, score } = this.data;
    if (!name || !credit || score === '') {
      wx.showToast({ title: '请填完整', icon: 'none' });
      return;
    }
    const courses = this.data.courses.concat([{
      name, credit: Number(credit), score: Number(score)
    }]);
    wx.setStorageSync('courses', courses);
    this.setData({ courses, name: '', credit: '', score: '' }, this.recalc);
  },

  remove(e) {
    const i = e.currentTarget.dataset.i;
    const courses = this.data.courses.slice();
    courses.splice(i, 1);
    wx.setStorageSync('courses', courses);
    this.setData({ courses }, this.recalc);
  },

  // 本地也算一份 GPA，和后端工具逻辑保持一致，便于离线查看
  recalc() {
    const cs = this.data.courses.filter(c => c.score != null && c.credit);
    if (!cs.length) { this.setData({ gpa: null, avg: null }); return; }
    const g = s => s>=90?4.0:s>=85?3.7:s>=82?3.3:s>=78?3.0:s>=75?2.7:s>=72?2.3:s>=68?2.0:s>=64?1.5:s>=60?1.0:0.0;
    const tc = cs.reduce((a,c)=>a+Number(c.credit),0);
    const gpa = cs.reduce((a,c)=>a+g(c.score)*Number(c.credit),0)/tc;
    const avg = cs.reduce((a,c)=>a+Number(c.score)*Number(c.credit),0)/tc;
    this.setData({ gpa: gpa.toFixed(3), avg: avg.toFixed(2) });
  }
});
