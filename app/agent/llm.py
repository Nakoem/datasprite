"""
电商问数 Agent 使用的大模型实例

集中初始化一个 OpenAI 兼容的 Chat Model，供节点或本地测试直接复用。

容错策略：
- request_timeout 防止请求挂死
- max_retries OpenAI 客户端级自动重试（指数退避）
- fallback_model 主模型全部失败后降级到备用模型
"""

from langchain.chat_models import init_chat_model

from app.conf.app_config import app_config

_TIMEOUT = getattr(app_config.llm, "request_timeout", 60)
_MAX_RETRIES = getattr(app_config.llm, "max_retries", 2)


def _make_llm(model: str) -> object:
    """创建一个 LLM 实例，统一 timeout + retry 配置"""
    return init_chat_model(
        model=model,
        model_provider="openai",
        base_url=app_config.llm.base_url,
        api_key=app_config.llm.api_key,
        temperature=0,
        max_retries=_MAX_RETRIES,
        request_timeout=_TIMEOUT,
    )


# 主模型
_primary = _make_llm(app_config.llm.model_name)

# 降级链：主模型失败 → 备用模型（如果配置了）
fallback_model = getattr(app_config.llm, "fallback_model", None)
if fallback_model and fallback_model != app_config.llm.model_name:
    fallback_llm = _make_llm(fallback_model)
    llm = _primary.with_fallbacks([fallback_llm])
else:
    llm = _primary

if __name__ == "__main__":
    # 本地快速验证 LLM 配置是否能正常调用
    print(llm.invoke("你好，你是什么模型").content)
