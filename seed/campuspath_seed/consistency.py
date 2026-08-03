"""跨表一致性校验（WP2 验收条款）。

Spec §11.5 要求"所有 ID、先修关系、时间和资格必须跨表一致"，
且"不随机生成互相矛盾却无法解释的数据"。契约层已经挡住了单条记录的非法值，
这里挡的是**记录之间**的矛盾：引用了不存在的 id、先修顺序倒置、
Gold Label 指向已经不在数据集里的机会。

按 Plan §10 H5，本模块自带 ``--selftest``：往数据集里注入已知的矛盾，
断言每一项检查确实会失败。检查器不被检查，就只是让人放心的摆设。
"""

from __future__ import annotations

import copy
import dataclasses
import re
from typing import Any, Callable

from .config import FULL_SCALE_FLOORS, GOLD_SET_FLOORS, SYNTHETIC_NOTICE

#: 明显是真实个人信息的形状。合成数据里出现即失败（Plan §9）。
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.invalid)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HK_PHONE = re.compile(r"\b[2-9]\d{7}\b")


@dataclasses.dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


Check = Callable[[dict[str, Any]], CheckResult]


def _ids(rows: list[dict], key: str) -> set[str]:
    return {row[key] for row in rows if key in row}


def _result(name: str, offenders: list[str], noun: str) -> CheckResult:
    if offenders:
        shown = ", ".join(sorted(offenders)[:5])
        more = f"（共 {len(offenders)} 条）" if len(offenders) > 5 else ""
        return CheckResult(name, False, f"{noun}：{shown}{more}")
    return CheckResult(name, True)


# --------------------------------------------------------------------------
# 各项检查
# --------------------------------------------------------------------------


def check_course_references(bundle: dict[str, Any]) -> CheckResult:
    known = _ids(bundle["courses"], "course_id")
    offenders: list[str] = []
    for row in bundle["student_course_records"]:
        if row["course_id"] not in known:
            offenders.append(f"record {row['record_id']} → {row['course_id']}")
    for row in bundle["course_offerings"]:
        if row["course_id"] not in known:
            offenders.append(f"offering {row['offering_id']} → {row['course_id']}")
    for row in bundle["degree_requirements"]:
        for code in row["alternatives"]:
            if code not in known:
                offenders.append(f"requirement {row['requirement_id']} → {code}")
    return _result("课程引用一致", offenders, "引用了不存在的课程")


def check_student_references(bundle: dict[str, Any]) -> CheckResult:
    known = _ids(bundle["students"], "student_id")
    offenders: list[str] = []
    for table in (
        "student_course_records", "experiences", "projects", "achievements", "skills",
        "evidence", "notes", "goals", "calendar_connections", "availability_blocks",
        "capacity_snapshots", "profile_update_proposals", "profile_change_events",
        "memory_entries",
    ):
        for row in bundle[table]:
            if row.get("student_id") not in known:
                offenders.append(f"{table} → {row.get('student_id')}")
                break
    return _result("学生引用一致", offenders, "引用了不存在的学生")


def check_evidence_and_note_references(bundle: dict[str, Any]) -> CheckResult:
    evidence = _ids(bundle["evidence"], "evidence_id")
    notes = _ids(bundle["notes"], "note_id")
    offenders: list[str] = []
    for table, id_key in (("experiences", "experience_id"), ("projects", "project_id"),
                          ("achievements", "achievement_id"), ("skills", "skill_id")):
        for row in bundle[table]:
            for eid in row.get("evidence_ids", ()):
                if eid not in evidence:
                    offenders.append(f"{table} {row[id_key]} → {eid}")
            for nid in row.get("note_ids", ()):
                if nid not in notes:
                    offenders.append(f"{table} {row[id_key]} → {nid}")
    return _result("证据与笔记引用一致", offenders, "引用了不存在的 Evidence/Note")


