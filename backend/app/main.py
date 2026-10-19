"""FastAPI 入口：对小程序暴露 /chat 与 RAG 文档导入接口。"""
from __future__ import annotations

import os

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import (agent, auth, documents, files, life, market, providers, school_sync,
                 universities, vision)
from app.tools import ToolContext
from rag import store

app = FastAPI(title="校园服务智能体 API", version="0.1.0")

# 开发阶段放开跨域；上线时收紧为小程序域名
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

life.init_db()        # 启动即建失物招领表
auth.init_db()        # 启动即建用户表
market.init_db()      # 启动即建二手市场表
school_sync.init_db() # 启动即建官网同步表
os.makedirs(documents.EXPORT_DIR, exist_ok=True)
# 静态托管：二手市场图片、导出的文档
app.mount("/uploads", StaticFiles(directory=market.UPLOAD_DIR), name="uploads")
app.mount("/exports", StaticFiles(directory=documents.EXPORT_DIR), name="exports")


class Course(BaseModel):
    name: str
    credit: float
    score: float | None = None


class Ddl(BaseModel):
    title: str
    due: str  # YYYY-MM-DD


class LLMConfig(BaseModel):
    """用户自选的大模型配置；key 由前端本地保存、随请求传入，服务端不落库。"""
    provider: str = ""
    api_key: str = ""
    model: str = ""


class ChatFile(BaseModel):
    """前端已解析好的文件：只要文件名和正文，原文件不必再传一遍。"""
    name: str = ""
    text: str = ""


class ChatReq(BaseModel):
    message: str
    history: list[dict] = []
    courses: list[Course] = []
    ddls: list[Ddl] = []
    user_name: str = "同学"
    llm: LLMConfig | None = None
    agent_key: str = ""     # 指定智能体；留空则由路由自动判断
    files: list[ChatFile] = []


class VisionReq(BaseModel):
    """拍照识别请求：图 + 用途 +（可选）要问的话。"""
    image: str              # data:image/jpeg;base64,... 形式
    mode: str = "ask"       # ask 图片问答 / solve 拍题 / notice 拍通知 / scores 拍成绩单
    message: str = ""
    history: list[dict] = []
    courses: list[Course] = []
    ddls: list[Ddl] = []
    user_name: str = "同学"
    llm: LLMConfig | None = None          # 文本模型（讲解/生成待办用）
    vision_llm: LLMConfig | None = None   # 识图模型（多模态）


@app.get("/health")
def health():
    return {"ok": True, "docs_indexed": store._get_collection().count()}


@app.get("/providers")
def providers_list():
    """可供选择的大模型厂商列表（不含任何密钥）。"""
    return {"ok": True, "providers": providers.list_providers()}


class ModelListReq(BaseModel):
    provider: str = ""
    api_key: str = ""


@app.post("/providers/models")
def providers_models(req: ModelListReq):
    """用用户自己的 Key 去厂商拉当前可用的模型列表。

    内置列表更新不及时（各家一年换一代），这个接口让用户随时能拿到真实型号。
    """
    key = (req.api_key or "").strip()
    if not key:
        return {"ok": False, "error": "先填上 API Key 再拉取"}
    try:
        models = providers.fetch_models(req.provider, key)
    except Exception as e:
        s = str(e)
        if "401" in s or "403" in s or "auth" in s.lower():
            return {"ok": False, "error": "Key 不对或没权限，检查一下是不是复制全了"}
        if "404" in s:
            return {"ok": False, "error": "这家没提供模型列表接口，直接在下面手填模型名"}
        if "connect" in s.lower() or "timeout" in s.lower():
            return {"ok": False, "error": "连不上这家的服务器，检查网络后重试"}
        return {"ok": False, "error": "拉取失败：" + s[:120]}
    if not models:
        return {"ok": False, "error": "这家返回的列表是空的，直接在下面手填模型名"}
    return {"ok": True, "models": models, "count": len(models)}


@app.get("/providers/vision")
def providers_vision():
    """支持识图的厂商与多模态模型（不含任何密钥）。"""
    return {"ok": True, "providers": providers.list_vision_providers()}


