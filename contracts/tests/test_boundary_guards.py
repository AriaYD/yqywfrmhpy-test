"""数据域边界的字段级断言：B4 / B5 / B10，以及扫描器自身的自检（Plan §10 H5）。

这些测试断言的是**字段根本不存在**，不是"运行时没填"。
区别很重要：后者靠纪律，前者靠类型。
"""

from __future__ import annotations

import pydantic
import pytest
from pydantic import BaseModel

from campuspath_contracts.aggregation import MetricTuple, ResourceCoverageAggregate
from datetime import datetime, timezone

from pydantic import ValidationError

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CalendarConnection,
    CalendarDetailLevel,
    CapacitySnapshot,
    ScheduleProposal,
)
from campuspath_contracts.common import TimeRange
from campuspath_contracts.guards import (
    CALENDAR_DETAIL_TERMS,
    CREDENTIAL_TERMS,
    FREE_TEXT_TERMS,
    RANKING_TERMS,
    STUDENT_IDENTITY_TERMS,
    WELLBEING_TERMS,
    BoundaryViolation,
    assert_no_forbidden_fields,
    find_forbidden_fields,
    walk_fields,
)
from campuspath_contracts.academic import AnnotatedCourseCandidate
from campuspath_contracts.reflection import EventQualityFeedback
from campuspath_contracts.wellbeing import OutreachEmailFields


# --------------------------------------------------------------------------
# H5：先证明扫描器真的会失败
# --------------------------------------------------------------------------


class _KnownBadCalendarBlock(BaseModel):
    """已知会失败的样例。如果扫描器放过它，说明扫描器本身坏了。"""

    block_id: str
    event_title: str          # ← 应该被 CALENDAR_DETAIL_TERMS 抓到
    attendee_emails: list[str]  # ← 同上


class _KnownBadNested(BaseModel):
    """嵌套一层的坏样例：证明扫描器不只看顶层字段。"""

    ok_field: str
    nested: _KnownBadCalendarBlock


def test_scanner_catches_known_bad_model():
    hits = find_forbidden_fields(_KnownBadCalendarBlock, CALENDAR_DETAIL_TERMS)
    names = {h.name for h in hits}
    assert names == {"event_title", "attendee_emails"}, f"扫描器漏抓：{names}"


def test_scanner_recurses_into_nested_models():
    hits = find_forbidden_fields(_KnownBadNested, CALENDAR_DETAIL_TERMS)
    assert {h.name for h in hits} == {"event_title", "attendee_emails"}
    assert any(h.path.startswith("_KnownBadNested.nested") for h in hits)


def test_scanner_raises_with_useful_message():
    with pytest.raises(BoundaryViolation) as excinfo:
        assert_no_forbidden_fields(
            _KnownBadCalendarBlock, CALENDAR_DETAIL_TERMS, reason="自检"
        )
    assert "event_title" in str(excinfo.value)


def test_allow_paths_exemption_is_honoured():
    hits = find_forbidden_fields(
        _KnownBadCalendarBlock,
        CALENDAR_DETAIL_TERMS,
        allow_paths={"_KnownBadCalendarBlock.event_title"},
    )
    assert {h.name for h in hits} == {"attendee_emails"}


def test_walk_terminates_on_recursive_models():
    """自引用模型不能让遍历打转。"""

    class Recursive(BaseModel):
        name: str
        parent: "Recursive | None" = None

    Recursive.model_rebuild()
    nodes = list(walk_fields(Recursive))
    assert len(nodes) < 10


# --------------------------------------------------------------------------
# B5：日历详情不出 Capacity & Calendar Service
# --------------------------------------------------------------------------

#: 唯一豁免。``CalendarWriteDraft.event_title`` 是 CampusPath 生成、学生预览后写回的
#: 事件名称，不是从学生日历读取并保存的标题。B5 禁止的是后者。
_CALENDAR_WRITE_EXEMPTIONS = frozenset(
    {
        "ScheduleProposal.calendar_action_ids",  # 只是 id，不含内容
    }
)


@pytest.mark.parametrize("model", [CalendarConnection, CapacitySnapshot])
def test_calendar_models_carry_no_event_detail(model):
    assert_no_forbidden_fields(
        model, CALENDAR_DETAIL_TERMS, reason="B5：采集不得超出授权层级"
    )


