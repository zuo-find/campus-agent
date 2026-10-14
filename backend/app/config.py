"""应用配置：从环境变量 / .env 读取。不把密钥写进代码。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 大模型（DeepSeek，OpenAI 兼容接口）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # 图像识别（多模态模型）。DeepSeek 看不了图，所以单独配一套；
    # 留空则要求用户在小程序「大模型设置 → 识图模型」里自填 Key。
    vision_api_key: str = ""
    vision_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    vision_model: str = "glm-4v-flash"

    # 微信小程序登录（填了 appid+secret 走真实登录，否则降级游客模式）
    wx_appid: str = ""
    wx_secret: str = ""

    # 向量库 / RAG
    chroma_dir: str = "./data/chroma"
    rag_collection: str = "campus_docs"
    rag_top_k: int = 4

    # 嵌入模型：DeepSeek 暂无 embedding 接口，默认用 chroma 自带的本地模型，
    # 若配置了 embedding_api_key 则走远程（如智谱/openai）。
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""

    app_host: str = "0.0.0.0"
    app_port: int = 8000


settings = Settings()