def check_prerequisite_ordering(bundle: dict[str, Any]) -> CheckResult:
    """已修课程的先修必须在**更早或同一**学期完成。

    只检查先修表达式里没有 OR / 成绩条件的简单情形——
    复杂表达式的判定属于 Rules Engine，Seed 不越权判定。
    """
    order = {row["course_id"]: row for row in bundle["courses"]}
    completed: dict[tuple[str, str], str] = {}
    for row in bundle["student_course_records"]:
        if row["status"] == "completed":
            completed[(row["student_id"], row["course_id"])] = row["term"]

    offenders: list[str] = []
    for (student_id, course_id), term in sorted(completed.items()):
        expression = order.get(course_id, {}).get("prerequisite_expression")
        if not expression or " OR " in expression.upper() or "Grade" in expression:
            continue
        for code in re.findall(r"\b[A-Z]{4}\s?\d{4}[A-Z]?\b", expression):
            code = re.sub(r"([A-Z]{4})(\d)", r"\1 \2", code)
            prereq_term = completed.get((student_id, code))
            if prereq_term is not None and prereq_term > term:
                offenders.append(f"{student_id}: {course_id}@{term} 先于其先修 {code}@{prereq_term}")
    return _result("先修顺序一致", offenders, "先修晚于本课")


def check_opportunity_ids_unique(bundle: dict[str, Any]) -> CheckResult:
    seen: set[str] = set()
    offenders: list[str] = []
    for row in bundle["opportunities"]:
        if row["opportunity_id"] in seen:
            offenders.append(row["opportunity_id"])
        seen.add(row["opportunity_id"])
    return _result("机会 id 唯一", offenders, "重复的 opportunity_id")


def check_opportunity_tags_unique(bundle: dict[str, Any]) -> CheckResult:
    """标签在单条机会内不得重复——前端拿标签当 React key，重复即报错
    （2026-07-31 用户报障：('internship','internship')）。"""
    offenders = [
        row["opportunity_id"] for row in bundle["opportunities"]
        if len(row["category_tags"]) != len(set(row["category_tags"]))
    ]
    return _result("机会标签无重复", offenders, "category_tags 内有重复")


def check_gold_set_references(bundle: dict[str, Any]) -> CheckResult:
    students = _ids(bundle["students"], "student_id")
    opportunities = _ids(bundle["opportunities"], "opportunity_id")
    courses = _ids(bundle["courses"], "course_id")
    gold = bundle["gold_set"]
    offenders: list[str] = []
    for row in gold["eligibility"]:
        if row["student_id"] not in students:
            offenders.append(f"{row['case_id']} → 学生 {row['student_id']}")
        if row["opportunity_id"] not in opportunities:
            offenders.append(f"{row['case_id']} → 机会 {row['opportunity_id']}")
    for row in gold["course_constraints"]:
        if row["course_id"] not in courses:
            offenders.append(f"{row['case_id']} → 课程 {row['course_id']}")
    for row in gold["memory_regression"]:
        if row["subject_id"] not in opportunities:
            offenders.append(f"{row['case_id']} → 主体 {row['subject_id']}")
    return _result("Gold Set 引用一致", offenders, "Gold Label 指向不存在的实体")


def check_gold_labels_have_reasons(bundle: dict[str, Any]) -> CheckResult:
    """D6.5 规则②：每条标签必须写明判定依据。"""
    offenders = [
        row["case_id"] for row in bundle["gold_set"]["eligibility"] if not row["reasons"]
    ] + [
        row["case_id"] for row in bundle["gold_set"]["course_constraints"] if not row["reasons"]
    ]
    return _result("Gold Label 均有判定依据", offenders, "缺少 reasons")


def check_four_states_covered(bundle: dict[str, Any]) -> CheckResult:
    """四态各有样本，否则 T1 的宏平均与 T2 都测不出东西。"""
    labels = {row["label"] for row in bundle["gold_set"]["eligibility"]}
    expected = {"eligible_now", "future_eligible", "needs_confirmation",
                "ineligible_current_cycle"}
    missing = sorted(expected - labels)
    return _result("四态资格均有 Gold 样本", missing, "缺少该状态的样本")