@app.get("/kb/stats")
def kb_stats():
    """知识库概况：片段数 + 收录了哪些资料。问答页空态会展示这份数据。"""
    col = store._get_collection()
    total = col.count()
    sources: list[str] = []
    try:
        metas = (col.get(include=["metadatas"]) or {}).get("metadatas") or []
        names = {(m or {}).get("source", "") for m in metas}
        sources = sorted(n for n in names if n)
    except Exception:
        sources = []   # 元数据读取失败不影响问答，只让概况少一块
    return {"ok": True, "chunks": total, "docs": len(sources), "sources": sources}


def _friendly_llm_error(e: Exception) -> str:
    """把大模型调用异常转成用户看得懂的提示。"""
    s = str(e)
    low = s.lower()
    # 配置缺失类错误（如识图模型没配）本身就是给用户看的，原样返回
    if "还没配置" in s or "未配置" in s:
        return s
    if "401" in s or "authentication" in low or "invalid" in low and "key" in low:
        return "API Key 无效或已过期，请点问答页顶部的「切换模型」检查你填的 Key。"
    if "404" in s or "model" in low and "not found" in low:
        return "模型名不存在，请点问答页顶部的「切换模型」换一个模型。"
    if "429" in s or "rate" in low or "quota" in low:
        return "调用太频繁或额度用尽，稍后再试，或换一个模型/Key。"
    if "max_tokens" in s:
        return "这个模型对输出长度有上限，本次请求超出被拒。已自动降档，请再发一次。"
    if "connect" in low or "timeout" in low or "timed out" in low:
        return "连接大模型服务失败，检查网络，或确认该厂商的调用地址是否可达。"
    return "调用出错了：" + s[:200]


@app.post("/chat")
def chat(req: ChatReq):
    ctx = ToolContext(
        courses=[c.model_dump() for c in req.courses],
        ddls=[d.model_dump() for d in req.ddls],
        user_name=req.user_name,
    )
    llm = req.llm.model_dump() if req.llm else None
    try:
        return {"ok": True, **agent.chat(req.message, req.history, ctx, llm=llm,
                                         agent_key=req.agent_key or None,
                                         files=[f.model_dump() for f in req.files])}
    except Exception as e:  # 统一错误出口，转成用户看得懂的话
        return {"ok": False, "error": _friendly_llm_error(e)}


@app.post("/chat/vision")
def chat_vision(req: VisionReq):
    """拍照识别：按用途走「识图 → 讲解 / 待办 / 结构化成绩」。"""
    if not req.image.startswith("data:image/"):
        return {"ok": False, "error": "图片格式不对，请重新选择一张图片。"}
    if len(req.image) > 5 * 1024 * 1024:
        return {"ok": False, "error": "图片太大了，换一张分辨率低一点的（多数识图模型限单图 5MB）。"}
    ctx = ToolContext(
        courses=[c.model_dump() for c in req.courses],
        ddls=[d.model_dump() for d in req.ddls],
        user_name=req.user_name,
    )
    try:
        return {"ok": True, **vision.handle(
            req.image, req.mode, req.message, req.history, ctx,
            llm=req.llm.model_dump() if req.llm else None,
            vision_llm=req.vision_llm.model_dump() if req.vision_llm else None,
        )}
    except Exception as e:
        return {"ok": False, "error": _friendly_llm_error(e)}


@app.post("/file/parse")
async def file_parse(file: UploadFile = File(...)):
    """解析一个上传的文件（PDF / Word / 文本），返回正文给前端。

    只解析、不落库：文件正文由前端随提问一起发回，用完即弃。
    """
    raw = await file.read()
    return files.parse(file.filename or "未命名文件", raw)


@app.post("/rag/upload")
async def rag_upload(file: UploadFile = File(...)):
    """上传一篇校园文档（txt/pdf）并入库。后台管理用。"""
    raw = await file.read()
    name = file.filename or "doc"
    if name.lower().endswith(".pdf"):
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    else:
        text = raw.decode("utf-8", errors="ignore")
    n = store.add_document(doc_id=name, text=text, source=name)
    return {"ok": True, "source": name, "chunks": n}


# ------------------------------------------------------------ 「生活」栏

