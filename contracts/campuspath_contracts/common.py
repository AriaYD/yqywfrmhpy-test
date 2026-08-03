"""共享基础类型：ID、枚举、来源、基类。

设计原则（对应 Spec §8.9 与 Plan D6）：

1. 所有模型 ``extra="forbid"``。契约是白名单，不是建议——多传一个字段就应该报错，
   否则 "MetricTuple 不含 student_id" 这类断言在类型层根本无法成立。
2. 边界模型（跨数据域传递的）额外由 ``guards.py`` 做字段名扫描，
   防止有人日后加一个 ``notes: str`` 就把日历详情带出域。
3. 不在契约层做任何排序/评分。分数只允许出现在 A5 的输出模型上（Spec §8.1 A2 行）。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# 契约版本。任何破坏性字段变更都必须同步 bump，并在 CHANGELOG 记录。
CONTRACTS_VERSION = "1.35.0"

# --------------------------------------------------------------------------
# 标识符
# --------------------------------------------------------------------------

_ID = StringConstraints(strip_whitespace=True, min_length=1, max_length=128)

Identifier = Annotated[str, _ID]
StudentId = Annotated[str, _ID]
CourseId = Annotated[str, _ID]
OpportunityId = Annotated[str, _ID]
EvidenceId = Annotated[str, _ID]
NoteId = Annotated[str, _ID]
RequirementId = Annotated[str, _ID]
GoalId = Annotated[str, _ID]
EventId = Annotated[str, _ID]

#: Rules & Constraint Engine 签发的校验凭据。格式固定，便于 API 层先做廉价的形状检查，
#: 再由 :class:`ValidationRegistry` 做"是否真的被签发过"的检查（Spec §8.9.3）。
VALIDATION_ID_PATTERN = r"^val_[0-9a-f]{32}$"
ValidationId = Annotated[str, StringConstraints(pattern=VALIDATION_ID_PATTERN)]

#: 学期标识，例如 ``2025-26_FALL``。与 HKUST 课程目录的 term 编码对齐。
TERM_PATTERN = r"^\d{4}-\d{2}_(FALL|WINTER|SPRING|SUMMER)$"
TermCode = Annotated[str, StringConstraints(pattern=TERM_PATTERN)]

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
"""0–1 的置信度。不允许 >1 的"120% 确定"。"""


def is_wellformed_validation_id(value: str) -> bool:
    """形状检查。**不代表该 id 真的被 Rules 签发过**——那是 Registry 的职责。"""
    return bool(re.match(VALIDATION_ID_PATTERN, value))


# --------------------------------------------------------------------------
# 枚举
# --------------------------------------------------------------------------


class StrEnum(str, Enum):
    """序列化为字符串的枚举，JSON Schema 里表现为 ``enum`` 而非整数。"""

    def __str__(self) -> str:  # pragma: no cover - 仅便于日志阅读
        return str(self.value)


class DataDomain(StrEnum):
    """Spec §13.2 的数据域。跨域传递必须经过显式的边界模型。"""

    STUDENT_PRIVATE = "student_private"
    STUDENT_OPERATIONAL = "student_operational"
    CALENDAR = "calendar"
    WELLBEING = "wellbeing"
    ACADEMIC = "academic"
    CATALOG_PUBLIC = "catalog_public"
    AGGREGATED_INSIGHTS = "aggregated_insights"


class VerificationStatus(StrEnum):
    """Spec §8.2.3：不把上传文件自动当成学校认证。"""

    SELF_REPORTED = "self_reported"
    SOURCE_IMPORTED = "source_imported"
    INSTITUTION_VERIFIED = "institution_verified"
    EXPIRED = "expired"
    DISPUTED = "disputed"


class Visibility(StrEnum):
    PRIVATE = "private"
    SHARED_WITH_ADVISOR = "shared_with_advisor"
    INSTITUTION_VISIBLE = "institution_visible"


class DevelopmentModeType(StrEnum):
    EMPLOYMENT = "employment"
    ACADEMIA = "academia"
    ENTREPRENEURSHIP = "entrepreneurship"
    PERSONAL_INTEREST = "personal_interest"
    EXPLORATION = "exploration"


class IntensityMode(StrEnum):
    """学生选择的计划强度（Spec §16.7）。"""

    GENTLE = "gentle"
    BALANCED = "balanced"
    SPRINT = "sprint"


class Uncertainty(StrEnum):
    """字段级不确定性。``NEEDS_CONFIRMATION`` 永远不能被当成淘汰依据（Spec §16.2）。"""

    NONE = "none"
    LOW_CONFIDENCE = "low_confidence"
    MISSING_SOURCE_FIELD = "missing_source_field"
    CONFLICTING_SOURCES = "conflicting_sources"
    NEEDS_CONFIRMATION = "needs_confirmation"


class ActorRole(StrEnum):
    """RBAC 角色（Plan WP5）。"""

    STUDENT = "student"
    PUBLISHER = "publisher"
    REVIEWER = "reviewer"
    CURATOR = "curator"
    CONNECTOR_ADMIN = "connector_admin"
    #: R6-B（2026-08-01）：Career Center 现实中一人身兼审核/策展/接入三职——
    #: 登录入口合并为一个复合岗位。原三角色保留（真实部署可拆开）。
    CAREER_CENTER_ADMIN = "career_center_admin"
    WELLBEING_COORDINATOR = "wellbeing_coordinator"
    ADVISOR = "advisor"
    SECURITY_ADMIN = "security_admin"
    SYSTEM = "system"


class AgentId(StrEnum):
    """6 个语义 Agent（Spec §8.1）。数量固定，新增需改 Spec。"""

    A0_ORCHESTRATOR = "A0"
    A1_STUDENT_CONTEXT = "A1"
    A2_ACADEMIC = "A2"
    A3_GOAL_GAP = "A3"
    A4_OPPORTUNITY = "A4"
    A5_PATHWAY = "A5"


class RuntimeId(StrEnum):
    """2 个 Runtime（Spec §8.1）。A4 独立部署是安全边界，不是性能优化。"""

    STUDENT_PATH = "student_path_runtime"
    OPPORTUNITY_OPS = "opportunity_ops_runtime"


class Locale(StrEnum):
    """UI 双语要求（Plan §2）。契约层只承载 locale 标签，不承载文案。"""

    ZH_HANS = "zh-Hans"
    EN = "en"


# --------------------------------------------------------------------------
# 基类
# --------------------------------------------------------------------------


class CampusPathModel(BaseModel):
    """所有契约模型的基类。

    ``extra="forbid"`` 是本项目多条 BLOCKER 的类型层地基（B4/B5/B10）：
    自由文本或日历详情"顺手多带一个字段"这种事，在反序列化时就会失败。

    ``validate_assignment=True`` 让 ``obj.field = x`` 也重跑 validator。
    但 pydantic 的 ``model_copy(update=...)`` **不**校验，而它在本仓库里
    已经是惯用法——于是 B1/B2/B3/B6/B9 全都能被一行代码翻掉：

        approved = proposal.model_copy(update={"student_decision": "approved"})

    所以这里覆写它：带 ``update`` 的复制走完整校验。
    ``model_construct`` 仍然不校验，那是 pydantic 明示的"我知道我在做什么"出口，
    评测里需要它来构造违规样本；区别在于它得写出来，不会被顺手用到。
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        use_enum_values=False,
        frozen=False,
    )

    def model_copy(self, *, update: Any = None, deep: bool = False):  # type: ignore[override]
        if not update:
            return super().model_copy(deep=deep)
        merged = {**self.model_dump(), **dict(update)}
        return type(self).model_validate(merged)