def check_publisher_references(bundle: dict[str, Any]) -> CheckResult:
    grants = {row["grant_id"]: row for row in bundle["publisher_grants"]}
    principals = {row["principal_id"] for row in bundle["publisher_grants"]}
    submissions = _ids(bundle["publication_submissions"], "submission_id")
    offenders: list[str] = []
    for row in bundle["publication_submissions"]:
        if row["owner_principal_id"] not in principals:
            offenders.append(f"投稿 {row['submission_id']} → 未授权主体")
    for row in bundle["moderation_decisions"]:
        if row["submission_id"] not in submissions:
            offenders.append(f"审核 {row['decision_id']} → 不存在的投稿")
    for row in bundle["scope_violations"]:
        if row["grant_id"] is not None and row["grant_id"] not in grants:
            offenders.append(f"越权记录 {row['violation_id']} → 不存在的授权")
    return _result("发布方引用一致", offenders, "引用不一致")


def check_metric_tuples_deidentified(bundle: dict[str, Any]) -> CheckResult:
    """B10 在数据层的复查。类型层已经挡了一遍，这里挡"绕过类型直接写 JSON"。"""
    banned = {"student_id", "name", "email", "profile", "goal_text", "reflection",
              "calendar", "sleep", "wellbeing"}
    offenders: list[str] = []
    for index, row in enumerate(bundle["metric_tuples"]):
        for key in row:
            if any(term in key.lower() for term in banned):
                offenders.append(f"metric_tuples[{index}].{key}")
    return _result("MetricTuple 已去标识", offenders, "出域元组携带可指向个人的字段")


def check_no_real_pii(bundle: dict[str, Any]) -> CheckResult:
    """合成数据不得出现真实邮箱或电话形状的串（Plan §9）。"""
    offenders: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, str):
            if _EMAIL.search(node):
                offenders.append(f"{path}: 邮箱形状")
            elif _HK_PHONE.search(node):
                offenders.append(f"{path}: 电话形状")
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")

    walk(bundle, "seed")
    return _result("无真实 PII 形状", offenders, "疑似真实个人信息")


def check_synthetic_notice(bundle: dict[str, Any]) -> CheckResult:
    ok = bundle["manifest"].get("notice") == SYNTHETIC_NOTICE
    return CheckResult("Synthetic / Demo Data 标记", ok,
                       "" if ok else "manifest 缺少 Synthetic / Demo Data 标记")


def check_scale_floors(bundle: dict[str, Any]) -> CheckResult:
    # tiny 档是给 smoke 与单测用的（Plan §10.5），本来就不该满足 §11.2 的下限
    if bundle["manifest"].get("scale_profile") != "full":
        return CheckResult("数据规模达到 Spec §11.2 下限", True, "tiny 档跳过")
    counts = {
        "students": len(bundle["students"]),
        "programs": len(bundle["programs"]),
        "catalog_courses": len(bundle["courses"]),
        "internships": sum(1 for o in bundle["opportunities"]
                           if o["type"] in {"internship", "job"}),
        "events": sum(1 for o in bundle["opportunities"]
                      if o["type"] in {"workshop", "event", "club_activity", "mentorship"}),
        "labs": sum(1 for o in bundle["opportunities"] if o["type"] == "research_position"),
        "competitions": sum(1 for o in bundle["opportunities"] if o["type"] == "competition"),
        "historical_feedback": len(bundle["event_quality_feedback"]),
        "publishers": len(bundle["publisher_grants"]),
        "submissions": len(bundle["publication_submissions"]),
        "profile_events": len(bundle["profile_update_proposals"]),
        "moodle_courses": len({r["course_id"] for r in bundle["student_course_records"]}),
    }
    offenders = [
        f"{key} {counts[key]} < {floor}"
        for key, floor in sorted(FULL_SCALE_FLOORS.items())
        if counts.get(key, 0) < floor
    ]
    return _result("数据规模达到 Spec §11.2 下限", offenders, "低于下限")


