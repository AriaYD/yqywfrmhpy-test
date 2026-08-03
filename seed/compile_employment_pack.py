#!/usr/bin/env python3
"""求职拆解 Pack 编译器（A2，2026-08-02 用户提案六步的固化）。

输入（seed/raw/jd_market/<role>/）：
  jd_corpus.draft.json                 —— 步骤 1+2：JD 语料 + 逐行拆解归类
  success_profiles_aggregate.draft.json（可选）—— 步骤 3：成功者履历去标识聚合
输入（agents/campuspath_agents/pack_data/）：
  evidence_catalog.draft.json          —— 步骤 4：权威比赛/证书/活动榜单
输出：
  agents/campuspath_agents/pack_data/employment_roles.json   —— 岗位画像（运行时消费）
  agents/campuspath_agents/pack_data/evidence_catalog.json   —— 定稿参考表
  docs/verification/pack-compiler/weights_audit.md           —— 权重审计表

权重规则（步骤 5，确定性）：
  core ⇔ JD 公司覆盖率 ≥ 60% **或** 履历聚合出现率 ≥ 50%。
  履历聚合缺失时按 JD-only 口径，market_note 与审计表如实注明
  （2026-08-02 实测：LinkedIn 免费账号搜索结果匿名化，步骤 3 未取得样本）。

重跑即刷新：数据драфт更新后 `python3 seed/compile_employment_pack.py`。
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict

REPO = pathlib.Path(__file__).resolve().parent.parent
JD_DIR = REPO / "seed" / "raw" / "jd_market"
PACK_DATA = REPO / "agents" / "campuspath_agents" / "pack_data"
AUDIT_DIR = REPO / "docs" / "verification" / "pack-compiler"

ROLES = {
    "ai-product-manager": {
        "keywords": ["产品经理", "product manager", "ai pm", "ai产品", "ai 产品",
                     "产品岗", "product owner"],
        "label_zh": "AI 产品经理", "label_en": "AI Product Manager",
    },
    "software-engineer": {
        "keywords": ["软件工程师", "software engineer", "swe", "开发工程师",
                     "developer", "后端", "前端", "backend", "frontend", "全栈"],
        "label_zh": "软件工程师", "label_en": "Software Engineer",
    },
}

#: category → (RequirementCategory, 中文标签, 英文标签)。
#: JD 语料的归类词表 → 契约枚举的确定性映射。
CATEGORY_MAP = {
    # hard
    "coursework": ("coursework", "专业课程与绩点", "Coursework & GPA"),
    "coursework/gpa": ("coursework", "专业课程与绩点", "Coursework & GPA"),
    "gpa": ("coursework", "专业课程与绩点", "Coursework & GPA"),
    "internship": ("industry_experience", "实习经历", "Internship experience"),
    "project_portfolio": ("project_portfolio", "完整项目经历与作品集", "Projects & portfolio"),
    "competition": ("project_portfolio", "比赛经历与奖项", "Competitions & awards"),
    "credential": ("credential", "证书与专业资格", "Credentials & certifications"),
    "technical_skill": ("technical_skill", "核心技能栈", "Core technical skills"),
    "education_degree": ("coursework", "学历与专业背景", "Degree & academic background"),
    # soft
    "communication": ("communication", "沟通表达", "Communication"),
    "teamwork": ("teamwork_evidence", "团队协作", "Teamwork"),
    "leadership": ("teamwork_evidence", "领导力", "Leadership"),
    "influence": ("communication", "影响力与推动力", "Influence"),
    "ownership": ("teamwork_evidence", "责任心与主人翁意识", "Ownership"),
    "learning_agility": ("technical_skill", "学习能力与好奇心", "Learning agility"),
    "user_empathy": ("communication", "用户同理心", "User empathy"),
    "data_sense": ("technical_skill", "数据敏感度", "Data sense"),
    "execution": ("teamwork_evidence", "执行落地能力", "Execution"),
    "problem_solving": ("technical_skill", "问题解决能力", "Problem solving"),
    # constraint
    "visa_identity": ("eligibility_status", "身份/工作授权", "Visa / work authorisation"),
    "location": ("eligibility_status", "工作地点", "Location"),
    "language": ("language", "语言要求", "Language requirements"),
    "availability_duration": ("eligibility_status", "到岗时长/实习时长", "Availability / duration"),
    "start_date": ("eligibility_status", "到岗时间", "Start date"),
}

#: 履历聚合的 evidence_type → JD category（两组数字并到同一行）
AGG_MAP = {
    "big_company_internship": "internship",
    "multiple_internships": "internship",
    "famous_competition": "competition",
    "personal_projects": "project_portfolio",
    "open_source": "project_portfolio",
    "certifications": "credential",
    "club_leadership": "leadership",
    "research_papers": "coursework",
    "language_certificates": "language",
    "target_degree": "education_degree",
}

CORE_JD_COVERAGE = 0.60
CORE_RESUME_RATE = 0.50


def load_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compile_role(role: str) -> tuple[list[dict], list[str]]:
    corpus = load_json(JD_DIR / role / "jd_corpus.draft.json")
    companies = corpus["companies"]
    n_companies = len(companies)
    assert n_companies >= 8, f"{role}: 语料公司数不足（{n_companies}）"

    # 覆盖率 = 有该 category 要点的公司数 / 公司总数（不是要点计数——
    # 一家公司写三遍沟通能力不该算三票）
    company_hits: dict[str, set[str]] = defaultdict(set)
    layer_of: dict[str, str] = {}
    summaries: dict[str, Counter] = defaultdict(Counter)
    for company in companies:
        cov = company["coverage"]
        assert cov["lines_total"] == cov["lines_mapped"], \
            f"{role}/{company['company']}: 覆盖率不足（禁止遗漏被违反）"
        for line in company["requirement_lines"]:
            for point in line["points"]:
                cat = point["category"]
                company_hits[cat].add(company["company"])
                layer_of[cat] = point["layer"]
                summaries[cat][(point["summary_zh"], point["summary_en"])] += 1

    # 履历聚合（可选）
    agg_path = JD_DIR / role / "success_profiles_aggregate.draft.json"
    resume_rates: dict[str, tuple[int, int]] = {}
    resume_note = None
    if agg_path.exists():
        agg = load_json(agg_path)
        for stat in agg["evidence_stats"]:
            cat = AGG_MAP.get(stat["evidence_type"])
            if cat:
                resume_rates[cat] = (stat["count"], stat["of"])
    else:
        resume_note = ("履历聚合未执行（2026-08-02：LinkedIn 免费账号搜索结果"
                       "匿名化为「领英会员」，无法定位公开档案；换有完整可见性"
                       "的账号后可补跑），本轮权重为 JD-only 口径")

    catalog = load_json(PACK_DATA / "evidence_catalog.draft.json")
    refs_by_kind: dict[str, list[str]] = defaultdict(list)
    for entry in catalog["entries"]:
        if role in entry["applicable_roles"]:
            refs_by_kind[entry["kind"]].append(entry["id"])
    ref_map = {
        "competition": tuple(refs_by_kind["competition"][:5]),
        "project_portfolio": tuple(refs_by_kind["activity"][:4]),
        "credential": tuple(refs_by_kind["credential"][:5]),
        "internship": tuple(refs_by_kind["activity"][:3]),
    }

    facets: list[dict] = []
    audit_rows: list[str] = []
    order = {"hard": 0, "soft": 1, "constraint": 2}
    for cat in sorted(company_hits, key=lambda c: (order[layer_of[c]], -len(company_hits[c]))):
        mapped = CATEGORY_MAP.get(cat)
        if mapped is None:
            raise SystemExit(f"{role}: 未映射的 category {cat}")
        contract_cat, label_zh, label_en = mapped
        hits = len(company_hits[cat])
        coverage = hits / n_companies
        resume = resume_rates.get(cat)
        is_core = coverage >= CORE_JD_COVERAGE or (
            resume is not None and resume[1] > 0 and resume[0] / resume[1] >= CORE_RESUME_RATE
        )
        top = [pair for pair, _ in summaries[cat].most_common(2)]
        detail_zh = "；".join(z for z, _ in top)
        detail_en = "; ".join(e for _, e in top)
        note_zh = f"{n_companies} 份头部 JD 中 {hits} 份要求"
        note_en = f"Required by {hits} of {n_companies} top-company JDs"
        if resume:
            note_zh += f"；成功者履历 {resume[0]}/{resume[1]} 份具备"
            note_en += f"; present in {resume[0]}/{resume[1]} hire profiles"
        layer = layer_of[cat]
        facet = {
            "category": contract_cat,
            "kind": layer,
            "description": {"zh_Hans": f"{label_zh}：{detail_zh}",
                            "en": f"{label_en}: {detail_en}"},
            "evidence_sources": (
                [{"zh_Hans": f"取证参考：{label_zh}相关的权威比赛/证书/项目（见证据参考表）",
                  "en": f"Evidence via authoritative competitions/credentials/projects for {label_en}"}]
                if layer == "soft" else []
            ),
            "resource_channels": [],
            "priority": "core" if is_core else "standard",
            "market_note": {"zh_Hans": note_zh, "en": note_en},
            "evidence_refs": list(ref_map.get(cat, ())),
        }
        facets.append(facet)
        audit_rows.append(
            f"| {cat} | {layer} | {hits}/{n_companies} ({coverage:.0%}) | "
            f"{'%d/%d' % resume if resume else '—'} | "
            f"{'**core**' if is_core else 'standard'} |"
        )
    if resume_note:
        audit_rows.append(f"\n> {resume_note}\n")
    return facets, audit_rows


def main() -> int:
    role_profiles = {}
    audit_md = ["# 求职拆解 Pack 权重审计表（编译器自动生成）\n",
                f"生成命令：`python3 seed/compile_employment_pack.py`；"
                f"core 判据：JD 公司覆盖率 ≥{CORE_JD_COVERAGE:.0%} 或 履历出现率 ≥{CORE_RESUME_RATE:.0%}\n"]
    for role, meta in ROLES.items():
        facets, rows = compile_role(role)
        role_profiles[role] = {
            "label": {"zh_Hans": meta["label_zh"], "en": meta["label_en"]},
            "keywords": meta["keywords"],
            "facets": facets,
        }
        audit_md += [f"\n## {meta['label_zh']} / {meta['label_en']}\n",
                     "| category | layer | JD 覆盖 | 履历出现 | priority |",
                     "|---|---|---|---|---|", *rows]

    out = {
        "compiled_at": "2026-08-02",
        "methodology": "docs/pack-compiler-methodology.md",
        "sources": {
            role: f"seed/raw/jd_market/{role}/jd_corpus.draft.json（10 家公司官方 JD，"
                  "覆盖率 100% 行映射，URL 逐条实测可达）"
            for role in ROLES
        },
        "role_profiles": role_profiles,
    }
    PACK_DATA.mkdir(parents=True, exist_ok=True)
    (PACK_DATA / "employment_roles.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 参考表定稿：draft 原样晋级（人工复核在 git diff 里做）
    catalog = load_json(PACK_DATA / "evidence_catalog.draft.json")
    (PACK_DATA / "evidence_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # 前端副本（goals 页把 evidence_refs 展开为可点官方链接）。
    # 单一出处 = 本编译器：两份产物同一次生成，不存在手改漂移。
    web_copy = REPO / "apps" / "web" / "src" / "data" / "evidence-catalog.json"
    web_copy.parent.mkdir(parents=True, exist_ok=True)
    web_copy.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "weights_audit.md").write_text("\n".join(audit_md) + "\n", encoding="utf-8")

    for role, profile in role_profiles.items():
        core = sum(1 for f in profile["facets"] if f["priority"] == "core")
        print(f"{role}: {len(profile['facets'])} facets（core {core}）")
    print("written: employment_roles.json / evidence_catalog.json / weights_audit.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
