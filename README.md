# 校园服务智能体（AI+校园）· 微信小程序

> 西安思源学院电子信息工程学院第二届计算机综合实践挑战赛 · **T4 AI 应用与软件开发赛**参赛作品
>
> 一款"能答会办"的校园服务智能体小程序：以 RAG 知识库问答为底座，叠加大模型 function-calling 工具调用，帮同学解答校园制度流程，并能查成绩、算绩点、**生成事务材料并导出 Word**、整理 DDL。

## 命中的 AI 能力（对应赛题要求「至少含一项」，本作品含三项）

| AI 能力 | 实现 |
|---|---|
| RAG 知识库检索 | 校园制度文档切块入 Chroma 向量库，检索 top-k 片段并**标注来源**作答，不编造 |
| 大模型问答 | DeepSeek 自然语言理解与生成，口语化应答 |
| 工具调用（Agent） | 大模型 function-calling 自主决定调用 查成绩 / 算绩点 / **生成材料** / DDL 四个工具 |
| 材料生成闭环 | 口语描述 → 抽取结构化字段 → 模板渲染成正式材料 → 人工编辑确认 → **导出 Word**（不止问答） |
| 多 Agent 协同 | 路由式调度：**校园问答 / 刷题陪练 / 材料撰写 / 日程提醒** 四个专职智能体，各有独立提示词与工具子集 |
| 时间意图检索 | 问"什么时候/截止/赛程"时，自动把含具体日期的片段召回并加权；配套「待办卡片」给出倒计时 |
| 多模型可插拔 | 问答页可切换 8 家国内主流大模型（DeepSeek/通义千问/智谱/Kimi/文心/星火/混元/豆包），用户填自己的 API Key 调用 |

### 切换大模型 / 自带 Key

问答页顶部有「切换模型」条，点开可选厂商、选模型、填入自己的 API Key。
- Key 只保存在**用户手机本地**（`wx.storage`），随请求发给后端**仅用于当次调用，服务端不落库**。
- 各厂商均使用 OpenAI 兼容接口，后端统一用一份 SDK 调用；未配置时回退服务端默认模型。
- 厂商与默认地址见 `backend/app/providers.py`，可自行增删。

## 目录结构

```
campus-agent/
├─ backend/                FastAPI 后端
│  ├─ app/
│  │  ├─ main.py           API：/chat、/rag/upload、/life/*、/auth/*、/health
│  │  ├─ agent.py          Agent 核心：意图路由 + RAG 注入 + function-calling 循环
│  │  ├─ agent_defs.py     多 Agent 定义（4 个专职智能体的提示词与工具子集）
│  │  ├─ life.py           「生活」栏后端：天气/食堂推荐(接口保留)/失物招领
│  │  ├─ market.py         二手市场：商品 + 图片上传 + 静态托管
│  │  ├─ documents.py      材料模板库 + 渲染 + 导出 .docx
│  │  ├─ auth.py           微信登录：code→openid→会话 token
│  │  ├─ providers.py      大模型厂商注册表（8 家国内主流，OpenAI 兼容）
│  │  ├─ config.py         配置（从 .env 读密钥）
│  │  └─ tools/__init__.py 四个工具 + JSON Schema + 注册表
│  ├─ rag/store.py         Chroma 向量库：切块 / 入库 / 检索
│  ├─ scripts/ingest.py    批量导入 data/docs/ 下的校园文档
│  ├─ tests/test_tools.py  工具层单元测试（7 条，纯逻辑可复现）
│  └─ data/docs/           示例校园文档（请替换为学校官方文件）
└─ miniprogram/            微信原生小程序
   ├─ pages/chat/          问答（核心页，含来源标注、快捷提问）
   ├─ pages/scores/        成绩录入 + 本地绩点计算
   ├─ pages/life/          生活：天气·校历 / 快递外卖 / 失物招领
   ├─ pages/model/         选择大模型：切换厂商 + 填自己的 API Key
   └─ pages/mine/          我的：微信登录 + 个人中心
```

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

copy .env.example .env        # 然后填入 DeepSeek 密钥 LLM_API_KEY

python scripts\ingest.py      # 导入 data/docs 下的校园文档到向量库
uvicorn app.main:app --reload # 启动，默认 http://127.0.0.1:8000
```

验证：浏览器打开 `http://127.0.0.1:8000/health` 应返回 `docs_indexed` 数量。

### 小程序

1. 用微信开发者工具导入项目根目录（`campus-agent/`）。
2. 本地调试：设置 → 关闭「不校验合法域名」。
3. `miniprogram/app.js` 里 `apiBase` 默认指向本地后端，上线时改为 https 域名。

### 跑测试

```bash
cd backend
python -I tests\test_tools.py       # 或 python -I -m pytest tests/ -v
```

## 数据与合规说明

- 成绩数据由用户在小程序本地录入，仅存手机 `wx.storage`，随对话发给后端做即时计算，**后端不落库、不爬取教务系统**，落地合规。
- 校园制度文档请使用学校公开/授权文件；`data/docs/` 内为示例，须替换。
- 大模型密钥通过 `.env` 注入，不入库、不进 git。

## AI 工具使用声明

见 `docs/AI工具使用声明.md`（随作品提交，对应赛事纪律要求）。
