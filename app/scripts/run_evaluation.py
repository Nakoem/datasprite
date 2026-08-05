"""
评测体系批跑脚本

加载 evaluations/questions.yaml 问题集，逐题跑一遍完整 LangGraph 问数链路，
把智能体生成的 SQL 在数仓 DW 上真实执行，与每条 expected_sql 的执行结果做
「结果集对比」判定正确性（不做 SQL 字面对比，更贴近业务口径）。

用法：
    uv run python app/scripts/run_evaluation.py
    uv run python app/scripts/run_evaluation.py --category 维度筛选   # 只跑某一类
    uv run python app/scripts/run_evaluation.py --limit 3            # 只跑前 3 题（冒烟）
    uv run python app/scripts/run_evaluation.py --output docs/evaluations
"""

import argparse
import asyncio
import json
import sys
import time
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# 脚本以文件方式运行（python app/scripts/xxx.py）时 sys.path[0] 是脚本目录，
# 不会带上项目根，这里显式把项目根插进来，保证 `import app` 可用。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml

from app.agent.context import DataAgentContext
from app.agent.graph import graph
from app.agent.state import DataAgentState
from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def load_questions(path: Path) -> list[dict]:
    """加载问题集 YAML，返回 [{id, category, question, expected_sql}, ...]"""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions", [])
    for item in questions:
        item["expected_sql"] = item["expected_sql"].strip().rstrip(";")
    return questions


# 链路内 LLM 瞬时连接失败（网络抖动）时的整题重试上限与等待基数。
# 实测遇到 DashScope 连接瞬时中断 6 秒，客户端级 max_retries 也会全撞上，
# 评测不该因此误杀一道题 —— 但只对"连接/超时类"瞬时错误重试，逻辑错误不重试。
MAX_GRAPH_RETRIES = 2
RETRY_BACKOFF = 5  # 秒，按尝试次数递增

# 瞬时错误特征：命中说明是网络/服务端抖动，重试通常能恢复
_TRANSIENT_MARKERS = (
    "connection error",
    "connectionerror",
    "connect timeout",
    "apitimeouterror",
    "apiconnectionerror",
    "read timeout",
    "service unavailable",
    "temporarily unavailable",
    "429",
    "502",
    "503",
)


def _is_transient_error(msg: str) -> bool:
    m = (msg or "").lower()
    return any(marker in m for marker in _TRANSIENT_MARKERS)