#: ``AvailabilityBlock.title`` 是 2026-07-30 由用户决定引入的**二级授权**字段。
#: 它不再是"永远不该存在"，而是"没授权就不许有值"——后者由
#: ``AvailabilityBlock._title_requires_grant`` 在类型层强制，
#: 下面两条测试就是在测那道强制，而不是靠字段名扫描。
_AVAILABILITY_TIER_TWO_EXEMPTIONS = frozenset({
    "AvailabilityBlock.title",
    # A（2026-07-31）：学生编辑自己视图块的补丁。服务端把补丁套到原块后
    # **整块重新校验**，_title_requires_grant 照常生效——没授权二级的块
    # 依然装不上标题，所以这里豁免的是"编辑入口"，不是授权约束本身。
    "AvailabilityBlockPatch.title",
})


def test_availability_block_has_no_detail_beyond_the_granted_title():
    assert_no_forbidden_fields(
        AvailabilityBlock,
        CALENDAR_DETAIL_TERMS,
        allow_paths=_AVAILABILITY_TIER_TWO_EXEMPTIONS,
        reason="B5：除已授权的标题外，仍然没有参与人/地点/备注",
    )


def test_a_title_without_the_grant_cannot_be_constructed():
    """B5 现在的形态：**采集不得超出授权层级**。

    这条用一个**已知违规**的输入证明闸门真的会拒——
    没有它，"类型层保证"就只是一句注释。
    """
    span = TimeRange(
        start=datetime(2026, 9, 16, 9, tzinfo=timezone.utc),
        end=datetime(2026, 9, 16, 11, tzinfo=timezone.utc),
    )
    common = dict(
        block_id="B", student_id="STU-A", span=span,
        type=AvailabilityType.BUSY, source=BlockSource.CALENDAR_FREEBUSY,
    )
    with pytest.raises(ValidationError):
        AvailabilityBlock(**common, title="Weekly sync")

    granted = AvailabilityBlock(
        **common, detail_level=CalendarDetailLevel.EVENT_TITLES, title="Weekly sync"
    )
    assert granted.title == "Weekly sync"


def test_schedule_proposal_carries_no_event_detail():
    assert_no_forbidden_fields(
        ScheduleProposal,
        CALENDAR_DETAIL_TERMS,
        allow_paths=_CALENDAR_WRITE_EXEMPTIONS,
        reason="B5",
    )


def test_calendar_action_detail_is_limited_to_the_one_exemption():
    """写回日历的动作里，唯一允许的"内容"字段是我们自己生成的 event_title。

    再多一个（location / description / attendees）就说明有人把读来的详情
    顺手放进了写入路径。
    """
    from campuspath_contracts.calendar import CalendarAction

    hits = find_forbidden_fields(CalendarAction, CALENDAR_DETAIL_TERMS)
    assert {h.path for h in hits} == {"CalendarAction.draft.event_title"}, (
        f"CalendarAction 的日历详情字段超出唯一豁免：{[h.path for h in hits]}"
    )


def test_calendar_connection_has_no_credential_field():
    """Token 止步于服务内部，连字段都不该存在（CLAUDE.md 架构第 3 条）。

    此前这条是**集合相等**：只命中完全同名的字段，``oauth_token`` 与
    ``bearer`` 直接放行，而 CALENDAR_DETAIL_TERMS 里根本没有凭据类词——
    "Calendar Token 不进 LLM 上下文"在契约层没有一个能工作的检查。
    """
    assert_no_forbidden_fields(
        CalendarConnection, CREDENTIAL_TERMS, reason="日历凭据不得出现在契约里"
    )


@pytest.mark.parametrize(
    "model", [CalendarConnection, AvailabilityBlock, CapacitySnapshot, ScheduleProposal]
)
def test_no_calendar_model_carries_credentials(model):
    assert_no_forbidden_fields(model, CREDENTIAL_TERMS, reason="B5 / 架构第 3 条")


def test_credential_scan_catches_the_lookalikes_it_used_to_miss():
    """H5：拿审查者实测能过的两个字段名验证这次真的抓得住。"""

    class _WithOauthToken(BaseModel):
        connection_id: str
        oauth_token: str

    class _WithBearer(BaseModel):
        connection_id: str
        bearer: str

    for model in (_WithOauthToken, _WithBearer):
        assert find_forbidden_fields(model, CREDENTIAL_TERMS), model.__name__


