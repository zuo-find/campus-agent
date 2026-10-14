const app = getApp();
const API = app.globalData.apiBase;

// 判定哪些字段应该用多行输入（长文本）
const MULTI_KEYS = ['理由', '流程', '目的', '宗旨', '成员', '计划', '预算', '预案', '说明', '描述', '内容'];

// 按时间打招呼
function greeting() {
  const h = new Date().getHours();
  if (h < 6) return '夜深了';
  if (h < 11) return '早上好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

// 回答完给几条"接着问"，省得用户想下一句问什么
const FOLLOWUPS = {
  qa: ['需要准备哪些材料？', '在哪个部门办理？', '大概多久能办完？'],
  doc: ['帮我把时间改成下周', '这份材料还需要盖章吗？', '再写一份活动策划'],
  schedule: ['这些时间点里哪个最着急？', '报名需要什么条件？', '帮我把这些整理成一句话'],
  study: ['再出几道难一点的', '讲讲刚才那道题的思路', '我该先补哪块知识？'],
  '': ['能说得再具体一点吗？', '学校有相关的文件吗？', '那我要去哪里办？']
};

// 等待回答时展示的处理流程（与后端 route → retrieve → 生成 的实际流程对应）
const THINK_STEPS = ['正在判断该由哪个智能体来答', '正在检索校园知识库', '正在组织回答'];
const THINK_VISION = ['正在读取图片', '正在识别图片里的文字', '正在交给智能体处理'];

const HOT_ASKS = ['帮我算一下绩点', '挂科了怎么重修', '奖学金怎么评'];

Page({
  data: {
    messages: [],        // {role:'user'|'assistant', content, sources?}
    input: '',
    loading: false,
    scrollTop: 0,
    modelLabel: '默认模型',
    docEdit: { show: false, idx: -1, docType: '', title: '', fields: [] },
    // 输入框上方的能力入口，对应后端四个智能体
    caps: [
      { key: 'qa', label: '问制度', tone: 'qa' },
      { key: 'doc', label: '写材料', tone: 'doc' },
      { key: 'schedule', label: '查日程', tone: 'schedule' },
      { key: 'study', label: '刷题', tone: 'study' }
    ],
    docPick: false,
    docTypes: ['请假条', '实训申请', '活动策划', '社团申报'],
    quickAsks: HOT_ASKS,
    quickLabel: '大家都在问',
    // 空态欢迎区
    greeting: '你好',
    welcomeCards: [
      { key: 'qa', tone: 'qa', label: '问制度', desc: '挂科了怎么重修', preset: '挂科了怎么重修？' },
      { key: 'doc', tone: 'doc', label: '写材料', desc: '请假条 · 活动策划', preset: '' },
      { key: 'schedule', tone: 'schedule', label: '查日程', desc: '比赛什么时候截止', preset: '这次的比赛什么时候报名、什么时候交作品？' },
      { key: 'study', tone: 'study', label: '刷题陪练', desc: '出题 + 讲思路', preset: '出两道动态规划的题给我练练，顺便讲讲思路' }
    ],
    // 知识库概况
    kb: { chunks: 0, docs: 0, sources: [] }, kbShow: false,
    // 等待回答时的流程提示
    thinkSteps: THINK_STEPS, thinkStep: 0,
    // 拍照识别
    imgSheet: false,          // 选用途的弹层
    vModes: [
      { key: 'solve', label: '拍题解题', desc: '转写题干，交给刷题智能体讲解' },
      { key: 'notice', label: '拍通知转待办', desc: '抽出关键时间点，生成带倒计时的待办' },
      { key: 'scores', label: '拍成绩单导入', desc: '识别课程学分分数，写进成绩页' },
      { key: 'ask', label: '图片问答', desc: '看图回答问题' }
    ],
    // 成绩单识别结果确认
    scoreShow: false, scoreList: []
  },

  onLoad() {
    this.setData({ greeting: greeting() });
    this.loadKb();
  },

  // 知识库收录情况（空态里展示，回答完也算有个交代）
  loadKb() {
    wx.request({
      url: API + '/kb/stats', timeout: 10000,
      success: r => {
        const d = r.data || {};
        if (d.ok) this.setData({ kb: { chunks: d.chunks || 0, docs: d.docs || 0, sources: d.sources || [] } });
      }
    });
  },
  openKb() { if (this.data.kb.sources.length) this.setData({ kbShow: true }); },
  closeKb() { this.setData({ kbShow: false }); },

  // 空态能力卡：材料走选类型弹层，其余直接发问
  onWelcomeCard(e) {
    const key = e.currentTarget.dataset.key;
    const card = this.data.welcomeCards.find(c => c.key === key);
    if (!card) return;
    if (key === 'doc') { this.setData({ docPick: true }); return; }
    this.setData({ input: card.preset }, () => this.send());
  },

  // 等待中的流程动画：一步步点亮，最后一行停住直到回答返回
  startThink() {
    this.stopThink();
    this.setData({ thinkStep: 0 });
    this._thinkTimer = setInterval(() => {
      if (this.data.thinkStep >= THINK_STEPS.length - 1) return;
      this.setData({ thinkStep: this.data.thinkStep + 1 });
    }, 1200);
  },
  stopThink() {
    if (this._thinkTimer) { clearInterval(this._thinkTimer); this._thinkTimer = null; }
  },

  onUnload() { this.stopThink(); },

  onShow() {
    // 从「选择大模型」页返回时刷新当前模型显示
    const llm = wx.getStorageSync('llm');
    const label = llm && llm.apiKey
      ? (llm.name || llm.provider) + ' · ' + (llm.model || '')
      : '默认模型';
    this.setData({ modelLabel: label });

    // 其他页面（如成绩页）带过来的提问，自动发出
    const pending = app.globalData.pendingAsk;
    if (pending) {
      app.globalData.pendingAsk = '';
      this.setData({ input: pending }, () => this.send());
    }
  },

  goModel() { wx.navigateTo({ url: '/pages/model/model' }); },

  onInput(e) { this.setData({ input: e.detail.value }); },

  onQuick(e) { this.setData({ input: e.currentTarget.dataset.q }, () => this.send()); },

  // 能力入口：点了直接发一句能触发对应 Agent 的话
  onCap(e) {
    const key = (e.currentTarget.dataset.cap || '').trim();
    if (key === 'doc') { this.setData({ docPick: true }); return; }
    const preset = {
      qa: '挂科了怎么重修？',
      schedule: '这次院内挑战赛什么时候报名、什么时候交作品？',
      study: '蓝桥杯该怎么备赛？我的动态规划比较弱'
    }[key];
    if (preset) {
      this.setData({ input: preset }, () => this.send());
    } else {
      wx.showToast({ title: '未识别的入口：' + key, icon: 'none' });
    }
  },
  closeDocPick() { this.setData({ docPick: false }); },
  pickDocType(e) {
    const t = e.currentTarget.dataset.t;
    this.setData({ docPick: false, input: '帮我写一份' + t + '：' }, () => this.send());
  },

  // ==================== 拍照识别 ====================

  // 选图 → 选用途 → 发送
  pickImage() {
    if (this.data.loading) return;
    wx.chooseMedia({
      count: 1, mediaType: ['image'], sizeType: ['compressed'],
      sourceType: ['camera', 'album'],
      success: res => {
        const f = (res.tempFiles || [])[0];
        if (!f) return;
        this._rawImg = f.tempFilePath;
        this.setData({ imgSheet: true });
      },
      fail: () => {}   // 用户取消不提示
    });
  },
  closeImgSheet() { this.setData({ imgSheet: false }); },
  pickImgMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ imgSheet: false });
    this.sendImage(mode);
  },

  sendImage(mode) {
    const path = this._rawImg;
    if (!path || this.data.loading) return;
    const vm = this.data.vModes.find(v => v.key === mode) || { label: '图片' };
    const typed = (this.data.input || '').trim();
    const bubbleText = typed || vm.label;

    const messages = this.data.messages.concat([{ role: 'user', content: bubbleText, image: path }]);
    this.setData({
      messages, input: '', loading: true,
      thinkSteps: THINK_VISION, thinkStep: 0
    }, this.scrollToBottom);
    this.startThink();

    // 压缩后再转 base64，省流量也省 token
    wx.compressImage({
      src: path, quality: 70,
      success: r => this._sendVision(r.tempFilePath || path, mode, typed),
      fail: () => this._sendVision(path, mode, typed)
    });
  },

  _sendVision(file, mode, typed) {
    wx.getFileSystemManager().readFile({
      filePath: file, encoding: 'base64',
      success: res => {
        const ext = (file.split('.').pop() || 'jpg').toLowerCase();
        const mime = ext === 'png' ? 'image/png' : (ext === 'webp' ? 'image/webp' : 'image/jpeg');
        const dataUrl = 'data:' + mime + ';base64,' + res.data;
        if (dataUrl.length > 7 * 1024 * 1024) {
          this.stopThink();
          this.setData({ loading: false });
          wx.showToast({ title: '图片太大了，换一张', icon: 'none' });
          return;
        }

        const history = this.data.messages
          .filter(m => (m.role === 'user' || m.role === 'assistant') && !m.image)
          .map(m => ({ role: m.role, content: m.content }));

        const llm = wx.getStorageSync('llm');
        const vl = wx.getStorageSync('visionLlm');

        wx.request({
          url: API + '/chat/vision', method: 'POST', timeout: 120000,
          data: {
            image: dataUrl, mode, message: typed, history,
            courses: app.getCourses(), ddls: app.getDdls(),
            user_name: app.globalData.userName,
            llm: llm && llm.apiKey ? { provider: llm.provider, api_key: llm.apiKey, model: llm.model } : null,
            vision_llm: vl && vl.apiKey ? { provider: vl.provider, api_key: vl.apiKey, model: vl.model } : null
          },
          success: r => {
            const d = r.data || {};
            if (!d.ok) { this.appendAssistant('出错了：' + (d.error || '未知错误')); return; }
            if (d.mode === 'scores') {
              this.appendAssistant(d.reply || '');
              const list = (d.courses || []).map(c => ({ ...c, on: true }));
              if (list.length) this.setData({ scoreShow: true, scoreList: list });
              return;
            }
            const srcs = [...new Set((d.sources || []).map(s => s.source))];
            const todoCall = (d.tool_calls || []).find(t => t.name === 'gen_todos' && t.result && t.result.ok);
            const docCall = (d.tool_calls || []).find(t => t.name === 'gen_document' && t.result && t.result.ok);
            if (docCall) app.addMine('doc', { title: docCall.result.title, docType: docCall.result.doc_type });
            this.appendAssistant(d.reply || '（没有返回内容）', srcs,
              docCall ? docCall.result : null, d.agent || '', d.agent_name || '',
              todoCall ? todoCall.result.todos : null, d.ocr || '');
          },
          fail: () => this.appendAssistant('识别失败：连接后端失败，请确认后端已启动。'),
          complete: () => { this.stopThink(); this.setData({ loading: false }, this.scrollToBottom); }
        });
      },
      fail: () => {
        this.stopThink();
        this.setData({ loading: false });
        wx.showToast({ title: '读取图片失败，换一张试试', icon: 'none' });
      }
    });
  },

  // 识别出的文字：展开/收起
  toggleOcr(e) {
    const i = e.currentTarget.dataset.idx;
    this.setData({ ['messages[' + i + '].ocrOpen']: !this.data.messages[i].ocrOpen });
  },

  // ---------- 成绩单导入确认 ----------
  closeScore() { this.setData({ scoreShow: false }); },
  toggleScore(e) {
    const i = e.currentTarget.dataset.i;
    this.setData({ ['scoreList[' + i + '].on']: !this.data.scoreList[i].on });
  },
  importScores() {
    const picked = this.data.scoreList.filter(c => c.on);
    if (!picked.length) { wx.showToast({ title: '至少选一门课', icon: 'none' }); return; }
    const courses = app.getCourses() || [];
    const have = {};
    courses.forEach(c => { have[c.name] = 1; });
    const add = picked.filter(c => !have[c.name]);
    this.setData({ scoreShow: false });
    if (!add.length) {
      wx.showToast({ title: '这几门成绩页里已经有了', icon: 'none' });
      return;
    }
    wx.setStorageSync('courses', courses.concat(add.map(c => ({
      name: c.name, credit: c.credit, score: c.score
    }))));
    wx.showModal({
      title: '已导入 ' + add.length + ' 门',
      content: '去成绩页看看重算后的绩点？',
      confirmText: '去看看', cancelText: '留在这',
      success: r => { if (r.confirm) wx.switchTab({ url: '/pages/scores/scores' }); }
    });
  },

  send() {
    const text = (this.data.input || '').trim();
    if (!text || this.data.loading) return;

    const history = this.data.messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }));

    // 用户自选的大模型（存本地，随请求发给后端；服务端不落库）
    const llm = wx.getStorageSync('llm');
    const llmPayload = llm && llm.apiKey
      ? { provider: llm.provider, api_key: llm.apiKey, model: llm.model }
      : null;

    const messages = this.data.messages.concat([{ role: 'user', content: text }]);
    this.setData({
      messages, input: '', loading: true, thinkSteps: THINK_STEPS
    }, this.scrollToBottom);
    this.startThink();

    wx.request({
      url: app.globalData.apiBase + '/chat',
      method: 'POST',
      data: {
        message: text,
        history: history,
        courses: app.getCourses(),
        ddls: app.getDdls(),
        user_name: app.globalData.userName,
        llm: llmPayload
      },
      timeout: 60000,
      success: (res) => {
        const d = res.data || {};
        if (d.ok) {
          const srcs = (d.sources || []).map(s => s.source);
          // 若本轮调用了 gen_document，则附带一份可编辑、可导出的材料
          const call = (d.tool_calls || []).find(t => t.name === 'gen_document' && t.result && t.result.ok);
          const todoCall = (d.tool_calls || []).find(t => t.name === 'gen_todos' && t.result && t.result.ok);
          // 记到本地「我生成的材料」
          if (call) app.addMine('doc', { title: call.result.title, docType: call.result.doc_type });
          this.appendAssistant(d.reply || '（没有返回内容）', [...new Set(srcs)],
            call ? call.result : null, d.agent || '', d.agent_name || '',
            todoCall ? todoCall.result.todos : null);
        } else {
          this.appendAssistant('出错了：' + (d.error || '未知错误'));
        }
      },
      fail: () => this.appendAssistant('连接后端失败，请确认后端已启动、域名已配置。'),
      complete: () => { this.stopThink(); this.setData({ loading: false }, this.scrollToBottom); }
    });
  },

  appendAssistant(content, sources, doc, agent, agentName, todos, ocr) {
    const messages = this.data.messages.concat([{
      role: 'assistant', content, sources, doc: doc || null,
      agent: agent || '', agentName: agentName || '',
      todos: todos || null,
      ocr: ocr || '', ocrOpen: false
    }]);
    // 换一批"接着问"，让人能顺着聊下去
    this.setData({
      messages,
      quickAsks: FOLLOWUPS[agent] || FOLLOWUPS[''],
      quickLabel: '接着问'
    }, this.scrollToBottom);
  },

  // 长按气泡里的回答可以复制走
  copyMsg(e) {
    const m = this.data.messages[e.currentTarget.dataset.idx];
    if (!m || m.role !== 'assistant') return;
    wx.setClipboardData({ data: m.content, success: () => wx.showToast({ title: '已复制', icon: 'none' }) });
  },

  // ---------- 材料生成：字段编辑 + 导出 ----------
  noop() {},

  editDoc(e) {
    const idx = e.currentTarget.dataset.idx;
    const doc = this.data.messages[idx].doc;
    if (!doc) return;
    const fields = doc.fields.map(f => ({
      ...f,
      multi: MULTI_KEYS.some(k => f.label.indexOf(k) >= 0)
    }));
    this.setData({ docEdit: { show: true, idx, docType: doc.doc_type, title: doc.title, fields } });
  },
  closeDocEdit() { this.setData({ 'docEdit.show': false }); },
  onFieldInput(e) {
    const i = e.currentTarget.dataset.i;
    this.setData({ ['docEdit.fields[' + i + '].value']: e.detail.value });
  },
  saveDocEdit() {
    const { idx, docType, fields } = this.data.docEdit;
    const payload = {};
    fields.forEach(f => { payload[f.label] = f.value; });
    wx.showLoading({ title: '更新中…' });
    wx.request({
      url: API + '/doc/render', method: 'POST', timeout: 15000,
      data: { doc_type: docType, fields: payload },
      success: r => {
        const d = r.data || {};
        wx.hideLoading();
        if (d.ok) {
          this.setData({
            ['messages[' + idx + '].doc.text']: d.text,
            ['messages[' + idx + '].doc.fields']: d.fields,
            'docEdit.show': false
          });
          wx.showToast({ title: '已更新' });
        } else {
          wx.showToast({ title: d.msg || '更新失败', icon: 'none' });
        }
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '连接失败', icon: 'none' }); }
    });
  },
  exportDoc(e) {
    const idx = e.currentTarget.dataset.idx;
    const doc = this.data.messages[idx].doc;
    if (!doc) return;
    wx.showLoading({ title: '生成文档…' });
    wx.request({
      url: API + '/doc/export', method: 'POST', timeout: 20000,
      data: { title: doc.title, text: doc.text },
      success: r => {
        const d = r.data || {};
        if (!d.ok) { wx.hideLoading(); wx.showToast({ title: d.msg || '导出失败', icon: 'none' }); return; }
        wx.downloadFile({
          url: API + d.url,
          success: res => {
            wx.hideLoading();
            wx.openDocument({
              filePath: res.tempFilePath, fileType: 'docx', showMenu: true,
              fail: () => wx.showToast({ title: '打开失败，请重试', icon: 'none' })
            });
          },
          fail: () => { wx.hideLoading(); wx.showToast({ title: '下载失败', icon: 'none' }); }
        });
      },
      fail: () => { wx.hideLoading(); wx.showToast({ title: '连接失败', icon: 'none' }); }
    });
  },

  scrollToBottom() {
    this.setData({ scrollTop: this.data.messages.length * 100000 });
  }
});
