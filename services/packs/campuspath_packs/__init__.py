"""International Student Context Pack —— vendored（B1，2026-08-02）。

出处：github.com/JiangXiaohui-Christina/hkust-google-ai-hackathon
（commit ef6a2f2242bdb66ded423b341e5c414b3e7d3863，context-packs/international-student，
Pack 版本 0.1.0，队友交付）。`international_student/` 目录整体原样搬入，
**不改动求值逻辑**——上游修订时整目录替换并更新本注释的 commit。

设计契合点（也是不改它的理由）：
- 确定性求值、零 LLM（"does not infer policy, call an LLM"）；
- 缺失/过期/冲突/未复核 一律 needs_confirmation（与我们的 §16.1 四态同源）；
- 数据分层 base / jurisdiction / institution，源与规则逐条带官方出处与复核日期；
- Pack 状态为 draft/review_required：**人工政策复核通过前不得标 active**
  （上游 HANDOFF 的 reviewer guard，如实展示「待政策复核」）。

它自铸的 `VAL-*` digest 不在我们 Rules Registry 的签发链上——B8 闸门只认
Rules 签发的 validation_id。包装签发见 `campuspath_rules.context_pack`。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .international_student.campuspath_context import (   # noqa: F401
    ContextPackEvaluator,
    PackLoader,
)

VENDORED_COMMIT = "ef6a2f2242bdb66ded423b341e5c414b3e7d3863"
PACK_VERSION = "0.1.0"

_EVALUATOR: ContextPackEvaluator | None = None


def evaluate_intl_context(
    profile: dict[str, Any],
    opportunity: dict[str, Any] | None = None,
    *,
    as_of: str | date | None = None,
) -> dict[str, Any]:
    """求值信封（loader 进程内缓存——数据是入库冻结的，不会中途变）。"""
    global _EVALUATOR
    if _EVALUATOR is None:
        _EVALUATOR = ContextPackEvaluator()
    return _EVALUATOR.evaluate(profile, opportunity, as_of=as_of)


# ── 官方问答对照表（2026-08-02 用户需求：找官方信息类动作直接给链接）────
_ANSWERS: dict[str, Any] | None = None


def load_official_answers() -> dict[str, Any]:
    """加载 official_answers.json（进程内缓存；零 LLM，纯 stdlib）。"""
    global _ANSWERS
    if _ANSWERS is None:
        import json
        from pathlib import Path

        path = Path(__file__).resolve().parent / "official_answers.json"
        _ANSWERS = json.loads(path.read_text(encoding="utf-8"))
    return _ANSWERS


def match_official_answer(text: str) -> dict[str, Any] | None:
    """确定性关键词匹配：命中数最多的条目胜出（并列取 answer_id 字典序）。

    只做词面匹配、只回官方链接指引——**不转述、不解读政策内容**
    （政策解读归 Pack 的人工复核流程，见 Spec §8.9 红线纪律）。
    """
    haystack = text.lower()
    best: tuple[int, str, dict[str, Any]] | None = None
    for entry in load_official_answers()["entries"]:
        hits = sum(1 for kw in entry["keywords"] if kw.lower() in haystack)
        if hits == 0:
            continue
        key = (-hits, entry["answer_id"])
        if best is None or key < (best[0], best[1]):
            best = (key[0], key[1], entry)
    return best[2] if best else None