def test_calendar_write_exemptions_are_pinned_exactly():
    """豁免集合此前只靠"写在测试里所以 diff 可见"防守——

    审查实测：往 ScheduleProposal 加一个 event_summary，同时往豁免集合加一行，
    全绿。同一个文件里另一条用的是精确集合相等，弱的这条没有理由。
    """
    assert _CALENDAR_WRITE_EXEMPTIONS == frozenset(
        {"ScheduleProposal.calendar_action_ids"}
    )


# --------------------------------------------------------------------------
# B10 / B4：出域元组与聚合输入
# --------------------------------------------------------------------------


def test_metric_tuple_has_no_student_identity():
    assert_no_forbidden_fields(
        MetricTuple, STUDENT_IDENTITY_TERMS, reason="B10 MetricTuple Field Leakage"
    )


def test_metric_tuple_has_no_wellbeing_fields():
    assert_no_forbidden_fields(MetricTuple, WELLBEING_TERMS, reason="B10 / §17.1.2 边界 4")


def test_metric_tuple_has_no_calendar_fields():
    assert_no_forbidden_fields(MetricTuple, CALENDAR_DETAIL_TERMS, reason="B10")


def test_metric_tuple_carries_categories_not_free_text():
    """``uncovered_requirement_categories`` 必须是枚举——自由文本能反推到个人。"""
    from campuspath_contracts.goals import RequirementCategory

    field = MetricTuple.model_fields["uncovered_requirement_categories"]
    assert "RequirementCategory" in str(field.annotation)
    assert issubclass(RequirementCategory, str)


def test_event_quality_feedback_has_no_free_text():
    assert_no_forbidden_fields(
        EventQualityFeedback, FREE_TEXT_TERMS, reason="B4 Private Reflection Exposure"
    )


def test_event_quality_feedback_has_no_student_identity():
    assert_no_forbidden_fields(
        EventQualityFeedback, STUDENT_IDENTITY_TERMS, reason="§8.9.2 A1 输出类型边界"
    )


def test_resource_coverage_aggregate_has_no_individual_fields():
    assert_no_forbidden_fields(
        ResourceCoverageAggregate, STUDENT_IDENTITY_TERMS, reason="B9 / B10"
    )
    assert_no_forbidden_fields(ResourceCoverageAggregate, WELLBEING_TERMS, reason="B9")


def test_outreach_email_fields_are_a_whitelist():
    """Spec §16.8.4：邮件字段就这六项，多一项都不行。"""
    assert set(OutreachEmailFields.model_fields) == {
        "internal_student_ref",
        "student_requested_contact",
        "trigger_category",
        "triggered_at",
        "consent_receipt_id",
        "acknowledgement_url",
    }


def test_outreach_email_rejects_extra_field():
    """extra="forbid" 必须真的生效，而不只是写在 config 里。"""
    import pydantic

    from campuspath_contracts.wellbeing import WellbeingSignalType

    with pytest.raises(pydantic.ValidationError):
        OutreachEmailFields(
            internal_student_ref="ref-1",
            student_requested_contact=True,
            trigger_category=WellbeingSignalType.CAPACITY_OVERLOAD,
            triggered_at="2026-07-29T09:00:00Z",
            consent_receipt_id="consent-1",
            acknowledgement_url="https://example.test/ack",
            course_title="COMP 2011 Programming",  # ← 明令禁止
        )


# --------------------------------------------------------------------------
# A2 不排序
# --------------------------------------------------------------------------


def test_every_calendar_model_is_scanned_not_just_a_hardcoded_list():
    """审查实测：往 calendar.py 新增一个 RawCalendarEvent{title, attendee_emails,
    location, access_token}，165 个语义测试**全绿**——因为扫描列表是手写的。
    改成遍历模块里的全部契约模型。
    """
    import campuspath_contracts.calendar as calendar_module
    from campuspath_contracts import ROOT_MODELS

    models = [
        model for name, model in ROOT_MODELS.items()
        if model.__module__ == calendar_module.__name__
    ]
    assert len(models) >= 8, f"只扫到 {len(models)} 个日历模型，列表可能失效"
    for model in models:
        assert_no_forbidden_fields(
            model, CALENDAR_DETAIL_TERMS,
            allow_paths=(
                _CALENDAR_WRITE_EXEMPTIONS
                | _AVAILABILITY_TIER_TWO_EXEMPTIONS
                | {"CalendarWriteDraft.event_title",
                   "CalendarAction.draft.event_title",
                   # 二级授权的标题会随区块一路传到排程预览里
                   "ScheduleProposal.proposed_slots.conflicts.with_block_id"}
            ),
            reason=f"B5（{model.__name__}）",
        )
        # **架构第 3 条不随授权分级而放宽**：凭据永远不进契约，
        # 二级授权放行的是标题文本，不是 token。
        assert_no_forbidden_fields(model, CREDENTIAL_TERMS, reason="架构第 3 条")


