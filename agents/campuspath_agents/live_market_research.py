"""现场市场研究流水线（2026-08-02 用户裁定：现场拆解 = 真流水线）。

「AI 现场拆解这个岗位」按下后，Google 模型 agents **忠实执行**与离线编译器
同一套方法论——不是一次性的清单问答：

  S1 检索（接地搜索）   模型带 Google Search 工具找该岗位**当前在招**的真实 JD
  S2 抓取 + 逐行拆解    服务端逐条真实抓取 JD 原文（connector 抓取器，礼貌间隔），
                        模型把原文逐行拆成 layer|category 要点
                        ——原文永远走 data 通道（§8.9.1），抓不到的公司如实跳过
  S3 确定性加权合成     零模型：company 覆盖率 ≥60% ⇒ core；market_note 写实测
                        「现场实采：N 家在招 JD 中 M 家要求」；来源逐条带 URL

进度回调按真实阶段推进（检索 → 逐家抓取 i/N → 合成），前端进度条对应的就是
这条流水线。诚实纪律：搜不到就少、抓不到就跳过、解析不了就丢行——
**任何一步都不许编造**；产出 origin=ai_live，人工复核后可晋级编制库。

归类词表与 core 判据从离线编译器导入——两条流水线同一口径，不许漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from json import JSONDecodeError, loads
from typing import Callable, Protocol

from campuspath_contracts.common import LocalizedText
from campuspath_contracts.goals import Goal, RequirementFacet

from .model import ModelRequest

#: 与 seed/compile_employment_pack.py 同源的词表与判据——两条流水线不许漂移。
try:
    from compile_employment_pack import CATEGORY_MAP, CORE_JD_COVERAGE  # type: ignore
except ImportError:   # agents 独立跑测试时 seed 不在 path：就地补上
    import pathlib
    import sys as _sys

    _sys.path.append(str(pathlib.Path(__file__).resolve().parents[2] / "seed"))
    from compile_employment_pack import CATEGORY_MAP, CORE_JD_COVERAGE  # type: ignore

SEARCH_PROMPT = (
    "你是求职市场研究员。用搜索工具找出目标岗位**当前在招**的真实职位（JD），"
    "优先校招/初级岗，公司尽量多样（中外大厂/知名企业）。只输出一个 JSON 数组，"
    "不要其他文字：[{\"company\": \"公司名\", \"jd_title\": \"职位名\", "
    "\"url\": \"…\"}]。最多 8 家，每家一条。url 必须指向**正文直接包含任职要求"
    "文本**的职位详情页（官方 JD 详情页，或 nowcoder/liepin/就业平台等镜像的"
    "详情页均可）——不要招聘首页、职位列表页、搜索结果页、需登录的页面。"
    "只写你真的搜到的——搜不到就少写。"
)

EXTRACT_GROUNDED_PROMPT = (
    "你是 JD 拆解员。DATA-1 指定了公司与职位。用搜索工具找到并**阅读**该公司"
    "这一职位（或其当前在招的最接近同类职位）的任职要求原文，逐行拆成要点。"
    "只输出行，不要任何前言：layer|category|中文概括|English summary。"
    "layer ∈ {hard,soft,constraint}；category **只能**从这份词表里选："
    + ", ".join(sorted(CATEGORY_MAP)) +
    "。最后一行额外输出 SOURCE|<你实际引用的职位页面 URL>。"
    "读不到真实要求就只输出 NO_REQUIREMENTS，不许凭印象编造。"
)

#: 模型常见的词表外近义 → 词表内类目（确定性归一，宁保守勿臆断——
#: 归不进去的仍然丢弃）。2026-08-02 实测：接地抽取会给 education/tool/time。
CATEGORY_ALIASES = {
    "education": "education_degree",
    "degree": "education_degree",
    "major": "education_degree",
    "tool": "technical_skill",
    "tools": "technical_skill",
    "software": "technical_skill",
    "skill": "technical_skill",
    "skills": "technical_skill",
    "portfolio": "project_portfolio",
    "experience": "internship",
    "work_experience": "internship",
    "time": "availability_duration",
    "duration": "availability_duration",
    "analytics": "data_sense",
    "data": "data_sense",
    "creativity": "problem_solving",
}

EXTRACT_PROMPT = (
    "你是 JD 拆解员。DATA-1 是公司与职位名，DATA-2 是该职位页面抓取的原文。"
    "把其中的**任职要求/资格要求**逐行拆成要点。只输出行，每行格式："
    "layer|category|中文概括|English summary。"
    "layer ∈ {hard,soft,constraint}；category 只能用："
    + ", ".join(sorted(CATEGORY_MAP)) + "。"
    "原文里没有的不要发明；页面若不含职位要求内容，输出 NO_REQUIREMENTS。"
)


class ResearchModel(Protocol):
    def generate(self, request: ModelRequest) -> str: ...
    def generate_grounded(self, request: ModelRequest) -> str: ...


@dataclass
class CollectedJD:
    company: str
    jd_title: str
    url: str
    #: (layer, category, zh, en)
    points: tuple[tuple[str, str, str, str], ...]


@dataclass
class LiveResearchOutcome:
    facets: tuple[RequirementFacet, ...]
    companies: tuple[CollectedJD, ...]
    #: 搜到但抓取失败/无正文而被如实跳过的公司名
    skipped: tuple[str, ...] = field(default_factory=tuple)


class LiveResearchEmpty(RuntimeError):
    """一份 JD 都没能采到——如实失败，不出无来源的结果。"""


def _parse_postings(raw: str, cap: int) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        rows = loads(text[start:end + 1])
    except JSONDecodeError:
        return []
    postings, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company", "")).strip()
        url = str(row.get("url", "")).strip()
        if not company or not url.startswith("http") or company in seen:
            continue
        seen.add(company)
        postings.append({"company": company,
                         "jd_title": str(row.get("jd_title", "")).strip(),
                         "url": url})
        if len(postings) >= cap:
            break
    return postings


def _parse_points(raw: str) -> tuple[tuple[str, str, str, str], ...]:
    points = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            continue
        layer, category, zh, en = parts
        if layer not in {"hard", "soft", "constraint"}:
            continue
        category = CATEGORY_ALIASES.get(category, category)
        if category not in CATEGORY_MAP or not zh or not en:
            continue   # 词表外/残行：丢弃，不硬造
        points.append((layer, category, zh, en))
    return tuple(points)


def _synthesise(collected: list[CollectedJD], today: date,
                ) -> tuple[RequirementFacet, ...]:
    """步骤 5 的运行时版：与编译器同判据的确定性加权，零模型。"""
    from collections import Counter, defaultdict

    n = len(collected)
    company_hits: dict[str, set[str]] = defaultdict(set)
    layer_of: dict[str, str] = {}
    summaries: dict[str, Counter] = defaultdict(Counter)
    sources_of: dict[str, list[CollectedJD]] = defaultdict(list)
    for jd in collected:
        seen_cats = set()
        for layer, category, zh, en in jd.points:
            company_hits[category].add(jd.company)
            layer_of[category] = layer
            summaries[category][(zh, en)] += 1
            if category not in seen_cats:
                sources_of[category].append(jd)
                seen_cats.add(category)

    order = {"hard": 0, "soft": 1, "constraint": 2}
    facets: list[RequirementFacet] = []
    for category in sorted(company_hits,
                           key=lambda c: (order[layer_of[c]],
                                          -len(company_hits[c]))):
        contract_cat, label_zh, label_en = CATEGORY_MAP[category]
        hits = len(company_hits[category])
        top = [pair for pair, _ in summaries[category].most_common(2)]
        detail_zh = "；".join(z for z, _ in top)
        detail_en = "; ".join(e for _, e in top)
        facets.append(RequirementFacet(
            category=contract_cat,
            kind=layer_of[category],
            description=LocalizedText(zh_Hans=f"{label_zh}：{detail_zh}",
                                      en=f"{label_en}: {detail_en}"),
            priority="core" if hits / n >= CORE_JD_COVERAGE else "standard",
            market_note=LocalizedText(
                zh_Hans=f"{n} 家在招 JD 中 {hits} 家要求"
                        f"（{today.isoformat()} 实时采集）",
                en=f"Required by {hits} of {n} open JDs "
                   f"(live-collected {today.isoformat()})",
            ),
            evidence_sources=tuple(
                LocalizedText(
                    zh_Hans=f"「{jd.company} · {jd.jd_title or '在招职位'}」{jd.url}",
                    en=f"[{jd.company} · {jd.jd_title or 'open role'}] {jd.url}",
                ) for jd in sources_of[category][:3]
            ),
            origin="ai_live",
        ))
    return tuple(facets)


def run_live_market_research(
    model: ResearchModel,
    goal: Goal,
    *,
    fetch_text: Callable[[str], str | None],
    progress: Callable[[int, str, str], None],
    today: date,
    max_companies: int = 8,
) -> LiveResearchOutcome:
    progress(8, f"检索「{goal.target_name}」的在招 JD…",
             f"Searching open JDs for “{goal.target_name}”…")
    raw = model.generate_grounded(ModelRequest(
        purpose=f"jd-search:{goal.goal_id}",
        system=SEARCH_PROMPT, data=(goal.target_name,)))
    postings = _parse_postings(raw, cap=max_companies)
    if not postings:
        raise LiveResearchEmpty("接地搜索没有返回可用的在招 JD 列表")

    collected: list[CollectedJD] = []
    skipped: list[str] = []
    for index, posting in enumerate(postings):
        progress(15 + int(60 * index / len(postings)),
                 f"抓取并逐行拆解 {index + 1}/{len(postings)}：{posting['company']}",
                 f"Fetching & decomposing {index + 1}/{len(postings)}: "
                 f"{posting['company']}")
        points: tuple = ()
        used_url = posting["url"]
        text = fetch_text(posting["url"])
        if text and len(text.strip()) >= 80:
            raw_points = model.generate(ModelRequest(
                purpose=f"jd-extract:{goal.goal_id}:{index}",
                system=EXTRACT_PROMPT,
                data=(f"公司：{posting['company']}；职位：{posting['jd_title']}",
                      text[:8000]),
            ))
            points = _parse_points(raw_points)
        if not points:
            # 直抓失败/壳页（大厂招聘页多为 JS 渲染）→ 接地抽取回退：
            # 带搜索工具的模型自己找到并阅读该职位要求原文，并回报
            # 它实际引用的页面 URL。内容仍来自实时网页，不是凭印象。
            try:
                raw_grounded = model.generate_grounded(ModelRequest(
                    purpose=f"jd-extract-grounded:{goal.goal_id}:{index}",
                    system=EXTRACT_GROUNDED_PROMPT,
                    data=(f"公司：{posting['company']}；职位：{posting['jd_title']}；"
                          f"参考 URL：{posting['url']}",),
                ))
            except Exception:
                raw_grounded = ""
            points = _parse_points(raw_grounded)
            for line in raw_grounded.splitlines():
                if line.strip().startswith("SOURCE|"):
                    candidate = line.split("|", 1)[1].strip()
                    if candidate.startswith("http"):
                        used_url = candidate
                    break
        if not points:
            skipped.append(posting["company"])   # 两条路都拿不到 → 如实跳过
            continue
        collected.append(CollectedJD(
            company=posting["company"], jd_title=posting["jd_title"],
            url=used_url, points=points))

    if not collected:
        raise LiveResearchEmpty(
            f"搜到 {len(postings)} 家但全部抓取/拆解失败（{', '.join(skipped)}）")

    progress(88, f"确定性加权合成（实采 {len(collected)} 家）…",
             f"Deterministic weighting over {len(collected)} collected JDs…")
    facets = _synthesise(collected, today)
    return LiveResearchOutcome(
        facets=facets, companies=tuple(collected), skipped=tuple(skipped))
