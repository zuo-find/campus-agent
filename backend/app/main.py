"""FastAPI 入口：对小程序暴露 /chat 与 RAG 文档导入接口。"""
from __future__ import annotations

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import agent, life
from app.tools import ToolContext
from rag import store

app = FastAPI(title="校园服务智能体 API", version="0.1.0")

# 开发阶段放开跨域；上线时收紧为小程序域名
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

life.init_db()  # 启动即建失物招领表


class Course(BaseModel):
    name: str
    credit: float
    score: float | None = None


class Ddl(BaseModel):
    title: str
    due: str  # YYYY-MM-DD


class ChatReq(BaseModel):
    message: str
    history: list[dict] = []
    courses: list[Course] = []
    ddls: list[Ddl] = []
    user_name: str = "同学"


@app.get("/health")
def health():
    return {"ok": True, "docs_indexed": store._get_collection().count()}


@app.post("/chat")
def chat(req: ChatReq):
    ctx = ToolContext(
        courses=[c.model_dump() for c in req.courses],
        ddls=[d.model_dump() for d in req.ddls],
        user_name=req.user_name,
    )
    try:
        return {"ok": True, **agent.chat(req.message, req.history, ctx)}
    except Exception as e:  # 统一错误出口，前端好处理
        return {"ok": False, "error": str(e)}


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