def check_gold_floors(bundle: dict[str, Any]) -> CheckResult:
    if bundle["manifest"].get("scale_profile") != "full":
        return CheckResult("Gold Set 达到 D6.5 下限", True, "tiny 档跳过")
    gold = bundle["gold_set"]
    counts = {
        "eligibility": len(gold["eligibility"]),
        "course_constraints": len(gold["course_constraints"]),
        "replan": len(gold["replan"]),
        "failure_kinds": len({c["kind"] for c in bundle["failure_cases"]}),
        "memory_regression": len(gold["memory_regression"]),
    }
    offenders = [
        f"{key} {counts[key]} < {floor}"
        for key, floor in sorted(GOLD_SET_FLOORS.items())
        if counts.get(key, 0) < floor
    ]
    return _result("Gold Set 达到 D6.5 下限", offenders, "低于下限")


def check_failure_cases_actionable(bundle: dict[str, Any]) -> CheckResult:
    """每条失败样本都要说明「不许做什么」——只写期望行为无法证伪。"""
    offenders = [
        case["case_id"] for case in bundle["failure_cases"]
        if not case.get("must_not") or not case.get("injected")
    ]
    return _result("失败样本可证伪", offenders, "缺少 must_not 或 injected")


def check_rejected_proposals_not_written(bundle: dict[str, Any]) -> CheckResult:
    """B3 在数据层的复查：被拒绝的提案不得对应版本号变化。"""
    offenders = [
        row["event_id"] for row in bundle["profile_change_events"]
        if row["decision"] == "rejected"
        and (row["profile_version_after"] != row["profile_version_before"]
             or row["changed_fields"])
    ]
    return _result("被拒绝的提案未写入 Profile", offenders, "拒绝却改了版本或字段")


CHECKS: tuple[Check, ...] = (
    check_course_references,
    check_student_references,
    check_evidence_and_note_references,
    check_prerequisite_ordering,
    check_opportunity_ids_unique,
    check_opportunity_tags_unique,
    check_gold_set_references,
    check_gold_labels_have_reasons,
    check_four_states_covered,
    check_publisher_references,
    check_metric_tuples_deidentified,
    check_no_real_pii,
    check_synthetic_notice,
    check_scale_floors,
    check_gold_floors,
    check_failure_cases_actionable,
    check_rejected_proposals_not_written,
)


def run_checks(bundle: dict[str, Any]) -> list[CheckResult]:
    return [check(bundle) for check in CHECKS]


# --------------------------------------------------------------------------
# H5：注入已知矛盾，断言检查器确实会失败
# --------------------------------------------------------------------------

Mutation = tuple[str, Callable[[dict[str, Any]], None], str]


def _invert_prerequisite_order(bundle: dict[str, Any]) -> None:
    """把某门课的先修改成"更晚才修"，制造出先修顺序矛盾。"""
    courses = {row["course_id"]: row for row in bundle["courses"]}
    completed = {
        (row["student_id"], row["course_id"]): row
        for row in bundle["student_course_records"] if row["status"] == "completed"
    }
    for (student_id, course_id), row in sorted(completed.items()):
        expression = courses.get(course_id, {}).get("prerequisite_expression")
        if not expression or " OR " in expression.upper() or "Grade" in expression:
            continue
        for code in re.findall(r"\b[A-Z]{4}\s?\d{4}[A-Z]?\b", expression):
            code = re.sub(r"([A-Z]{4})(\d)", r"\1 \2", code)
            prereq = completed.get((student_id, code))
            if prereq is not None:
                prereq["term"] = "2027-28_SPRING"     # 先修被挪到本课之后
                return
    raise AssertionError("找不到可用于制造先修矛盾的记录——变异样例本身失效了")

