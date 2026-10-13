const app = getApp();

// 百分制 → 绩点（与后端 tools/_score_to_gpa 保持一致）
function scoreToGpa(s) {
  if (s >= 90) return 4.0;
  if (s >= 85) return 3.7;
  if (s >= 82) return 3.3;
  if (s >= 78) return 3.0;
  if (s >= 75) return 2.7;
  if (s >= 72) return 2.3;
  if (s >= 68) return 2.0;
  if (s >= 64) return 1.5;
  if (s >= 60) return 1.0;
  return 0.0;
}

// 绩点 → 大致需要的分数（用于提分测算的口语化提示）
const GPA_SCORE = [[4.0, 90], [3.7, 85], [3.3, 82], [3.0, 78], [2.7, 75],
                   [2.3, 72], [2.0, 68], [1.5, 64], [1.0, 60]];

function gpaToScore(g) {
  for (const [gp, sc] of GPA_SCORE) if (g >= gp) return sc;
  return 0;
}

// 分数 → 等级
function levelOf(s) {
  if (s >= 90) return { text: '优秀', tone: 'a' };
  if (s >= 80) return { text: '良好', tone: 'b' };
  if (s >= 70) return { text: '中等', tone: 'c' };
  if (s >= 60) return { text: '及格', tone: 'd' };
  return { text: '不及格', tone: 'e' };
}

const LEVELS = [['优秀', 90], ['良好', 80], ['中等', 70], ['及格', 60], ['不及格', 0]];

Page({
  data: {
    courses: [],       // 原始数据
    list: [],          // 展示用（带等级）
    name: '', credit: '', score: '',
    gpa: null, avg: null, totalCredit: 0, count: 0,
    gpaPct: 0,         // 绩点进度（0~100）
    gpaLevel: '',      // 绩点等级评定
    failed: [],        // 挂科课程
    dist: [],          // 等级分布
    maxDist: 1,
    // 提分测算
    targetGpa: '3.5', nextCredits: '20', planText: '', planWarn: false
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
    wx.showModal({
      title: '删除课程', content: '确定删除这条成绩？',
      success: r => {
        if (!r.confirm) return;
        const courses = this.data.courses.slice();
        courses.splice(i, 1);
        wx.setStorageSync('courses', courses);
        this.setData({ courses }, this.recalc);
      }
    });
  },

  recalc() {
    const raw = this.data.courses;
    const valid = raw.filter(c => c.score != null && c.credit);

    // 展示列表：带等级、按分数从高到低
    const list = raw.map((c, i) => ({
      ...c, idx: i, level: levelOf(c.score).text, tone: levelOf(c.score).tone
    })).sort((a, b) => b.score - a.score);

    if (!valid.length) {
      this.setData({
        list, gpa: null, avg: null, totalCredit: 0, count: 0, gpaPct: 0,
        gpaLevel: '', failed: [], dist: [], planText: ''
      });
      return;
    }

    const tc = valid.reduce((a, c) => a + Number(c.credit), 0);
    const gpa = valid.reduce((a, c) => a + scoreToGpa(c.score) * Number(c.credit), 0) / tc;
    const avg = valid.reduce((a, c) => a + Number(c.score) * Number(c.credit), 0) / tc;

    const gpaLevel = gpa >= 3.7 ? '优秀' : gpa >= 3.0 ? '良好' : gpa >= 2.0 ? '中等' : gpa >= 1.0 ? '及格' : '待提升';
    const failed = valid.filter(c => c.score < 60).map(c => c.name);

    // 等级分布
    let dist = LEVELS.map(([text]) => ({ text, n: 0 }));
    valid.forEach(c => {
      const t = levelOf(c.score).text;
      const found = dist.find(d => d.text === t);
      if (found) found.n += 1;
    });
    const maxDist = Math.max(1, ...dist.map(d => d.n));
    dist = dist.map(d => ({ ...d, pct: Math.round(d.n / maxDist * 100) }));

    this.setData({
      list, gpa: gpa.toFixed(2), avg: avg.toFixed(1), totalCredit: tc,
      count: valid.length, gpaPct: Math.min(100, Math.round(gpa / 4 * 100)),
      gpaLevel, failed, dist, maxDist
    }, this.calcPlan);
  },

  // 提分测算：按目标绩点反推下学期需要拿到多少分
  onTarget(e) { this.setData({ targetGpa: e.detail.value }, this.calcPlan); },
  onNextCredit(e) { this.setData({ nextCredits: e.detail.value }, this.calcPlan); },

  calcPlan() {
    const cur = Number(this.data.gpa);
    const cc = Number(this.data.totalCredit);
    const goal = Number(this.data.targetGpa);
    const nc = Number(this.data.nextCredits);
    if (!cur || !cc || !goal || !nc) { this.setData({ planText: '' }); return; }

    if (cur >= goal) {
      this.setData({ planText: `当前绩点 ${cur} 已达目标，保持住就好。`, planWarn: false });
      return;
    }
    const need = (goal * (cc + nc) - cur * cc) / nc;
    if (need > 4.0) {
      this.setData({
        planText: `差距较大：这 ${nc} 学分即使全部拿满绩点(4.0)也达不到 ${goal}，需要更多学分或更长的学期铺垫。`,
        planWarn: true
      });
      return;
    }
    this.setData({
      planText: `下学期这 ${nc} 学分，平均绩点需 ≥ ${need.toFixed(2)}，约合均分 ${gpaToScore(need)} 分以上。`,
      planWarn: false
    });
  },

  // 把成绩交给问答 Agent 分析
  askAI() {
    if (!this.data.count) {
      wx.showToast({ title: '先录入几门成绩', icon: 'none' });
      return;
    }
    app.globalData.pendingAsk = '帮我分析一下我的成绩：目前平均绩点 ' + this.data.gpa +
      '，加权均分 ' + this.data.avg + '，共 ' + this.data.count + ' 门课。' +
      (this.data.failed.length ? '其中有挂科：' + this.data.failed.join('、') + '。' : '') +
      '给我一些提升建议。';
    wx.switchTab({ url: '/pages/chat/chat' });
  }
});
