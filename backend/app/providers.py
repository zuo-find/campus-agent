"""国内主流大模型 provider 注册表（均提供 OpenAI 兼容接口）。

用户在小程序里选一个 provider、填自己的 API Key，key 只存在用户手机本地，
随请求发到后端，仅用于当次调用、服务端不落库。
"""

PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "name": "DeepSeek 深度求索",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "key_url": "https://platform.deepseek.com/api_keys",
        "note": "性价比高，中文强，官方直连",
    },
    "qwen": {
        "name": "通义千问（阿里云）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
        "vision": ["qwen-vl-plus", "qwen-vl-max"],
        "key_url": "https://bailian.console.aliyun.com/",
        "note": "需在阿里云百炼开通并创建 API-KEY",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-air", "glm-4-plus"],
        "vision": ["glm-4v-flash", "glm-4v-plus"],
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "note": "glm-4-flash 有免费额度",
    },
    "moonshot": {
        "name": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "vision": ["moonshot-v1-8k-vision-preview", "moonshot-v1-32k-vision-preview"],
        "key_url": "https://platform.moonshot.cn/console/api-keys",
        "note": "长文本见长",
    },
    "qianfan": {
        "name": "文心一言（百度千帆）",
        "base_url": "https://qianfan.baidubce.com/v2",
        "models": ["ernie-4.0-turbo-8k", "ernie-3.5-8k", "ernie-speed-8k"],
        "key_url": "https://console.bce.baidu.com/qianfan/",
        "note": "千帆 v2 已支持 OpenAI 兼容",
    },
    "spark": {
        "name": "讯飞星火",
        "base_url": "https://spark-api-open.xf-yun.com/v1",
        "models": ["generalv3.5", "4.0Ultra", "lite"],
        "key_url": "https://console.xfyun.cn/",
        "note": "用 APIKey:APISecret 形式的密钥",
    },
    "hunyuan": {
        "name": "腾讯混元",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "models": ["hunyuan-turbo", "hunyuan-pro", "hunyuan-standard"],
        "vision": ["hunyuan-vision"],
        "key_url": "https://console.cloud.tencent.com/hunyuan/api-key",
        "note": "需在腾讯云开通混元",
    },
    "ark": {
        "name": "豆包（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-lite-32k"],
        "vision": ["doubao-1.5-vision-pro-32k"],
        "key_url": "https://console.volcengine.com/ark",
        "note": "注意：模型名需填你的「接入点 ID」(ep-开头)",
    },
}

# 识图（多模态）推荐顺序：智谱 glm-4v-flash 免费，学生最容易拿到 key
VISION_ORDER = ["zhipu", "qwen", "moonshot", "hunyuan", "ark"]


def list_providers() -> list[dict]:
    """给前端的可选列表（不含任何密钥）。"""
    return [{"id": pid, **{k: v for k, v in p.items()}} for pid, p in PROVIDERS.items()]


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
