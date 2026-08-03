"""Rules & Constraint Engine 的校验凭据与绑定规则（Spec §8.9.3）。

这是 B8 `Unbacked Plan Item = 0` 的类型层实现。分两层：

* **形状层**：``ValidationId`` 的正则。缺失或格式错的 id 在反序列化时就失败。
* **签发层**：``ValidationRegistry.verify()``。防的是"模型编了一个格式正确的 id"。
  API 层在接受 A5 输出前必须调用它——只有形状检查挡不住伪造。

Rules Engine 本身零 LLM，本模块也因此不得 import 任何模型 SDK。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from pydantic import Field

from .common import (
    CampusPathModel,
    FrozenModel,
    Identifier,
    LocalizedText,
    SourceRef,
    StrEnum,
    ValidationId,
)


class Verdict(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NEEDS_CONFIRMATION = "needs_confirmation"
    NOT_APPLICABLE = "not_applicable"


class RuleCategory(StrEnum):
    """Spec §8.1 Rules & Constraint Engine 的职责范围。"""

    ELIGIBILITY = "eligibility"
    PREREQUISITE = "prerequisite"
    CREDIT = "credit"
    DEADLINE = "deadline"
    CAPACITY = "capacity"
    PROTECTED_BLOCK = "protected_block"
    OFFERING = "offering"
    SCHEDULE_CONFLICT = "schedule_conflict"
    CONTEXT_PACK = "context_pack"
    WELLBEING_THRESHOLD = "wellbeing_threshold"


class ValidationReason(CampusPathModel):
    """一条判定依据。``rule_id`` 必须能在 rule set 中查到，不能是模型生成的散文。"""

    rule_id: Identifier
    category: RuleCategory
    verdict: Verdict
    message: LocalizedText
    observed: str | None = Field(default=None, description="实测值，例如 '已修 9 学分'")
    expected: str | None = Field(default=None, description="要求值，例如 '需 12 学分'")


class ConstraintValidation(FrozenModel):
    """Rules & Constraint Engine 每次校验的签发结果（Spec §14.2）。

    不可变：一旦签发就不能改判。改判必须重新签发一个新的 validation_id，
    否则审计链会断。
    """

    validation_id: ValidationId
    rule_set_version: str
    subject_ref: SourceRef
    verdict: Verdict
    reasons: tuple[ValidationReason, ...] = ()
    evaluated_at: datetime
    expires_at: datetime | None = Field(
        default=None,
        description="超过该时间需重新校验（例如名额、截止日期类规则）",
    )

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or datetime.now(timezone.utc)) > self.expires_at

    def decision_key(self) -> tuple:
        """判定本身，**不含计算时刻**。

        "同一个 id 不可改判"说的是判定不能变，不是"不能重新算一次"。
        `deterministic_validation_id` 只由（规则集 + 主体）决定，而
        ``evaluated_at`` 每次调用都不同——把时刻算进同一性，
        同一个端点被调用两次就会炸（实测过：why-not-recommended 第二次 500）。
        """
        return (
            self.rule_set_version,
            self.subject_ref.entity_type,
            self.subject_ref.entity_id,
            self.subject_ref.entity_version,
            self.verdict,
            tuple((r.rule_id, r.verdict, r.observed, r.expected) for r in self.reasons),
            self.expires_at,
        )


def new_validation_id() -> ValidationId:
    """生成符合 ``VALIDATION_ID_PATTERN`` 的新 id。只应由 Rules Engine 调用。"""
    return f"val_{uuid.uuid4().hex}"


def deterministic_validation_id(
    rule_set_version: str, subject_ref: SourceRef, context: str = ""
) -> ValidationId:
    """同一 rule set + 同一 subject + 同一 context 得到同一 id。

    D6.7 要求"固定 Seed 可复现两次数字一致"；随机 id 会让 report 的 diff 永远不为空。

    ``context`` 是 2026-07-30 由评测 harness 抓出来的缺口。此前 id 只由
    （规则集 + 主体）决定，而**先修判定的结论取决于是谁在问**——
    同一门 COMP 2011，修过它的学生得 SATISFIED，没修过的得 VIOLATED。
    两者拿到同一个 id，于是第二次签发撞上"同一 id 不可改判"直接抛异常：

        ValueError: val_7ffb… 已签发且**判定不同**

    主体仍然是那门课（``registry.verify`` 按 entity_type + entity_id 比对，
    绑定语义不变），只是**判定不同的两次校验不再共用一个编号**。
    调用方传什么进 context 由它自己决定——对先修来说是学生，
    对名额类规则可能是时间窗。
    """
    digest = hashlib.sha256(
        f"{rule_set_version}|{subject_ref.entity_type}|{subject_ref.entity_id}|"
        f"{subject_ref.entity_version or ''}|{context}".encode()
    ).hexdigest()
    return f"val_{digest[:32]}"


#: 可以背书一个计划项的判定。
#:
#: ``NEEDS_CONFIRMATION`` 在列，是因为 Spec §16.4 明确允许"先安排对
#: Needs confirmation 的核实动作"——那种计划项本来就该存在。
#: ``VIOLATED`` 与 ``NOT_APPLICABLE`` 不在列：前者是 Rules 明说违规，
#: 后者是"这条规则不适用"，两者都不是"可以做"的证据。
BACKING_VERDICTS: frozenset[Verdict] = frozenset(
    {Verdict.SATISFIED, Verdict.NEEDS_CONFIRMATION}
)


@runtime_checkable
class ValidationRegistry(Protocol):
    """API 层用它回答"这个 validation_id 真的被签发过、而且判定是能用的吗"。

    WP5 提供 Firestore 实现；``InMemoryValidationRegistry`` 供测试与评测使用。
    """

    def issue(self, validation: ConstraintValidation) -> None: ...

    def get(self, validation_id: str) -> ConstraintValidation | None: ...

    def verify(self, validation_id: str, subject_ref: SourceRef) -> bool:
        """id 存在、未过期、是对 ``subject_ref`` 的校验，**且判定可以背书**。"""
        ...


class InMemoryValidationRegistry:
    """参考实现。行为即契约——WP5 的持久化实现必须通过同一套测试。"""

    def __init__(self) -> None:
        self._store: dict[str, ConstraintValidation] = {}

    def issue(self, validation: ConstraintValidation) -> None:
        """签发。同一个 id 重复签发**同一判定**是允许的（重新算了一次）；
        判定不同则拒绝——那是改判，必须用新 id，否则审计链会断。
        """
        existing = self._store.get(validation.validation_id)
        if existing is not None and existing.decision_key() != validation.decision_key():
            raise ValueError(
                f"validation_id {validation.validation_id} 已签发且**判定不同**——"
                "校验结果不可改判，请签发新 id"
            )
        if existing is None:
            self._store[validation.validation_id] = validation

    def get(self, validation_id: str) -> ConstraintValidation | None:
        return self._store.get(validation_id)

    def verify(
        self,
        validation_id: str,
        subject_ref: SourceRef,
        *,
        now: datetime | None = None,
        accept_verdicts: frozenset[Verdict] = BACKING_VERDICTS,
    ) -> bool:
        """曾经这里只查"签发过没有"，不看判定。

        于是 A5 可以拿一条 Rules 真实签发的、主体也完全正确的
        「先修不满足」判定去背书一个计划项，闸门照样放行——
        证明了**出处**，没证明**合规**。Spec §8.9.3 要这条绑定保证的是
        "判定结果不可能被模型输出覆盖"，只查出处做不到这一点。
        """
        found = self._store.get(validation_id)
        if found is None:
            return False
        if found.is_expired(now):
            return False
        if found.verdict not in accept_verdicts:
            return False
        return (
            found.subject_ref.entity_type == subject_ref.entity_type
            and found.subject_ref.entity_id == subject_ref.entity_id
        )


class UnbackedOutputError(ValueError):
    """A5 输出携带了未签发、过期或张冠李戴的 validation_id。API 层据此返回 4xx。"""
