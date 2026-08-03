"""D 裁定（2026-08-02）：Resume 上传模板化——零模型、纯规则解析。

用户原话：「上传用 markdown 文档上传简历，resume 模板定死……直接可以通过
规则脚本把信息对应填到个人成长总览页面。这里就不用那个 google 的 ai 了。」
边界不变：解析产物仍是 pending 提议（B3——档案唯一写入路径是已确认提议），
但提炼环节从模型换成确定性解析器，教育/证书/语言/荣誉四类不再结构性丢弃。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_api.app import create_app
from campuspath_api.resume_template import TemplateError, parse_resume_template

TEMPLATE_RESUME = """# Resume — 陈思远

## Education（教育经历）
- HKUST | BSc in Computer Science | 2025 → 2029
- 合成高中（Demo） | 理科 | 2019 → 2025

## Internships & Work（实习与工作）
- 合成科技公司（Demo） | 前端开发实习生 | 2026-06 → 2026-08

## Projects（项目）
- Mist Courier | 独立完成关卡系统与存档系统 | 2025-11 → 2026-02
- RhythmGrid | 实现判定窗口与谱面编辑器 | 2025-06 → 2025-08

## Clubs & Volunteering（社团与志愿）
- HKUST Game Development Club | Workshop Officer | 2025-09 → present

## Skills（技能）
- C#, C++, Python, TypeScript, Unity

## Certificates（证书）
- Unity Certified User: Programmer | SYNTH-UCUP-2025-1187 | 2025-12

## Awards & Honors（荣誉奖项）
- Dorm Jam「Best Feel」提名 | Dorm Jam 评审团 | 2025-10

