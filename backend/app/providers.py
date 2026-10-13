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
        "key_url": "https://bailian.console.aliyun.com/",
        "note": "需在阿里云百炼开通并创建 API-KEY",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-flash", "glm-4-air", "glm-4-plus"],
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "note": "glm-4-flash 有免费额度",
    },
    "moonshot": {
        "name": "Kimi（月之暗面）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
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
        "key_url": "https://console.cloud.tencent.com/hunyuan/api-key",
        "note": "需在腾讯云开通混元",
    },
    "ark": {
        "name": "豆包（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-32k", "doubao-lite-32k"],
        "key_url": "https://console.volcengine.com/ark",
        "note": "注意：模型名需填你的「接入点 ID」(ep-开头)",
    },
}


def list_providers() -> list[dict]:
    """给前端的可选列表（不含任何密钥）。"""
    return [{"id": pid, **{k: v for k, v in p.items()}} for pid, p in PROVIDERS.items()]


def resolve(provider: str, model: str = "") -> tuple[str, str, str]:
    """返回 (base_url, model, display_name)。provider 不在表内则回退 deepseek。"""
    p = PROVIDERS.get(provider) or PROVIDERS["deepseek"]
    use_model = model or p["models"][0]
    return p["base_url"], use_model, p["name"]
