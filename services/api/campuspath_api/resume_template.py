"""Resume 模板的确定性解析器（D 裁定，2026-08-02）。**零模型。**

用户裁定：上传只接受定死的 markdown 模板；符合模板的简历用规则脚本
逐节解析，「总不会出错」，且这一步彻底不接模型。模板正文的唯一出处是
``apps/web/public/resume-template.md``（学生可下载），小节标题在下表；
中英文标题都认，节内每行 ``- 字段1 | 字段2 | 字段3``。

解析产物是 :class:`ProposedChange` 列表——仍走 B3（学生逐项确认才落档），
换掉的只是「模型提炼」这一环。
"""

from __future__ import annotations

import re

from campuspath_contracts.profile import ProposedChange

#: 小节识别：小写化后的标题只要含任一关键词即归类。顺序即优先级——
#: 「社团与志愿」要先于「组织」类词命中，避免被更泛的词抢走。
_SECTION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("education", ("education", "教育")),
    ("internship", ("internship", "work", "实习", "工作")),
    ("project", ("project", "项目")),
    ("club", ("club", "volunteer", "社团", "志愿")),
    ("skills", ("skill", "技能")),
    ("certificate", ("certificate", "证书")),
    ("honor", ("award", "honor", "荣誉", "奖")),
    ("language", ("language", "语言")),
)

_YM = re.compile(r"^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?$")

#: 审查 H4：未改动的模板占位符（``<学校>`` 这类）不许变成提案条目
_PLACEHOLDER = re.compile(r"^[<＜].*[>＞]$")

#: 审查 M5：每类条目上限——60k 字符的输入不许物化出上千条记录
_MAX_PER_KIND = 50

#: 小节标题必须是行首 ``## ``（审查 L17：### 子标题与代码块里的 ## 不算）
_SECTION_LINE = re.compile(r"^##\s")


class TemplateError(ValueError):
    """正文不符合模板：没有任何可识别小节，或识别出的小节全部为空。"""

    #: 给 422 详情用的模板小节清单（一处维护）
    EXPECTED = ("Education / Internships & Work / Projects / "
                "Clubs & Volunteering / Skills / Certificates / "
                "Awards & Honors / Languages")


def _norm_date(token: str | None) -> str | None:
    """``2025-11-03``→原样；``2025-11`` → ``2025-11-01``；``2025`` → ``2025-01-01``；

    ``present``/``至今``/空 → None。规则解析不猜具体日：缺月/日统一取 1，
    完整 ISO 日期照收（审查 L16）——排序与分桶够用，且可回溯到原文。
    """
    if not token:
        return None
    token = token.strip().lower()
    if token in ("present", "now", "至今", "current"):
        return None
    m = _YM.match(token)
    if not m:
        return None
    year, month, day = m.group(1), m.group(2) or "01", m.group(3) or "01"
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _split_range(cell: str) -> tuple[str | None, str | None]:
    # 审查 L16：分隔符补最常见的「空格-空格」（带空格才不与 YYYY-MM 冲突）
    parts = re.split(r"\s*(?:→|->|—|~|至)\s*|\s+-\s+", cell.strip(), maxsplit=1)
    start = _norm_date(parts[0])
    end = _norm_date(parts[1]) if len(parts) > 1 else None
    return start, end


def _clean_cell(cell: str) -> str:
    """剥掉尾部括注（「（逗号分隔…）」这类填写说明），占位符判空。"""
    cell = re.sub(r"[（(][^（()）]*[)）]\s*$", "", cell).strip()
    if _PLACEHOLDER.match(cell):
        return ""
    return cell


def _rows(section_lines: list[str]) -> list[list[str]]:
    rows = []
    for line in section_lines:
        line = line.strip()
        if not line.startswith(("-", "*")):
            continue
        cells = [_clean_cell(c) for c in line.lstrip("-* ").split("|")]
        # 首列是占位/说明 → 整条丢弃（审查 H4：模板原样上传零产出）
        if cells and cells[0]:
            rows.append(cells)
        if len(rows) >= _MAX_PER_KIND:
            break
    return rows


def parse_resume_template(text: str) -> list[ProposedChange]:
    """按模板逐节解析。识别不出任何条目 → :class:`TemplateError`。"""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if _SECTION_LINE.match(line):
            title = line.lstrip("# ").lower()
            current = next(
                (kind for kind, keys in _SECTION_RULES
                 if any(k in title for k in keys)), None)
            if current is not None:
                sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    changes: list[ProposedChange] = []

    for kind in ("internship", "project", "club"):
        for cells in _rows(sections.get(kind, [])):
            org = cells[0]
            role = cells[1] if len(cells) > 1 else ""
            start = end = None
            if len(cells) > 2:
                start, end = _split_range(cells[2])
            value: dict = {"type": kind, "organization": org, "role": role}
            if start:
                value["period_start"] = start
            if end:
                value["period_end"] = end
            changes.append(ProposedChange(
                entity_type="experience", operation="add",
                field_path="experiences[]", new_value=value))

    for cells in _rows(sections.get("skills", [])):
        for name in re.split(r"[,，、;；]", cells[0]):
            name = _clean_cell(name.strip())
            if name:
                changes.append(ProposedChange(
                    entity_type="skill", operation="add",
                    field_path="skills[]", new_value=name[:80]))

    for cells in _rows(sections.get("education", [])):
        entry = {"school": cells[0][:200],
                 "program": (cells[1][:200] if len(cells) > 1 and cells[1]
                             else None)}
        if len(cells) > 2:
            start, end = _split_range(cells[2])
            entry["start_year"] = (start or "")[:4] or None
            entry["end_year"] = (end or "")[:4] or None
        changes.append(ProposedChange(
            entity_type="education", operation="add",
            field_path="extras.education[]", new_value=entry))

    for cells in _rows(sections.get("certificate", [])):
        changes.append(ProposedChange(
            entity_type="certificate", operation="add",
            field_path="evidence[]",
            new_value={"title": cells[0][:200],
                       "credential_id": cells[1][:120] if len(cells) > 1 else None,
                       "obtained": _norm_date(cells[2]) if len(cells) > 2 else None}))

    for cells in _rows(sections.get("honor", [])):
        changes.append(ProposedChange(
            entity_type="honor", operation="add",
            field_path="extras.honors[]",
            new_value={"title": cells[0][:300],
                       "issuer": cells[1][:200] if len(cells) > 1 else None,
                       "date": cells[2][:20] if len(cells) > 2 else None}))

    for cells in _rows(sections.get("language", [])):
        changes.append(ProposedChange(
            entity_type="language", operation="add",
            field_path="extras.languages[]",
            new_value={"language": cells[0][:60],
                       "proficiency": (cells[1][:60] if len(cells) > 1
                                       and cells[1] else "未注明"),
                       "certification": cells[2][:200] if len(cells) > 2 else None}))

    if not changes:
        raise TemplateError(
            f"未识别出任何模板小节条目；模板小节：{TemplateError.EXPECTED}")
    return changes
