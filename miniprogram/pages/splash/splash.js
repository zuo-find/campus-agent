Page({
  data: { go: false, leaving: false },

  onLoad() {
    // 触发入场动画
    setTimeout(() => this.setData({ go: true }), 60);
    // 动画放完 → 淡出 → 进入主页
    this.t1 = setTimeout(() => this.setData({ leaving: true }), 2000);
    this.t2 = setTimeout(() => this.enter(), 2400);
  },

  onUnload() {
    clearTimeout(this.t1);
    clearTimeout(this.t2);
  },

  // 点击可跳过
  skip() {
    clearTimeout(this.t1);
    clearTimeout(this.t2);
    this.enter();
  },

  enter() {
    if (this._entered) return;
    this._entered = true;
    wx.reLaunch({ url: '/pages/chat/chat' });
  }
});