@app.get("/life/weather")
def life_weather():
    try:
        return {"ok": True, **life.weather_advice()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class MealReq(BaseModel):
    taste: str = ""
    budget: float = 0
    meal: str = "午餐"


@app.post("/life/meal")
def life_meal(req: MealReq):
    try:
        return {"ok": True, **life.recommend_meal(req.taste, req.budget, req.meal)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class LostFoundReq(BaseModel):
    kind: str            # lost / found
    title: str
    location: str = ""
    contact: str = ""
    detail: str = ""
    images: list[str] = []      # 照片（最多 3 张，先传到 /life/market/upload 拿地址）


@app.post("/life/lostfound")
def life_lf_add(req: LostFoundReq):
    return life.add_lost_found(req.kind, req.title, req.location, req.contact,
                               req.detail, req.images)


@app.get("/life/lostfound")
def life_lf_list(kind: str = ""):
    return life.list_lost_found(kind)


@app.post("/life/lostfound/{item_id}/close")
def life_lf_close(item_id: int):
    return life.close_lost_found(item_id)


# ------------------------------------------------------------ 官网信息同步

class SchoolSourceReq(BaseModel):
    category: str
    url: str


@app.get("/school/search")
def school_search(q: str = "", limit: int = 30):
    """按校名搜学校，用于「选择学校」自动填官网地址。"""
    return {"ok": True, **universities.count(),
            "items": universities.search(q, max(1, min(limit, 60)))}


@app.get("/school/sources")
def school_sources():
    """已配置的同步网址与可用的类别。"""
    return school_sync.list_sources()


@app.post("/school/source")
def school_set_source(req: SchoolSourceReq):
    """保存某类别要同步的官网网址。"""
    return school_sync.set_source(req.category, req.url)


class SchoolSyncReq(BaseModel):
    category: str = ""


@app.post("/school/sync")
def school_do_sync(req: SchoolSyncReq):
    """抓取并抽取（留空 category 则同步全部已配置的类别）。"""
    try:
        return school_sync.sync(req.category)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/school/items")
def school_items(category: str = ""):
    """同步后的结构化条目。"""
    return school_sync.get_items(category)


# ------------------------------------------------------------ 材料生成 / 导出

class DocRenderReq(BaseModel):
    doc_type: str
    fields: dict = {}


@app.get("/doc/types")
def doc_types():
    """可生成的材料类型。"""
    return {"ok": True, "types": documents.doc_types()}


@app.post("/doc/render")
def doc_render(req: DocRenderReq):
    """用新字段重新渲染材料（前端编辑字段后调用）。"""
    return documents.render(req.doc_type, req.fields)


class DocExportReq(BaseModel):
    title: str = ""
    text: str = ""


@app.post("/doc/export")
def doc_export(req: DocExportReq):
    """把材料文本导出为 .docx，返回下载地址。"""
    return documents.export_docx(req.title, req.text)


# ------------------------------------------------------------ 二手市场

class MarketReq(BaseModel):
    title: str
    price: float
    orig_price: float | None = None
    category: str = ""
    detail: str = ""
    images: list[str] = []
    contact: str = ""


@app.get("/life/market")
def market_list(category: str = ""):
    return market.list_items(category)


@app.get("/life/market/{item_id}")
def market_detail(item_id: int):
    return market.get_item(item_id)


@app.post("/life/market")
def market_create(req: MarketReq):
    return market.add_item(req.title, req.price, req.orig_price, req.category,
                           req.detail, req.images, req.contact)


@app.post("/life/market/{item_id}/sold")
def market_sold(item_id: int):
    return market.mark_sold(item_id)


@app.post("/life/market/upload")
async def market_upload(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        return {"ok": False, "msg": "图片过大（限 8MB）"}
    url = market.save_image(data, file.filename or "img.jpg")
    return {"ok": True, "url": url}


# ------------------------------------------------------------ 微信登录

class LoginReq(BaseModel):
    code: str


@app.post("/auth/login")
def auth_login(req: LoginReq):
    """小程序 wx.login 的 code → openid → 会话 token。"""
    try:
        return auth.login(req.code)
    except Exception as e:
        return {"ok": False, "error": str(e)}


class ProfileReq(BaseModel):
    token: str
    nickname: str = ""
    avatar: str = ""


@app.post("/auth/profile")
def auth_profile(req: ProfileReq):
    return auth.update_profile(req.token, req.nickname, req.avatar)


@app.get("/auth/me")
def auth_me(token: str):
    return auth.get_user(token)