def _normalize_value(v):
    """数值统一取整，避免浮点 / Decimal 精度差异误判不一致"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        return round(float(v), 6)
    return v


def _canonical_rows(rows: list[dict]) -> list:
    """每行只取排序后的值元组，整张表再按行排序。

    刻意忽略列名：智能体生成的 SQL 别名可能与期望 SQL 不同（如 total_amount vs
    销售总额），但数值一致就算答对；列名不一致不应误判。列数不同仍会判不一致。
    """
    out = []
    for row in rows or []:
        # key=repr 提供全类型稳定全序：None / 数字 / 字符串混排不抛 TypeError
        values = tuple(sorted((_normalize_value(v) for v in row.values()), key=repr))
        out.append(values)
    return sorted(out)


def rows_equal(expected: list[dict], actual: list[dict]) -> bool:
    """结果集对比：期望结果与生成 SQL 结果是否一致"""
    return _canonical_rows(expected) == _canonical_rows(actual)


async def _run_graph(query: str, context: DataAgentContext, timeout: int) -> dict:
    """跑完整问数链路，返回 final state；异常时返回 {"_error": ...}。

    注意用 _error 前缀做内部哨兵，因为 DataAgentState 本身就有一个 error 字段
    （SQL 校验错误），撞名会让正常结束也被误判为链路异常。
    """
    state = DataAgentState(query=query, correct_retry_count=0)
    final = None
    try:
        async def _astream():
            nonlocal final
            async for chunk in graph.astream(
                input=state, context=context, stream_mode="values"
            ):
                final = chunk
        await asyncio.wait_for(_astream(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"_error": f"链路执行超时（{timeout}秒）"}
    except Exception as e:  # noqa: BLE001 — 评测要吞掉单题异常，不能中断整轮
        return {"_error": str(e)}
    return final or {}


async def evaluate_one(
    item: dict, context: DataAgentContext, dw_repo: DWMySQLRepository, timeout: int
) -> dict:
    """评测单题：先执行期望 SQL，再跑链路生成 SQL 并对比结果集"""
    result = {
        "id": item["id"],
        "category": item.get("category", ""),
        "question": item["question"],
        "pass": False,
        "reason": "",
        "generated_sql": None,
        "error": None,
        "expected_rows": None,
        "actual_rows": None,
        "elapsed": 0.0,
        "retries": 0,
    }
    start = time.perf_counter()

    try:
        expected_rows = await dw_repo.run(item["expected_sql"])
    except Exception as e:  # noqa: BLE001
        result["error"] = f"期望SQL执行失败：{e}"
        result["reason"] = "期望SQL执行失败"
        result["elapsed"] = round(time.perf_counter() - start, 2)
        return result
    result["expected_rows"] = expected_rows

    # 链路执行带瞬时错误重试：只重试连接/超时类抖动，逻辑错误直接判失败
    final_state = {}
    for attempt in range(MAX_GRAPH_RETRIES + 1):
        final_state = await _run_graph(item["question"], context, timeout)
        err = final_state.get("_error")
        if err and attempt < MAX_GRAPH_RETRIES and _is_transient_error(err):
            result["retries"] = attempt + 1
            await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
            continue
        break
    result["elapsed"] = round(time.perf_counter() - start, 2)

    if "_error" in final_state:
        result["error"] = final_state["_error"]
        result["reason"] = "链路执行异常"
        return result

    sql = final_state.get("sql")
    result["generated_sql"] = sql
    if not sql:
        result["reason"] = "澄清追问/未生成SQL"
        return result

    try:
        actual_rows = await dw_repo.run(sql)
    except Exception as e:  # noqa: BLE001
        result["error"] = f"生成SQL执行失败：{e}"
        result["reason"] = "生成SQL执行失败"
        return result
    result["actual_rows"] = actual_rows

    if rows_equal(expected_rows, actual_rows):
        result["pass"] = True
        result["reason"] = "结果集一致"
    else:
        result["reason"] = "结果集不一致"
    return result


def _build_report(results: list[dict], started_at: str) -> str:
    """把评测结果渲染成 Markdown 报告文本"""
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    acc = passed / total if total else 0.0

    cats: OrderedDict[str, list[dict]] = OrderedDict()
    for r in results:
        cats.setdefault(r["category"], []).append(r)

    lines = [
        "# DataSprite 问数评测报告",
        "",
        f"- 评测时间：{started_at}",
        f"- 问题总数：{total}",
        f"- 通过：{passed}",
        f"- 失败：{total - passed}",
        f"- **正确率：{acc:.1%}**",
        "",
        "## 按类别统计",
        "",
        "| 类别 | 通过/总数 | 正确率 |",
        "|------|----------|--------|",
    ]
    for cat, items in cats.items():
        cp = sum(1 for r in items if r["pass"])
        lines.append(f"| {cat} | {cp}/{len(items)} | {cp / len(items):.0%} |")

    lines += ["", "## 明细", "", "| ID | 问题 | 类别 | 结果 | 原因 |", "|----|------|------|------|------|"]
    for r in results:
        mark = "✅" if r["pass"] else "❌"
        retry = f"（重试{r['retries']}次）" if r.get("retries") else ""
        lines.append(f"| {r['id']} | {r['question']} | {r['category']} | {mark} | {r['reason']}{retry} |")

    fails = [r for r in results if not r["pass"]]
    if fails:
        lines += ["", "## 失败详情", ""]
        for r in fails:
            lines += [f"### {r['id']} {r['question']}", ""]
            lines.append(f"- 类别：{r['category']}")
            lines.append(f"- 原因：{r['reason']}")
            if r.get("generated_sql"):
                lines += ["```sql", r["generated_sql"], "```"]
            if r.get("error"):
                lines.append(f"- 错误：{r['error']}")
            lines.append("")

    return "\n".join(lines)


async def run(
    questions_path: Path,
    output_dir: Path,
    category: str | None = None,
    limit: int | None = None,
    timeout: int = 300,
) -> int:
    """初始化依赖，逐题评测，落盘报告，返回通过题数"""
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()

    questions = load_questions(questions_path)
    if category:
        questions = [q for q in questions if q.get("category") == category]
    if limit:
        questions = questions[:limit]
    if not questions:
        print("没有匹配的问题，请检查 --category / 问题集文件")
        await _close_clients()
        return 0

    try:
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            dw_repo = DWMySQLRepository(dw_session)
            context = DataAgentContext(
                column_qdrant_repository=ColumnQdrantRepository(qdrant_client_manager.client),
                embedding_client=embedding_client_manager.client,
                metric_qdrant_repository=MetricQdrantRepository(qdrant_client_manager.client),
                value_es_repository=ValueESRepository(es_client_manager.client),
                meta_mysql_repository=MetaMySQLRepository(meta_session),
                dw_mysql_repository=dw_repo,
            )

            results = []
            total = len(questions)
            for idx, item in enumerate(questions, start=1):
                r = await evaluate_one(item, context, dw_repo, timeout)
                results.append(r)
                # 控制台用 ASCII 标记（Windows GBK 编码无法打印 ✅/❌），报告文件里才用 emoji
                mark = "PASS" if r["pass"] else "FAIL"
                retry = f"（重试{r['retries']}次）" if r.get("retries") else ""
                print(
                    f"[{idx}/{total}] {r['id']} {mark} {r['reason']}{retry}"
                    f"（{r['elapsed']}s）| {r['question']}"
                )

            started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            md_path = output_dir / f"evaluation-{ts}.md"
            md_path.write_text(_build_report(results, started_at), encoding="utf-8")
            json_path = output_dir / f"evaluation-{ts}.json"
            json_path.write_text(
                json.dumps(results, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            passed = sum(1 for r in results if r["pass"])
            print(f"\n评测完成：{passed}/{total} 通过，正确率 {passed / total:.1%}")
            print(f"报告：{md_path}")
            print(f"数据：{json_path}")
            return passed
    finally:
        await _close_clients()


async def _close_clients():
    """关闭显式创建的异步客户端，避免本地跑批时连接资源悬挂"""
    await meta_mysql_client_manager.close()
    await dw_mysql_client_manager.close()
    await qdrant_client_manager.close()
    await embedding_client_manager.close()
    await es_client_manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataSprite 问数评测批跑")
    parser.add_argument(
        "-q", "--questions", type=Path,
        default=Path("evaluations/questions.yaml"),
        help="问题集 YAML 路径",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("docs/evaluations"),
        help="报告输出目录",
    )
    parser.add_argument("--category", type=str, default=None, help="只跑指定类别")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（冒烟）")
    parser.add_argument(
        "--timeout", type=int, default=300, help="单题链路执行超时（秒），默认 300"
    )
    args = parser.parse_args()

    asyncio.run(run(args.questions, args.output, args.category, args.limit, args.timeout))