def test_metric_tuple_field_set_is_pinned():
    """B10 说的是"字段白名单"。此前只有 OutreachEmailFields 做了精确集合断言，
    MetricTuple 只有子串扫描——加一个 origin_hash 全绿。"""
    assert set(MetricTuple.model_fields) == {
        "period", "cohort_dims", "eligible_count", "seen_count", "acted_count",
        "gap_total", "gap_covered", "uncovered_requirement_categories",
    }


def test_event_quality_feedback_field_set_is_pinned():
    """B4 的全部依据就是这个类型不含自由文本。加一个 learning_summary 曾经全绿。"""
    assert set(EventQualityFeedback.model_fields) == {
        "feedback_id", "occurrence_id", "series_id", "verified_attendance",
        "verification_ref", "dimensions", "fit_tags", "cohort_dims", "submitted_at",
    }


def test_cohort_dims_are_constrained_types_not_free_text():
    """§17.1.2 要求"仅粗粒度分组"。裸 str 时
    school="ENGG/COMP/AI-track/2024-intake/GPA3.7-3.8" 完全合法。"""
    from campuspath_contracts.common import DevelopmentModeType
    from campuspath_contracts.reflection import CohortDims

    with pytest.raises(pydantic.ValidationError):
        CohortDims(school="ENGG/COMP/AI-track/2024", year_level=2,
                   development_mode=DevelopmentModeType.EMPLOYMENT)
    with pytest.raises(pydantic.ValidationError):
        CohortDims(school="ENGG", year_level=2,
                   development_mode="想去 CMU 读博，只跟导师说过")


def test_verification_ref_must_be_opaque():
    """改名把字段从扫描器眼前挪走，但没让"不透明"变成可校验的。"""
    from campuspath_contracts.reflection import CohortDims, DimensionRating, QualityDimension
    from campuspath_contracts.common import DevelopmentModeType

    def build(ref):
        return EventQualityFeedback(
            feedback_id="F-1", occurrence_id="OCC-1", verified_attendance=True,
            verification_ref=ref,
            dimensions=(DimensionRating(dimension=QualityDimension.CONTENT_DEPTH, rating=4),),
            cohort_dims=CohortDims(school="ENGG", year_level=2,
                                   development_mode=DevelopmentModeType.EMPLOYMENT),
            submitted_at="2026-09-15T10:00:00Z",
        )

    with pytest.raises(pydantic.ValidationError):
        build("EV-STUDENT-S001-transcript-upload")
    assert build("ver_" + "a" * 16).verification_ref.startswith("ver_")


def test_response_envelope_payload_cannot_carry_private_content():
    """唯一的 Any 逃逸口，也正好开在所有面向学生响应的外壳上。"""
    from campuspath_contracts.agents import ResponseEnvelope
    from campuspath_contracts.common import Locale

    with pytest.raises(pydantic.ValidationError):
        ResponseEnvelope(
            envelope_id="E-1", student_id="S-1", locale=Locale.EN,
            payload_type="MatchResult[]",
            payload={"private_text": "我最近很崩溃", "calendar_event_title": "Therapy"},
            generated_at="2026-09-15T10:00:00Z",
        )


def test_walk_fields_refuses_an_unrebuilt_model():
    """前向引用没解析时，字段注解还是字符串，扫描器会一无所获——
    静默失明比报错危险得多，因为边界检查会"通过"。"""
    class _Lazy(BaseModel):
        model_config = {"defer_build": True}
        name: str

    _Lazy.__pydantic_complete__ = False
    with pytest.raises(BoundaryViolation):
        list(walk_fields(_Lazy))


def test_annotated_course_candidate_has_no_ranking_fields():
    """Spec §8.1：A2 只出事实与候选，不排序。排序是 A5 的独占职责。"""
    assert_no_forbidden_fields(
        AnnotatedCourseCandidate, RANKING_TERMS, reason="A5 是唯一排序者"
    )
