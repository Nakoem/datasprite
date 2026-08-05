"""
评测样本自动捕获脚本：把真实运行过的问数沉淀成候选评测样本

原理：meta.messages 里每条 user 问题之后的 assistant 消息带完整 sql/result，
本脚本把 (user问题 + 生成SQL) 配对，与 evaluations/questions.yaml 去重，
并在数仓上执行生成的 SQL 验证可运行性（语法 + 行数），产出「候选审核报告」。

注意：生成的 SQL 只是候选，不能直接当标准答案 —— 那等于系统拿自己的输出自评。
必须经人工/AI 审核（在 MySQL 实跑确认该 SQL 确实答对了问题）后，
才写 expected_sql 晋升进评测集。

用法：
    uv run python app/scripts/sync_eval_questions.py
    uv run python app/scripts/sync_eval_questions.py --report docs/evaluations
    uv run python app/scripts/sync_eval_questions.py --no-verify   # 跳过 DW 验证，只出候选
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# 脚本以文件方式运行（python app/scripts/xxx.py）时 sys.path[0] 是脚本目录，
# 不会带上项目根，这里显式把项目根插进来，保证 `import app` 可用。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml
from sqlalchemy import text

from app.clients.mysql_client_manager import (
    dw_mysql_client_manager,
    meta_mysql_client_manager,
)
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

DEFAULT_QUESTIONS = Path("evaluations/questions.yaml")


def _norm(q: str) -> str:
    """问题文本归一化：去空白（含全角）、去句末标点，用于去重比对"""
    s = (q or "").strip().replace(" ", "").replace("　", "")
    return re.sub(r"[。？！？!；;，,]$", "", s)


def load_existing_questions(path: Path) -> set[str]:
    """读取评测集里已收录的问题（归一化后），用于去重"""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {_norm(q.get("question", "")) for q in data.get("questions", [])}


async def fetch_pairs(session) -> list[dict]:
    """把每条 user 问题与同会话紧随其后的 assistant 消息配对，取生成的 SQL"""
    res = await session.execute(
        text(
            "SELECT id, conversation_id, role, content, `sql`, created_at "
            "FROM messages ORDER BY conversation_id, id"
        )
    )
    rows = res.fetchall()
    pairs = []
    for i, row in enumerate(rows):
        if row.role != "user":
            continue
        asst = None
        for j in range(i + 1, len(rows)):
            if rows[j].conversation_id != row.conversation_id:
                break
            if rows[j].role == "assistant" and rows[j].sql:
                asst = rows[j]
                break
        if asst is not None:
            pairs.append(
                {
                    "question": row.content,
                    "sql": asst.sql,
                    "asked_at": str(row.created_at),
                }
            )
    return pairs


async def run(
    questions_path: Path,
    report_dir: Path,
    verify: bool,
) -> int:
    """扫描消息配对 → 去重 → 验证 → 写候选审核报告，返回候选数"""
    meta_mysql_client_manager.init()
    # dw 引擎是惰性创建（不真正连库），无条件 init 保证 --no-verify 时 session 工厂可用
    dw_mysql_client_manager.init()

    try:
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            dw_repo = DWMySQLRepository(dw_session)
            existing = load_existing_questions(questions_path)
            pairs = await fetch_pairs(meta_session)

            # 内部去重（同文本问题只留一条，取最早提问）
            seen_text: set[str] = set()
            candidates = []
            for p in pairs:
                key = _norm(p["question"])
                if key in seen_text:
                    continue
                seen_text.add(key)
                p["_existing"] = key in existing
                p["_key"] = key
                candidates.append(p)

            new_cands = [p for p in candidates if not p["_existing"]]
            already = [p for p in candidates if p["_existing"]]

            out = [
                "# 评测样本候选 — 真实运行沉淀",
                "",
                f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "- 消息源：meta.messages（user 问题 + assistant 生成 SQL 配对）",
                f"- 配对总数：{len(candidates)}",
                f"- **新候选（待审核晋升）：{len(new_cands)}**",
                f"- 已在评测集（自动跳过）：{len(already)}",
                "",
            ]

            if new_cands:
                out += ["## 新候选（待审核晋升）", ""]
                for idx, p in enumerate(new_cands, 1):
                    out.append(f"### {idx:02d}. {p['question']}")
                    out.append("")
                    out.append(f"- 提问时间：{p['asked_at']}")
                    out.append(f"- 问题key：{p['_key']}")
                    if verify:
                        try:
                            rows = await dw_repo.run(p["sql"])
                            out.append(
                                f"- 生成SQL可运行性：✅ 执行成功，{len(rows)} 行"
                            )
                            if rows:
                                out.append(f"- 首行样例：`{rows[0]}`")
                        except Exception as e:  # noqa: BLE001
                            out.append(f"- 生成SQL可运行性：❌ {e}")
                    out.append("- 生成SQL：")
                    out += ["```sql", p["sql"], "```"]
                    out.append("")
                    out.append(
                        "> 审核：该 SQL 是否真的答对了问题？对则写 expected_sql "
                        "（可直接用验证后的 SQL 或独立写法）晋升进评测集；"
                        "近重复/无价值则跳过。"
                    )
                    out.append("")

            if already:
                out += ["## 已在评测集（自动跳过）", ""]
                for p in already:
                    out.append(f"- {p['question']}")

            report_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = report_dir / f"review-{ts}.md"
            path.write_text("\n".join(out), encoding="utf-8")

            # 控制台用 ASCII 摘要（Windows GBK 无法打印 emoji）
            print(
                f"配对 {len(candidates)} 条：新候选 {len(new_cands)}，"
                f"已在评测集 {len(already)}"
            )
            print(f"候选审核报告：{path}")
            return len(new_cands)
    finally:
        await meta_mysql_client_manager.close()
        await dw_mysql_client_manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DataSprite 评测样本自动捕获")
    parser.add_argument(
        "-q",
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
        help="评测集问题 YAML 路径",
    )
    parser.add_argument(
        "-r",
        "--report",
        type=Path,
        default=Path("docs/evaluations"),
        help="候选审核报告输出目录",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="跳过在数仓执行生成 SQL 的验证（只出候选清单）",
    )
    args = parser.parse_args()

    import asyncio

    asyncio.run(run(args.questions, args.report, verify=not args.no_verify))
