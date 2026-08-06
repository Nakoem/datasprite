"""
评测样本自动捕获脚本：把真实运行过的问数沉淀成候选评测样本

原理：meta.messages 里每条 user 问题之后的 assistant 消息带完整 sql/result，
本脚本把 (user问题 + 生成SQL) 配对，与 evaluations/questions.yaml 去重，
并在数仓上执行生成的 SQL 验证可运行性（语法 + 行数），产出「候选审核报告」。

自评陷阱原则：生成的 SQL 只是候选，不能直接当标准答案 —— 那等于系统拿自己的输出自评。
所以审核门禁是 AI 建议 + 独立 SQL 硬验证：
- `--review`：LLM 对每个候选判 promote / filter / defer + 理由 + 相似题 + 独立 expected_sql；
  promote 的候选必须把「独立 expected_sql」与「候选 SQL」都在数仓实跑、结果集对比一致
  （硬验证）才算数。任何 AI 异常/缺独立SQL/结果不一致 → 一律 defer（宁放过不误杀）。
- `--apply`：把「AI 建议 promote + 硬验证通过」的候选自动晋升进评测集，宝可 git diff 回退。

用法：
    uv run python app/scripts/sync_eval_questions.py
    uv run python app/scripts/sync_eval_questions.py --review       # 捕获 + AI 审核建议
    uv run python app/scripts/sync_eval_questions.py --apply        # 一键晋升（promote+硬验证）
    uv run python app/scripts/sync_eval_questions.py --apply-all    # 放宽硬验证门的逃生舱
    uv run python app/scripts/sync_eval_questions.py --no-verify    # 跳过 DW 验证，只出候选
    uv run python app/scripts/sync_eval_questions.py --no-ai        # 跳过 LLM，纯规则捕获
    uv run python app/scripts/sync_eval_questions.py --report docs/evaluations
"""

import argparse
import asyncio
import json
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
from app.scripts.eval_rows import rows_equal

DEFAULT_QUESTIONS = Path("evaluations/questions.yaml")
STATE_PATH = Path("docs/evaluations/ai-review-state.json")

# 任何 LLM 调用异常/非法输出的降级 verdict：defer（保留待人工）比 filter（永久丢弃）
# 更贴合「宁放过不误杀」——错过一个真候选的代价高于多留一个待人工候选。
LLM_FAIL_VERDICT = "defer"

_VERDICTS = ("promote", "filter", "defer")


def _norm(q: str) -> str:
    """问题文本归一化：去空白（含全角）、去句末标点，用于去重比对"""
    s = (q or "").strip().replace(" ", "").replace("　", "")
    return re.sub(r"[。？！？!；;，,]$", "", s)


def load_existing_questions(text: str) -> set[str]:
    """解析评测集文本，返回已收录问题的归一化集合，用于去重"""
    data = yaml.safe_load(text) or {}
    return {_norm(q.get("question", "")) for q in data.get("questions", [])}


def load_existing_qs(text: str) -> list[dict]:
    """解析评测集文本，返回 [{id, category, question}]，供 AI 审核做近重复比对"""
    data = yaml.safe_load(text) or {}
    return [
        {
            "id": q.get("id", ""),
            "category": q.get("category", ""),
            "question": q.get("question", ""),
        }
        for q in data.get("questions", [])
    ]


def _next_real_id(text: str) -> str:
    """扫现有 r## 编号，返回下一个可用 id（真实历史问题统一 r 系列）。

    兼容 yaml 列表项 `- id: r16` 与裸 `id: r16` 两种写法。
    """
    max_r = 0
    for line in text.splitlines():
        m = re.match(r"^\s*(?:-\s*)?id:\s*r(\d+)\s*$", line)
        if m:
            max_r = max(max_r, int(m.group(1)))
    return f"r{max_r + 1:02d}"


