"""国内主流大模型 provider 注册表（均提供 OpenAI 兼容接口）。

用户在小程序里选一个 provider、填自己的 API Key，key 只存在用户手机本地，
随请求发到后端，仅用于当次调用、服务端不落库。
"""

PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "name": "DeepSeek 深度求索",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-v4-pro", "deepseek-v4-flash",
                   "deepseek-reasoner", "deepseek-chat"],
        "key_url": "https://platform.deepseek.com/api_keys",
        "note": "最强 deepseek-v4-pro；快而便宜选 deepseek-v4-flash",
    },
    "qwen": {
        "name": "通义千问（阿里云）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.7-max", "qwen3.7-plus", "qwen3.7-flash",
                   "qwen3.6-plus", "qwen3.5-plus", "qwen3.5-flash",
                   "qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"],
        "vision": ["qwen-vl-max", "qwen-vl-plus"],
        "key_url": "https://bailian.console.aliyun.com/",
        "note": "最强 qwen3.7-max；日常够用 qwen3.7-flash",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.3", "glm-5.3-flash", "glm-5.2", "glm-5", "glm-5-turbo",
                   "glm-4-plus", "glm-4-flash"],
        "vision": ["glm-5v-turbo", "glm-4v-plus", "glm-4v-flash"],
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "note": "最强 glm-5.3；glm-4-flash 与 glm-4v-flash 有免费额度",
    },
    "moonshot": {
        "name": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3", "kimi-k2.8-preview", "kimi-k2.7-code",
                   "kimi-k2.6", "kimi-k2.5",
                   "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "vision": ["moonshot-v1-8k-vision-preview", "moonshot-v1-32k-vision-preview"],
        "key_url": "https://platform.moonshot.cn/console/api-keys",
        "note": "最强 kimi-k3；长文本见长，写代码可选 kimi-k2.7-code",
    },
    "ark": {
        "name": "豆包（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-seed-2.1-pro", "doubao-seed-2.1-turbo",
                   "doubao-seed-2.0-pro", "doubao-seed-1.8", "doubao-pro-32k"],
        "vision": ["doubao-1.5-vision-pro-32k"],
        "key_url": "https://console.volcengine.com/ark",
        "note": "最强 doubao-seed-2.1-pro；模型名通常要填接入点 ID",
    },
    "hunyuan": {
        "name": "腾讯混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": ["hy4-preview", "hy3",
                   "hunyuan-turbo", "hunyuan-pro", "hunyuan-standard"],
        "vision": ["hunyuan-vision"],
        "key_url": "https://console.cloud.tencent.com/hunyuan/api-key",
        "note": "最新 hy4-preview；需在腾讯云开通混元",
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V3.1", "deepseek-ai/DeepSeek-V3",
                   "deepseek-ai/DeepSeek-R1", "Qwen/Qwen3-8B",
                   "Qwen/Qwen3-Max", "THUDM/glm-4-9b-chat"],
        "vision": ["Qwen/Qwen2.5-VL-72B-Instruct", "deepseek-ai/DeepSeek-OCR"],
        "key_url": "https://cloud.siliconflow.cn/account/ak",
        "note": "一个 Key 用上百个模型，注册送额度，有免费模型",
    },
    "qianfan": {
        "name": "文心一言（百度千帆）",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-4.0-turbo-8k", "ernie-3.5-8k", "ernie-speed-8k"],
        "key_url": "https://console.bce.baidu.com/qianfan/",
        "note": "千帆 v2 已支持 OpenAI 兼容；型号名建议用「拉取最新列表」",
    },
    "spark": {
        "name": "讯飞星火",
        "base_url": "https://spark-api-open.xf-yun.com/v1",
        "models": ["4.0Ultra", "generalv3.5", "lite"],
        "key_url": "https://console.xfyun.cn/",
        "note": "用 APIKey:APISecret 形式的密钥",
    },
}

# 识图（多模态）推荐顺序：智谱 glm-4v-flash 免费，学生最容易拿到 key
VISION_ORDER = ["zhipu", "qwen", "moonshot", "hunyuan", "ark"]


def list_providers() -> list[dict]:
    """给前端的可选列表（不含任何密钥）。"""
    return [{"id": pid, **{k: v for k, v in p.items()}} for pid, p in PROVIDERS.items()]


def fetch_models(provider: str, api_key: str) -> list[str]:
    """拿用户的 Key 去厂商拉一次真实可用的模型列表。

    各家的型号一年就换一代，内置列表只能当起点。这个函数让小程序里能
    随时拉到当前真正可用的型号，用户不用等我们更新版本。
    """
    import httpx

    base, _, _ = resolve(provider, "")
    url = base.rstrip("/") + "/models"
    # 这些地址都是国内厂商，直连即可；走系统代理反而容易失败
    with httpx.Client(timeout=15, trust_env=False) as client:
        r = client.get(url, headers={"Authorization": "Bearer " + (api_key or "")})
        r.raise_for_status()
        data = r.json()
    ids = [str(m.get("id", "")).strip() for m in (data.get("data") or []) if m.get("id")]
    return sorted(set(ids))


def resolve(provider: str, model: str = "") -> tuple[str, str, str]:
    """返回 (base_url, model, display_name)。provider 不在表内则回退 deepseek。"""
    p = PROVIDERS.get(provider) or PROVIDERS["deepseek"]
    use_model = model or p["models"][0]
    return p["base_url"], use_model, p["name"]


def list_vision_providers() -> list[dict]:
    """支持识图的厂商（本次只列出多模态模型），按易获取程度排序。"""
    def rank(pid: str) -> int:
        return VISION_ORDER.index(pid) if pid in VISION_ORDER else len(VISION_ORDER)

    items = [
        {"id": pid, "name": p["name"], "base_url": p["base_url"], "models": p["vision"],
         "key_url": p.get("key_url", ""), "note": p.get("note", "")}
        for pid, p in PROVIDERS.items() if p.get("vision")
    ]
    return sorted(items, key=lambda x: rank(x["id"]))


def resolve_vision(provider: str, model: str = "") -> tuple[str, str, str]:
    """识图用的 (base_url, model, display_name)。选了不支持识图的厂商则回退智谱。"""
    p = PROVIDERS.get(provider)
    if not p or not p.get("vision"):
        p = PROVIDERS["zhipu"]
    use_model = model or p["vision"][0]   # 豆包等需填接入点 ID，所以允许自定义模型名
    return p["base_url"], use_model, p["name"]