class FrozenModel(CampusPathModel):
    """已签发即不可变的记录（校验凭据、审计事件）。

    ``frozen=True`` 挡住赋值，但挡不住 ``model_copy(update=...)``——
    审查实测：一条 verdict=violated 的 ``ConstraintValidation`` 可以被复制成
    satisfied 且**保留同一个 validation_id**，Registry 会为这份伪造背书。
    所以这里直接拒绝带 update 的复制：改判必须重新签发，审计链才不会断。
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        frozen=True,
    )

    def model_copy(self, *, update: Any = None, deep: bool = False):  # type: ignore[override]
        if update:
            raise TypeError(
                f"{type(self).__name__} 是不可变记录，不能用 model_copy(update=...) 改判。"
                "需要不同的内容就新建一条——否则同一个 id 会指向两种事实。"
            )
        return super().model_copy(deep=deep)


class Provenance(CampusPathModel):
    """Spec §14.3。任何进入 Catalog 的事实都必须能回溯到这里。"""

    source: str = Field(description="来源系统或站点标识")
    source_url: str | None = Field(default=None, description="官方页面 URL")
    retrieved_at: datetime
    published_at: datetime | None = None
    parser_version: str
    evidence_snippet: str | None = Field(
        default=None,
        max_length=2000,
        description="支撑该结论的原文片段，用于 Unsupported Key Claim 复核（T8）",
    )
    confidence: Confidence = 1.0


class SourceRef(CampusPathModel):
    """指向某个实体的稳定引用，用于 ConstraintValidation 的 ``subject_ref``。"""

    entity_type: str
    entity_id: Identifier
    entity_version: str | None = None


class DateRange(CampusPathModel):
    start: date
    end: date | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError("end 早于 start")


class TimeRange(CampusPathModel):
    start: datetime
    end: datetime

    def model_post_init(self, __context: Any) -> None:
        if self.end <= self.start:
            raise ValueError("end 不晚于 start")

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60.0


class LocalizedText(CampusPathModel):
    """需要在 UI 展示的系统生成文案，两种语言都必须存在（Plan §2 UI 语言）。

    学生自己写的内容（Note、Reflection）**不用**这个类型——那是原文，不翻译。
    """

    zh_Hans: str = Field(min_length=1)
    en: str = Field(min_length=1)

    def get(self, locale: Locale) -> str:
        return self.zh_Hans if locale is Locale.ZH_HANS else self.en


class DataUncertainty(CampusPathModel):
    """A2 的产出之一：明确说"这个字段我不确定"，而不是猜一个值填上（Spec §8.1.1）。"""

    field_path: str
    kind: Uncertainty
    detail: LocalizedText | None = None
    suggested_action: Literal[
        "ask_student", "consult_advisor", "check_source", "none"
    ] = "none"