def append_questions(text: str, entries: list[dict], audit_note: str) -> str:
    """文本级追加新题，完全保留原文件注释/结构（项目无 ruamel，不能 yaml.dump 重写）。

    entries 每项含 id/category/question/expected_sql；可选 note 追加单条注释。
    缩进与现有格式一致：列表项 2 格、字段 4 格、块标量内容 6 格。
    """
    blocks = [f"# {audit_note}"] if audit_note else []
    for e in entries:
        sql = (e.get("expected_sql") or "").strip().rstrip(";")
        blocks.append(f"  - id: {e['id']}")
        blocks.append(f"    category: {e['category']}")
        blocks.append(f"    question: {e['question']}")
        if e.get("note"):
            blocks.append(f"    # {e['note']}")
        blocks.append("    expected_sql: |")
        blocks += [f"      {ln}" for ln in sql.splitlines()]
    sep = "" if text.endswith("\n") else "\n"
    return text + sep + "\n" + "\n".join(blocks) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    """先写临时文件再原子替换，避免写一半崩溃留下残缺 yaml"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ── AI 审核 state（幂等：同问题同时间只审一次，省 LLM 费用）──────────────


def _load_handled(path: Path = STATE_PATH) -> dict:
    """读取已审核候选索引；文件不存在/损坏返回空（幂等索引，坏了重建比崩掉好）。
    key 形如「归一化问题|asked_at」"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"handled": data.get("handled", {})}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"handled": {}}


def _save_handled(handled: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(handled, ensure_ascii=False, indent=2))


# ── AI 审核与硬验证 ──────────────────────────────────────────────────────


async def _hard_verify(
    dw_repo: DWMySQLRepository, candidate_sql: str, suggested_sql: str
) -> tuple[bool, str]:
    """独立 expected_sql 实跑 vs 候选 SQL 实跑 → rows_equal。只读 SELECT 可安全重复。

    这是防自评陷阱的核心：AI 说「该晋升」不算数，必须独立写法的标准 SQL 与系统
    候选 SQL 实跑结果一致，才证明问题真的可稳定作答。
    """
    try:
        expected_rows = await dw_repo.run(suggested_sql)
        actual_rows = await dw_repo.run(candidate_sql)
    except Exception as e:  # noqa: BLE001
        return False, f"实跑异常：{e}"
    if rows_equal(expected_rows, actual_rows):
        return True, f"结果集一致（{len(expected_rows)} 行）"
    return (
        False,
        f"独立SQL {len(expected_rows)} 行 vs 候选SQL {len(actual_rows)} 行结果集不一致",
    )


async def ai_review_candidate(
    candidate: dict,
    dw_session,
    existing_qs: list[dict],
    dw_repo: DWMySQLRepository,
) -> dict:
    """对单个候选做 AI 审核，返回完整审核记录（含硬验证修正后的最终 verdict）。

    verdict 语义：
      promote = AI 判 promote 且独立 SQL 硬验证通过（唯一可晋升类）
      filter  = AI 判近重复/无价值/SQL 答非所问（带 similar_ids）
      defer   = 拿不准/命中盲区/依赖上下文，或任何降级路径（AI 异常/非法输出/
                promote 缺独立SQL/硬验证失败）——绝不无硬验证地 promote
    """
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import PromptTemplate

    from app.agent.llm import llm
    from app.prompt.prompt_loader import load_prompt

    out = {
        "question": candidate["question"],
        "key": candidate["_key"],
        "asked_at": str(candidate["asked_at"]),
        "candidate_sql": candidate["sql"],
        "verdict": None,
        "reason": "",
        "similar_ids": [],
        "suggested_expected_sql": None,
        "hard_verified": False,
        "promote_blocked": False,
        "exec_ok": candidate.get("_exec_ok", False),
        "first_row": candidate.get("_first_row"),
        "error": None,
    }

    existing_block = yaml.dump(existing_qs, allow_unicode=True, sort_keys=False)
    try:
        chain = (
            PromptTemplate(
                template=load_prompt("review_eval_candidate"),
                input_variables=[
                    "question",
                    "candidate_sql",
                    "first_row_sample",
                    "existing_questions",
                ],
            )
            | llm
            | JsonOutputParser()
        )
        raw = await chain.ainvoke(
            {
                "question": candidate["question"],
                "candidate_sql": candidate["sql"],
                "first_row_sample": yaml.dump(
                    candidate.get("_first_row"), allow_unicode=True, sort_keys=False
                )
                if candidate.get("_first_row") is not None
                else "(候选 SQL 执行失败或无结果)",
                "existing_questions": existing_block,
            }
        )
    except Exception as e:  # noqa: BLE001
        # 宁放过不误杀：不晋升也不永久丢弃，降级为 defer 留待人工
        out["verdict"] = LLM_FAIL_VERDICT
        out["reason"] = f"AI 审核调用异常，降级为 defer：{e}"
        out["error"] = str(e)
        return out

    verdict = (raw.get("verdict") or "").strip().lower()
    out["reason"] = (raw.get("reason") or "").strip()
    out["similar_ids"] = raw.get("similar_ids") or []
    suggested = (raw.get("suggested_expected_sql") or "").strip().strip(";")

    if verdict not in _VERDICTS:
        out["verdict"] = "defer"
        out["reason"] = f"AI 返回非法 verdict={verdict!r}，保守 defer"
        return out

    if verdict == "promote":
        if not suggested:
            # AI 违反契约：promote 必须给独立 expected_sql → 无法硬验证 → 降级 defer
            out["verdict"] = "defer"
            out["reason"] = (out["reason"] or "") + (
                "（AI promote 但未提供独立 suggested_expected_sql，无法硬验证）"
            )
            return out
        out["suggested_expected_sql"] = suggested
        ok, detail = await _hard_verify(dw_repo, candidate["sql"], suggested)
        if ok:
            out["verdict"] = "promote"
            out["hard_verified"] = True
            out["reason"] = (out["reason"] or "") + f"｜硬验证：{detail}"
        else:
            # 独立 SQL 与候选 SQL 结果不一致 → 默认不能晋升，降 defer；
            # 但记录 promote_blocked，--apply-all 逃生舱可据此强制写入（带注释标记人工复核）
            out["verdict"] = "defer"
            out["promote_blocked"] = True
            out["reason"] = (out["reason"] or "") + f"（硬验证失败：{detail}）"
    else:
        out["verdict"] = verdict
    return out