MUTATIONS: tuple[Mutation, ...] = (
    ("引用不存在的课程",
     lambda b: b["student_course_records"][0].__setitem__("course_id", "FAKE 9999"),
     "check_course_references"),
    ("引用不存在的学生",
     lambda b: b["goals"][0].__setitem__("student_id", "STU-NOBODY"),
     "check_student_references"),
    ("引用不存在的 Evidence",
     lambda b: b["skills"][0].__setitem__("evidence_ids", ["EV-NOPE"]),
     "check_evidence_and_note_references"),
    ("先修晚于本课",
     lambda b: _invert_prerequisite_order(b),
     "check_prerequisite_ordering"),
    ("审核记录指向不存在的投稿",
     lambda b: b["moderation_decisions"][0].__setitem__("submission_id", "SUB-999"),
     "check_publisher_references"),
    ("机会 id 重复",
     lambda b: b["opportunities"].append(copy.deepcopy(b["opportunities"][0])),
     "check_opportunity_ids_unique"),
    ("机会标签重复",
     lambda b: b["opportunities"][0].__setitem__(
         "category_tags", ["internship", "internship"]),
     "check_opportunity_tags_unique"),
    ("Gold Label 指向已删除的机会",
     lambda b: b["gold_set"]["eligibility"][0].__setitem__("opportunity_id", "OPP-GONE"),
     "check_gold_set_references"),
    ("Gold Label 缺判定依据",
     lambda b: b["gold_set"]["eligibility"][0].__setitem__("reasons", []),
     "check_gold_labels_have_reasons"),
    ("四态缺一",
     lambda b: b["gold_set"].__setitem__(
         "eligibility",
         [r for r in b["gold_set"]["eligibility"] if r["label"] != "future_eligible"]),
     "check_four_states_covered"),
    ("MetricTuple 混入 student_id",
     lambda b: b["metric_tuples"][0].__setitem__("student_id", "STU-A"),
     "check_metric_tuples_deidentified"),
    ("出现真实邮箱形状",
     lambda b: b["notes"][0].__setitem__("text", "联系我 someone@realmail.com"),
     "check_no_real_pii"),
    ("丢失 Synthetic 标记",
     lambda b: b["manifest"].__setitem__("notice", ""),
     "check_synthetic_notice"),
    ("学生数量低于下限",
     lambda b: b.__setitem__("students", b["students"][:3]),
     "check_scale_floors"),
    ("Gold Set 低于下限",
     lambda b: b["gold_set"].__setitem__("eligibility", b["gold_set"]["eligibility"][:5]),
     "check_gold_floors"),
    ("失败样本缺 must_not",
     lambda b: b["failure_cases"][0].__setitem__("must_not", ""),
     "check_failure_cases_actionable"),
    ("被拒绝的提案却改了版本",
     lambda b: next(
         r for r in b["profile_change_events"] if r["decision"] == "rejected"
     ).__setitem__("profile_version_after", 99),
     "check_rejected_proposals_not_written"),
)


def run_selftest(bundle: dict[str, Any]) -> list[tuple[str, bool, str]]:
    """对每个变异，断言**对应的那一项**检查确实失败。

    只断言"有检查失败"是不够的——那样一个过于宽泛的检查会掩盖其他检查全都失效。
    """
    results: list[tuple[str, bool, str]] = []
    by_name = {check.__name__: check for check in CHECKS}
    for label, mutate, expected_check in MUTATIONS:
        mutated = copy.deepcopy(bundle)
        mutate(mutated)
        check = by_name[expected_check]
        try:
            outcome = check(mutated)
            caught = not outcome.ok
            detail = outcome.detail
        except Exception as exc:                      # 检查器自己炸了也算没抓住
            caught = False
            detail = f"检查器抛异常：{exc!r}"
        results.append((f"{label} → {expected_check}", caught, detail))
    return results