## Languages（语言）
- 粤语 | 母语
- English | Fluent | IELTS 7.0
"""


# ── 解析器单测（纯函数，零模型）──────────────────────────────────────


def test_parser_extracts_every_section():
    changes = parse_resume_template(TEMPLATE_RESUME)
    by_type: dict[str, list] = {}
    for c in changes:
        by_type.setdefault(c.entity_type, []).append(c)
    assert len(by_type["skill"]) == 5
    exps = by_type["experience"]
    assert len(exps) == 4          # 1 实习 + 2 项目 + 1 社团
    types = sorted(e.new_value["type"] for e in exps)
    assert types == ["club", "internship", "project", "project"]
    # 项目带真实起止（红-1 曾因 type=other + 无 period 而总览不可见）
    mist = next(e for e in exps if e.new_value["organization"] == "Mist Courier")
    assert mist.new_value["period_start"] == "2025-11-01"
    assert len(by_type["education"]) == 2
    assert len(by_type["certificate"]) == 1
    assert len(by_type["honor"]) == 1
    assert len(by_type["language"]) == 2


def test_parser_rejects_non_template_text():
    with pytest.raises(TemplateError):
        parse_resume_template("我是一段自由文本简历，没有任何模板小节。")


def test_parser_tolerates_missing_optional_sections():
    changes = parse_resume_template(
        "## Skills（技能）\n- Python, Go\n")
    assert [c.entity_type for c in changes] == ["skill", "skill"]


# ── 端点行为 ────────────────────────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _headers(student: str = "STU-A") -> dict[str, str]:
    return {"X-CampusPath-Role": "student", "X-CampusPath-Student": student}


def test_upload_template_resume_needs_no_model(client: TestClient):
    """零 AI：没有模型后端也必须能解析（此前 deps.model=None → 503）。"""
    resp = client.post(
        "/v1/students/STU-A/resume", headers=_headers(),
        json={"filename": "template.md",
              "content_text": TEMPLATE_RESUME},
    )
    assert resp.status_code == 200, resp.text
    proposal = resp.json()
    kinds = {c["entity_type"] for c in proposal["proposed_changes"]}
    assert {"skill", "experience", "education",
            "certificate", "honor", "language"} <= kinds
    assert "零 AI" in proposal["reason"] or "规则" in proposal["reason"]


def test_upload_free_text_resume_rejected_with_hint(client: TestClient):
    resp = client.post(
        "/v1/students/STU-A/resume", headers=_headers(),
        json={"filename": "free.md",
              "content_text": "这是一段没有模板结构的自由简历文本。"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "resume_not_in_template"
    assert "Skills" in str(detail) or "模板" in str(detail)


def test_confirm_materializes_all_entity_kinds(client: TestClient):
    up = client.post(
        "/v1/students/STU-A/resume", headers=_headers(),
        json={"filename": "template.md",
              "content_text": TEMPLATE_RESUME},
    )
    pid = up.json()["proposal_id"]
    dec = client.post(
        f"/v1/students/STU-A/profile/proposals/{pid}/decision?decision=confirmed",
        headers=_headers(),
    )
    assert dec.status_code == 200, dec.text

    exps = client.get("/v1/students/STU-A/experiences",
                      headers=_headers()).json()
    mine = [e for e in exps if e["experience_id"].startswith(f"EXP-{pid}")]
    assert sorted(e["type"] for e in mine) == [
        "club", "internship", "project", "project"]

    extras = client.get("/v1/students/STU-A/profile/extras",
                        headers=_headers()).json()
    schools = {e["school"] for e in extras["education"]}
    assert "HKUST" in schools
    assert any(l["language"] == "English" for l in extras["languages"])
    assert any("Best Feel" in h["title"] for h in extras["honors"])

    # 审查 M6：自述证书落 extras（无伪造 Vault 引用），编号进 note
    assert any("Unity Certified" in c["title"]
               and "SYNTH-UCUP" in (c["note"] or "")
               for c in extras["certificates"])
    evidence = client.get("/v1/students/STU-A/evidence",
                          headers=_headers()).json()
    assert not any("resume-certs" in (ev.get("object_ref") or "")
                   for ev in evidence), "不许伪造 Vault 对象引用"


def test_confirm_extras_materialization_is_idempotent_and_deduped(
        client: TestClient):
    """同一份模板传两次、各自确认：extras 不重复堆同一学校/语言。"""
    for _ in range(2):
        up = client.post(
            "/v1/students/STU-A/resume", headers=_headers(),
            json={"filename": "template.md",
                  "content_text": TEMPLATE_RESUME},
        )
        pid = up.json()["proposal_id"]
        client.post(
            f"/v1/students/STU-A/profile/proposals/{pid}/decision?decision=confirmed",
            headers=_headers(),
        )
    extras = client.get("/v1/students/STU-A/profile/extras",
                        headers=_headers()).json()
    assert len([e for e in extras["education"]
                if e["school"] == "HKUST"]) == 1
    assert len([l for l in extras["languages"]
                if l["language"] == "English"]) == 1


def test_untouched_template_yields_no_placeholder_changes():
    """审查 H4：官方模板原样上传（占位符没填）不许产出任何提案条目。"""
    template = open(
        "../../apps/web/public/resume-template.md", encoding="utf-8").read()
    with pytest.raises(TemplateError):
        parse_resume_template(template)


def test_per_kind_cap_limits_materialisation_volume():
    """审查 M5：每类条目有上限——不许一次确认写入上千条记录。"""
    flood = "## Skills（技能）\n" + "\n".join(
        f"- Skill{i}" for i in range(300))
    changes = parse_resume_template(flood)
    assert len(changes) <= 50


def test_full_iso_dates_and_ascii_range_separator_parse():
    """审查 L16：完整 ISO 日期与「空格-空格」分隔都要能解析。"""
    text = ("## Projects（项目）\n"
            "- DemoProj | 角色 | 2024-09-15 - 2025-06-30\n")
    changes = parse_resume_template(text)
    v = changes[0].new_value
    assert v["period_start"] == "2024-09-15"
    assert v["period_end"] == "2025-06-30"


def test_bundled_demo_resumes_parse_cleanly():
    """评委一键注入（2026-08-04 用户需求）：随站点分发的两份 demo 学生
    简历（「小红帽」「大灰狼」，专业不同）必须逐节解析干净——覆盖多类
    小节、字段成对、零 markdown 残渣（** 等）、零占位符漏网。这是演示
    第一入口，坏一行评委就看一行垃圾。"""
    for name in ("demo-resume-xiaohongmao.md", "demo-resume-dahuilang.md"):
        text = open(f"../../apps/web/public/{name}", encoding="utf-8").read()
        changes = parse_resume_template(text)
        kinds = {c.entity_type for c in changes}
        assert {"experience", "education", "certificate",
                "language"} <= kinds, (name, kinds)
        assert len(changes) >= 8, (name, len(changes))
        for c in changes:
            blob = str(c.new_value)
            assert "**" not in blob, (name, blob)
            assert "<" not in blob and "＜" not in blob, (name, blob)
            if c.entity_type == "experience":
                assert c.new_value.get("organization"), (name, c.new_value)
                assert c.new_value.get("role"), (name, c.new_value)