async def _review_candidates(
    candidates: list[dict],
    existing_qs: list[dict],
    dw_session,
    dw_repo: DWMySQLRepository,
    handled: dict,
) -> list[dict]:
    """逐候选 AI 审核；命中 state 的复用上次判定（幂等 + 省 LLM 费用）"""
    reviews = []
    for cand in candidates:
        key = f"{cand['_key']}|{cand['asked_at']}"
        if key in handled["handled"]:
            prev = handled["handled"][key]
            review = {
                "question": cand["question"],
                "key": cand["_key"],
                "asked_at": str(cand["asked_at"]),
                "candidate_sql": cand["sql"],
                "verdict": prev.get("verdict"),
                "reason": prev.get("reason", "(上次已审核，复用)"),
                "similar_ids": prev.get("similar_ids", []),
                "suggested_expected_sql": prev.get("suggested_expected_sql"),
                "hard_verified": prev.get("hard_verified", False),
                "promote_blocked": prev.get("promote_blocked", False),
                "exec_ok": cand.get("_exec_ok", False),
                "first_row": cand.get("_first_row"),
                "error": prev.get("error"),
            }
            reviews.append(review)
            continue
        review = await ai_review_candidate(cand, dw_session, existing_qs, dw_repo)
        handled["handled"][key] = {
            "verdict": review["verdict"],
            "reason": review["reason"],
            "similar_ids": review["similar_ids"],
            "suggested_expected_sql": review["suggested_expected_sql"],
            "hard_verified": review["hard_verified"],
            "promote_blocked": review["promote_blocked"],
            "applied_at": datetime.now().isoformat(timespec="seconds"),
        }
        reviews.append(review)
    return reviews


# ── 晋升写入与报告 ───────────────────────────────────────────────────────


def _plan_promotions(
    reviews: list[dict], apply: bool, apply_all: bool
) -> tuple[list[dict], list[dict]]:
    """根据最终 verdict 规划晋升条目。返回 (晋升条目, 硬验证失败但被 apply-all 放行的)"""
    if not apply:
        return [], []
    promote = [r for r in reviews if r["verdict"] == "promote" and r["hard_verified"]]
    if apply_all:
        # 逃生舱：AI 判 promote 但硬验证失败（promote_blocked）→ 强制写入并打注释标记，
        # 人工复核后放行。缺独立 SQL 的（无物可写）不在其列。
        loose = [
            r
            for r in reviews
            if r.get("promote_blocked") and r.get("suggested_expected_sql")
        ]
    else:
        loose = []
    return promote, loose


