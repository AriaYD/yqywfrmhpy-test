"""官方问答对照表测试（2026-08-02 用户需求：找官方信息类动作直接给链接）。

H5 双向：已知问题必须命中对应官方域名；无关文本必须返回 None。
纪律：只给链接指引、零 LLM、不转述政策内容。
"""

from campuspath_packs import load_official_answers, match_official_answer


def test_doc_shape_and_urls():
    doc = load_official_answers()
    assert doc["disclaimer_zh"] and doc["entries"]
    for entry in doc["entries"]:
        assert entry["keywords"], entry["answer_id"]
        assert entry["links"], entry["answer_id"]
        for link in entry["links"]:
            assert link["url"].startswith("https://"), link
            assert link["source_id"], link


def test_known_questions_hit_official_domains():
    cases = {
        "Confirm graduation status, timing, and current IANG requirements "
        "with Immigration Department.": "immd.gov.hk",
        "核实/补充信息：actual_graduation_date": "registry.hkust.edu.hk",
        "offer_or_employment_plan": "career.hkust.edu.hk",
        "student_visa 在读实习限制": "immd.gov.hk",
    }
    for question, domain in cases.items():
        answer = match_official_answer(question)
        assert answer is not None, question
        assert any(domain in link["url"] for link in answer["links"]), (
            question, answer["answer_id"])


def test_unrelated_text_returns_none():
    assert match_official_answer("篮球社周五训练 basketball drills") is None


def test_iang_answer_includes_user_specified_zh_page():
    answer = match_official_answer("current IANG requirements")
    urls = [link["url"] for link in answer["links"]]
    assert "https://www.immd.gov.hk/hks/services/visas/IANG.html" in urls
