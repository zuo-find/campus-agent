"""FastAPI 入口：对小程序暴露 /chat 与 RAG 文档导入接口。"""
from __future__ import annotations

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import agent, auth, life, providers
from app.tools import ToolContext
from rag import store

app = FastAPI(title="校园服务智能体 API", version="0.1.0")

# 开发阶段放开跨域；上线时收紧为小程序域名
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

life.init_db()  # 启动即建失物招领表
auth.init_db()  # 启动即建用户表


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


class ChatReq(BaseModel):
    message: str
    history: list[dict] = []
    courses: list[Course] = []
    ddls: list[Ddl] = []
    user_name: str = "同学"
    llm: LLMConfig | None = None


@app.get("/health")
def health():
    return {"ok": True, "docs_indexed": store._get_collection().count()}


@app.get("/providers")
def providers_list():
    """可供选择的大模型厂商列表（不含任何密钥）。"""
    return {"ok": True, "providers": providers.list_providers()}


def _friendly_llm_error(e: Exception) -> str:
    """把大模型调用异常转成用户看得懂的提示。"""
    s = str(e)
    low = s.lower()
    if "401" in s or "authentication" in low or "invalid" in low and "key" in low:
        return "API Key 无效或已过期，请点问答页顶部的「切换模型」检查你填的 Key。"
    if "404" in s or "model" in low and "not found" in low:
        return "模型名不存在，请点问答页顶部的「切换模型」换一个模型。"
    if "429" in s or "rate" in low or "quota" in low:
        return "调用太频繁或额度用尽，稍后再试，或换一个模型/Key。"
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
        return {"ok": True, **agent.chat(req.message, req.history, ctx, llm=llm)}
    except Exception as e:  # 统一错误出口，转成用户看得懂的话
        return {"ok": False, "error": _friendly_llm_error(e)}


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


@app.post("/life/lostfound")
def life_lf_add(req: LostFoundReq):
    return life.add_lost_found(req.kind, req.title, req.location, req.contact, req.detail)


@app.get("/life/lostfound")
def life_lf_list(kind: str = ""):
    return life.list_lost_found(kind)


@app.post("/life/lostfound/{item_id}/close")
def life_lf_close(item_id: int):
    return life.close_lost_found(item_id)


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