def _entries_for(
    promote: list[dict], loose: list[dict], existing_text: str
) -> list[dict]:
    """构造追加进 questions.yaml 的条目（真实问题统一 r## 递增）"""
    entries = []
    n = int(_next_real_id(existing_text).lstrip("r"))
    for r in promote:
        entries.append(
            {
                "id": f"r{n:02d}",
                "category": "真实历史问题",
                "question": r["question"],
                "expected_sql": r["suggested_expected_sql"].strip().rstrip(";"),
            }
        )
        n += 1
    for r in loose:
        entries.append(
            {
                "id": f"r{n:02d}",
                "category": "真实历史问题",
                "question": r["question"],
                "expected_sql": r["suggested_expected_sql"].strip().rstrip(";"),
                "note": (
                    f"AI promote 但独立SQL结果集不一致（{datetime.now().strftime('%Y-%m-%d')}，"
                    "人工复核后放行）"
                ),
            }
        )
        n += 1
    return entries


def _write_questions(
    existing_text: str, entries: list[dict], questions_path: Path
) -> bool:
    """文本级追加 + yaml 自检 + 原子写。自检失败（题数不符）则不落盘。"""
    if not entries:
        return False
    original_count = len(yaml.safe_load(existing_text).get("questions", []))
    audit_note = (
        f"以下 {len(entries)} 条由 sync_eval_questions.py --apply 从真实运行沉淀、"
        f"AI审核+独立SQL硬验证晋升而来（{datetime.now().strftime('%Y-%m-%d')}）"
    )
    new_text = append_questions(existing_text, entries, audit_note)
    parsed = yaml.safe_load(new_text)
    if not isinstance(parsed, dict) or len(parsed.get("questions", [])) != (
        original_count + len(entries)
    ):
        print(f"[apply] YAML 自检失败，拒绝写入 {questions_path}")
        return False
    _atomic_write(questions_path, new_text)
    return True


