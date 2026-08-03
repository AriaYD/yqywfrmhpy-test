"""F27：Context Pack 与 Career Path Pack 的清单契约（Spec §14.4、§15.4 规则 14）。

关键规则：**Pack 未安装或来源过期时，系统返回 `Context unavailable /
Needs confirmation`，不能让模型自行补政策。** 这是 T8（Unsupported Key Claim）
在国际学生签证这类高风险领域的具体落点。

MVP 只实装 ``undergrad-direct-employment`` 一个 Career Path Pack；
International Student Context Pack 与 ``phd-to-industry`` 只演示加载/卸载机制
（Plan §6 假设 5）。因此本模块给出的是**机制**，不是任何政策内容。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import CampusPathModel, Identifier, LocalizedText, Provenance, StrEnum


class PackKind(StrEnum):
    CONTEXT_PACK = "context_pack"
    CAREER_PATH_PACK = "career_path_pack"


class PackAvailability(StrEnum):
    """Pack 不可用时的三种状态。任何一种都不允许模型代为补全内容。"""

    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    SOURCE_EXPIRED = "source_expired"


class PackRule(CampusPathModel):
    rule_id: Identifier
    description: LocalizedText
    required_evidence: tuple[str, ...] = ()
    official_source: Provenance | None = None

    @model_validator(mode="after")
    def _rule_needs_a_source(self) -> "PackRule":
        if self.official_source is None:
            raise ValueError(
                "Pack 规则必须附官方来源——没有来源的政策条款不得进入系统（§15.4 规则 14）"
            )
        return self


class ContextPackManifest(CampusPathModel):
    pack_id: Identifier
    kind: PackKind
    version: str
    jurisdiction: str | None = None
    applicability: tuple[str, ...] = Field(
        default=(), description="适用条件，例如 'international_student'"
    )
    fields: tuple[str, ...] = ()
    rules: tuple[PackRule, ...] = ()
    official_sources: tuple[Provenance, ...] = ()
    effective_from: date
    review_at: date
    uncertainty_policy: Literal["needs_confirmation", "block"] = "needs_confirmation"
    availability: PackAvailability = PackAvailability.AVAILABLE

    def is_usable_on(self, when: date) -> bool:
        return (
            self.availability is PackAvailability.AVAILABLE
            and self.effective_from <= when <= self.review_at
        )


class PackResolution(CampusPathModel):
    """A0 加载 Pack 的结果。不可用时**必须**返回可展示的说明，而不是静默跳过。"""

    pack_id: Identifier
    availability: PackAvailability
    resolved_at: datetime
    message: LocalizedText | None = None

    @model_validator(mode="after")
    def _unavailable_must_explain(self) -> "PackResolution":
        if self.availability is not PackAvailability.AVAILABLE and self.message is None:
            raise ValueError(
                "Pack 不可用时必须给出 Context unavailable / Needs confirmation 的说明"
            )
        return self


# --------------------------------------------------------------------------
# International Student Context Pack 求值信封（B，2026-08-02）
# --------------------------------------------------------------------------
# vendored 求值器（services/packs）的输出契约化。前端只消费这个信封：
# 不读原始 YAML、不合并政策规则、不重算资格（integration-contract 的
# frontend boundary）。`rules_validation_id` 是 Rules 签发的真凭据（B8）；
# `pack_digest` 是 Pack 自铸的 VAL-*，仅留痕，不作凭据。


class PackSourceLink(CampusPathModel):
    source_id: Identifier
    title: str = Field(max_length=200)
    url: str = Field(max_length=500)
    last_checked_at: str = Field(max_length=40)


class PackPreparationAction(CampusPathModel):
    preparation_action_id: Identifier
    category: str = Field(max_length=40)
    title: str = Field(max_length=200)
    description: str = Field(max_length=1000)
    recommended_lead_time_days: int | None = Field(default=None, ge=0)
    mandatory: bool = False
    source_ids: tuple[str, ...] = ()


class PackSupportItem(CampusPathModel):
    support_item_id: Identifier
    category: str = Field(max_length=40)
    title: str = Field(max_length=200)
    provider: str = Field(max_length=200)
    eligibility_summary: str = Field(max_length=500)
    application_required: bool = False
    deadline: str | None = Field(default=None, max_length=40)
    source_ids: tuple[str, ...] = ()


class PackPathwayImpact(CampusPathModel):
    impact_id: Identifier
    rule_ids: tuple[str, ...] = ()
    pathway_segment_id: str = Field(max_length=80)
    impact_type: Literal["add_preparation_action", "add_confirmation"]
    summary: str = Field(max_length=500)


class ContextPackEvaluation(CampusPathModel):
    """求值信封（前端唯一消费面）。展示要求：辖区、Pack 版本、最近核验日期、
    来源链接、复核状态与**非法律建议免责声明**缺一不可。"""

    installed: bool
    applicable: bool
    consented: bool
    pack_current: bool
    eligibility_state: Literal[
        "eligible_now", "future_eligible", "needs_confirmation",
        "ineligible_current_cycle",
    ]
    headline_key: str = Field(max_length=60)
    jurisdiction: str | None = Field(default=None, max_length=20)
    pack_version: str | None = Field(default=None, max_length=20)
    last_verified_at: str | None = Field(default=None, max_length=40)
    applicable_rule_ids: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    preparation_actions: tuple[PackPreparationAction, ...] = ()
    support_items: tuple[PackSupportItem, ...] = ()
    source_links: tuple[PackSourceLink, ...] = ()
    pathway_impacts: tuple[PackPathwayImpact, ...] = ()
    #: Pack 自铸 digest（留痕）；不是凭据，B8 不认它
    pack_digest: str = Field(max_length=40)
    #: Rules 签发的真凭据（campuspath_rules.context_pack 桥）
    rules_validation_id: str = Field(max_length=60)
    review_required: bool
    evaluated_at: datetime
