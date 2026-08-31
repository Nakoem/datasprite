"""
LLM Token 计量器

收集一次问数全链路上所有 LLM 调用的 token 消耗（input/output/total），
并按 LangGraph 节点分桶，用于成本核算与大头定位（如 generate_sql / correct_sql）。

用法：挂在 astream 的 config.callbacks 上，LangGraph 会自动把回调下传给
图内所有 LLM 调用（节点配置中的 callbacks 由父 run 传播给子 run）：

    meter = TokenMeter()  # ⚠️ 必须每请求 new 一个，禁止全局单例（并发串账）
    astream_config["callbacks"] = [meter]
    ...
    meter.summary()  # {"total": ..., "input": ..., "output": ..., "by_node": {...}}

实现细节：
- 节点名从 on_llm_start 的 metadata["langgraph_node"] 取（LangGraph 自动注入），
  on_llm_end 的 metadata 为 None，所以用 run_id 在两次回调间配对。
- 经实测（langchain-openai 1.1.12 + qwen3.7-max）：AIMessage.usage_metadata 常为
  None，token 数在 response.llm_output["token_usage"]（OpenAI 兼容 schema：
  prompt_tokens / completion_tokens / total_tokens），本类做两端兼容。
"""

from langchain_core.callbacks import BaseCallbackHandler

# metadata 缺失时的兜底桶（正常情况不会出现）
_OTHER = "other"


class TokenMeter(BaseCallbackHandler):
    """一次请求的 LLM token 计量器（非线程安全，请求内串行使用）"""

    def __init__(self):
        # run_id -> 节点名，on_llm_start 记录、on_llm_end 消费
        self._run_nodes: dict[str, str] = {}
        # 节点名 -> {input, output, total}
        self._per_node: dict[str, dict[str, int]] = {}

    def on_llm_start(
        self,
        serialized,
        prompts,
        *,
        run_id,
        parent_run_id=None,
        tags=None,
        metadata=None,
        **kwargs,
    ):
        node = (metadata or {}).get("langgraph_node") or _OTHER
        self._run_nodes[run_id] = node

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        # 调用失败没有 on_llm_end，清理 on_llm_start 登记的映射，避免残留
        self._run_nodes.pop(run_id, None)

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        usage = self._extract_token_usage(response)
        if usage is None:
            return
        input_tokens, output_tokens, total_tokens = usage
        node = self._run_nodes.pop(run_id, _OTHER)
        bucket = self._per_node.setdefault(node, {"input": 0, "output": 0, "total": 0})
        bucket["input"] += input_tokens
        bucket["output"] += output_tokens
        bucket["total"] += total_tokens

    @staticmethod
    def _extract_token_usage(response) -> tuple[int, int, int] | None:
        """从回调 response 里提取 (input, output, total)，取不到返回 None。

        优先 llm_output["token_usage"]，兼容 langchain 标准 usage_metadata。
        """
        llm_output = getattr(response, "llm_output", None)
        if isinstance(llm_output, dict):
            usage = llm_output.get("token_usage")
            if isinstance(usage, dict):
                return (
                    usage.get("prompt_tokens") or 0,
                    usage.get("completion_tokens") or 0,
                    usage.get("total_tokens") or 0,
                )

        usage_metadata = getattr(response, "usage_metadata", None)
        if isinstance(usage_metadata, dict):
            return (
                usage_metadata.get("input_tokens") or 0,
                usage_metadata.get("output_tokens") or 0,
                usage_metadata.get("total_tokens") or 0,
            )
        return None

    def summary(self) -> dict:
        """汇总本次请求的 token 消耗，by_node 按 total 降序（大头在前）"""
        total = {"input": 0, "output": 0, "total": 0}
        for bucket in self._per_node.values():
            total["input"] += bucket["input"]
            total["output"] += bucket["output"]
            total["total"] += bucket["total"]
        by_node = {
            node: bucket["total"]
            for node, bucket in sorted(
                self._per_node.items(), key=lambda kv: kv[1]["total"], reverse=True
            )
        }
        return {
            "total": total["total"],
            "input": total["input"],
            "output": total["output"],
            "by_node": by_node,
        }