async def _run_inner(
    meta_session,
    dw_session,
    questions_path: Path,
    report_dir: Path,
    verify: bool,
    review: bool,
    apply: bool,
    apply_all: bool,
) -> int:
    """扫描消息配对 → 去重 → 验证 → (AI 审核) → (晋升入库) → 写报告。返回新候选数。"""
    dw_repo = DWMySQLRepository(dw_session)
    existing_text = questions_path.read_text(encoding="utf-8")
    existing_set = load_existing_questions(existing_text)
    existing_qs = load_existing_qs(existing_text)

    pairs = await fetch_pairs(meta_session)

    # 内部去重（同文本问题只留一条，取最早提问）
    seen_text: set[str] = set()
    candidates = []
    for p in pairs:
        key = _norm(p["question"])
        if key in seen_text:
            continue
        seen_text.add(key)
        p["_existing"] = key in existing_set
        p["_key"] = key
        candidates.append(p)

    new_cands = [p for p in candidates if not p["_existing"]]
    already = [p for p in candidates if p["_existing"]]

    # 数仓实跑验证可运行性 + 缓存首行样例（供 AI 审核复用，避免重跑）
    if verify:
        for p in new_cands:
            try:
                rows = await dw_repo.run(p["sql"])
                p["_exec_ok"] = True
                p["_row_count"] = len(rows)
                p["_first_row"] = rows[0] if rows else None
            except Exception as e:  # noqa: BLE001
                p["_exec_ok"] = False
                p["_row_count"] = 0
                p["_first_row"] = None
                p["_error"] = str(e)

    # AI 审核建议（review/apply 时）
    reviews: list[dict] = []
    if (review or apply) and new_cands:
        handled = _load_handled()
        reviews = await _review_candidates(
            new_cands, existing_qs, dw_session, dw_repo, handled
        )
        _save_handled(handled)

    # 晋升入库
    promote, loose = _plan_promotions(reviews, apply, apply_all)
    entries = _entries_for(promote, loose, existing_text)
    applied = _write_questions(existing_text, entries, questions_path)

    # 报告落盘（只有新候选才落盘，避免每次评测都刷一个空报告）
    if new_cands:
        report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        _write_review_report(report_dir / f"review-{ts}.md", new_cands, reviews, verify, already)
        if reviews:
            (report_dir / f"ai-review-{ts}.json").write_text(
                json.dumps(reviews, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        if apply:
            _write_apply_report(report_dir / f"apply-{ts}.md", reviews, promote, loose)

    # 控制台 ASCII/中文摘要（Windows GBK 打不了 emoji）
    print(
        f"配对 {len(candidates)} 条：新候选 {len(new_cands)}，"
        f"已在评测集 {len(already)}"
    )
    if reviews:
        counts = {v: sum(1 for r in reviews if r["verdict"] == v) for v in _VERDICTS}
        print(f"AI 审核：promote {counts['promote']} / filter {counts['filter']} / defer {counts['defer']}")
    if applied:
        ids = ", ".join(e["id"] for e in entries)
        print(f"晋升写入：{len(entries)} 条（{ids}）→ {questions_path}（git diff 可回退）")
    if apply and not applied:
        print("[apply] 无晋升（promote+硬验证为空），questions.yaml 未改动")
    if apply and entries and not all(
        r["hard_verified"] for r in reviews if r["verdict"] == "promote"
    ) and apply_all:
        print("[apply-all] 含硬验证未通过但被强制写入的条目，请人工复核")
    if new_cands:
        print(f"候选审核报告：{report_dir / f'review-{ts}.md'}")
    return len(new_cands)


def _write_review_report(
    path: Path, new_cands: list[dict], reviews: list[dict], verify: bool, already: list[dict]
) -> None:
    """候选审核报告：保留原有可运行性信息，每条新候选附 AI 判定"""
    out = [
        "# 评测样本候选 — 真实运行沉淀",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 消息源：meta.messages（user 问题 + assistant 生成 SQL 配对）",
        f"- **新候选（待审核晋升）：{len(new_cands)}**",
    ]
    if reviews:
        counts = {v: sum(1 for r in reviews if r["verdict"] == v) for v in _VERDICTS}
        out += [
            "- AI 审核汇总：",
            f"  - promote（建议晋升）：{counts['promote']}",
            f"  - filter（建议过滤）：{counts['filter']}",
            f"  - defer（暂缓/待人工）：{counts['defer']}",
        ]
    out += [""]

    if new_cands:
        out += ["## 新候选（待审核晋升）", ""]
        for idx, p in enumerate(new_cands, 1):
            out.append(f"### {idx:02d}. {p['question']}")
            out.append("")
            out.append(f"- 提问时间：{p['asked_at']}")
            out.append(f"- 问题key：{p['_key']}")
            if verify:
                if p.get("_exec_ok"):
                    out.append(
                        f"- 生成SQL可运行性：✅ 执行成功，{p.get('_row_count', 0)} 行"
                    )
                    if p.get("_first_row"):
                        out.append(f"- 首行样例：`{p['_first_row']}`")
                else:
                    out.append(f"- 生成SQL可运行性：❌ {p.get('_error')}")
            review = next((r for r in reviews if r["key"] == p["_key"]), None)
            if review:
                mark = {
                    "promote": "✅ 建议晋升",
                    "filter": "⏭ 建议过滤",
                    "defer": "⏸ 暂缓",
                }.get(review["verdict"], review["verdict"])
                out.append(f"- AI 审核：{mark}")
                if review.get("similar_ids"):
                    out.append(f"- 近重复/相似题：{review['similar_ids']}")
                if review.get("reason"):
                    out.append(f"- 理由：{review['reason']}")
                if review.get("suggested_expected_sql"):
                    out.append("- 建议 expected_sql（独立写法，已硬验证）：")
                    out += ["```sql", review["suggested_expected_sql"], "```"]
                out.append("")
            else:
                out.append("")
                out.append(
                    "> 审核：该 SQL 是否真的答对了问题？对则写 expected_sql "
                    "（可直接用验证后的 SQL 或独立写法）晋升进评测集；"
                    "近重复/无价值则跳过。"
                )
                out.append("")
            out.append("")

    already_lines = [f"- {p['question']}" for p in already]
    out += ["## 已在评测集（自动跳过）", ""]
    out += already_lines or ["（本批配对中无已在评测集的问题）", ""]
    path.write_text("\n".join(out), encoding="utf-8")


def _write_apply_report(
    path: Path, reviews: list[dict], promote: list[dict], loose: list[dict]
) -> None:
    """晋升审计报告：每条候选的 verdict/reason/similar_ids/硬验证/入库 SQL"""
    out = [
        "# 评测候选晋升审计",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 规则：仅 AI 建议 promote 且独立 SQL 硬验证通过的写入评测集",
        f"- 晋升：{len(promote)} 条",
        f"- 强制放行（apply-all，硬验证未过）：{len(loose)} 条",
        f"- 未晋升：{sum(1 for r in reviews if r['verdict'] != 'promote')} 条",
        "",
    ]
    for group, label in ((promote, "晋升"), (loose, "强制放行")):
        if not group:
            continue
        out += [f"## {label}", ""]
        for r in group:
            out += [f"### {r['key']}｜{r['question']}", ""]
            if r.get("reason"):
                out.append(f"- 理由：{r['reason']}")
            if r.get("similar_ids"):
                out.append(f"- 近重复/相似题：{r['similar_ids']}")
            out += ["```sql", r.get("suggested_expected_sql", ""), "```", ""]
    skipped = [r for r in reviews if r["verdict"] != "promote"]
    if skipped:
        out += ["## 未晋升（跳过）", ""]
        for r in skipped:
            mark = {"filter": "过滤", "defer": "暂缓"}.get(r["verdict"], r["verdict"])
            out.append(f"- [{mark}] {r['question']}")
            if r.get("reason"):
                out.append(f"  - {r['reason']}")
            if r.get("similar_ids"):
                out.append(f"  - 相似题：{r['similar_ids']}")
            out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


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
    verify: bool = True,
    review: bool = False,
    apply: bool = False,
    apply_all: bool = False,
    sessions: tuple | None = None,
) -> int:
    """扫描配对 → 去重 → 验证 → (AI审核) → (晋升入库)，返回新候选数。

    sessions=(meta_session, dw_session) 供外部（如 run_evaluation）注入既有会话，
    避免重复 init/close 客户端；None 时自行管理生命周期。
    """
    if sessions is not None:
        meta_session, dw_session = sessions
        return await _run_inner(
            meta_session,
            dw_session,
            questions_path,
            report_dir,
            verify,
            review,
            apply,
            apply_all,
        )

    meta_mysql_client_manager.init()
    # dw 引擎是惰性创建（不真正连库），无条件 init 保证 --no-verify 时 session 工厂可用
    dw_mysql_client_manager.init()
    try:
        async with (
            meta_mysql_client_manager.session_factory() as meta_session,
            dw_mysql_client_manager.session_factory() as dw_session,
        ):
            return await _run_inner(
                meta_session,
                dw_session,
                questions_path,
                report_dir,
                verify,
                review,
                apply,
                apply_all,
            )
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
    parser.add_argument(
        "--review",
        action="store_true",
        help="捕获 + AI 审核建议（promote/filter/defer + 独立SQL硬验证），不改评测集",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="一键晋升：AI 建议 promote 且硬验证通过的写进评测集（git diff 可回退）",
    )
    parser.add_argument(
        "--apply-all",
        action="store_true",
        help="同 --apply，但硬验证失败的也强制写入并打注释（人工复核逃生舱）",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="跳过 LLM 审核，纯规则捕获（现有行为）",
    )
    args = parser.parse_args()

    if args.apply or args.apply_all:
        args.review = True  # 晋升隐含审核
    review_mode = args.review and not args.no_ai
    if (args.apply or args.apply_all) and args.no_ai:
        print("警告：--no-ai 时无 AI 审核，--apply 无法晋升（promote 依赖 AI 判定）")

    asyncio.run(
        run(
            args.questions,
            args.report,
            verify=not args.no_verify,
            review=review_mode,
            apply=args.apply,
            apply_all=args.apply_all,
        )
    )
