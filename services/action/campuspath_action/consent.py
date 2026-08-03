"""Action & Consent Service（Spec §15.4 规则 8、D3）。**零 LLM。**

一条铁律：**学生批准之前，什么都不写。**
日历、任务、提醒投递、outreach 请求全部先出预览，学生确认后才执行。

因此这个服务的形状是"两段式"，而不是"带一个 confirm 参数的写入函数"：

```
preview(intent)  → ActionPreview（可展示、可比较、带 preview_id）
approve(preview) → ConsentReceipt（不可变，进审计）
execute(receipt) → ActionOutcome（幂等）
```

把预览与执行拆成两次调用，是为了让"没有回执就执行"在**类型上做不到**：
``execute`` 的参数是 :class:`ConsentReceipt`，编不出来就调不动。

幂等：同一 ``idempotency_key`` 重复执行返回**第一次的结果**，不重复写。
Demo 里学生手滑点两次，不该出现两个日历事件。
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime
from typing import Any, Callable, Literal

from campuspath_contracts.common import ActorRole, Identifier, LocalizedText

ActionKind = Literal[
    "calendar_write", "task_create", "reminder_delivery", "wellbeing_outreach",
    "profile_write", "application_submit",
]


class NotApproved(PermissionError):
    """没有有效同意回执就试图执行。API 层据此返回 403。"""


class PreviewMismatch(ValueError):
    """回执对应的预览与要执行的预览不是同一个——防止"确认了 A、执行了 B"。"""


@dataclasses.dataclass(frozen=True)
class ActionPreview:
    """给学生看的东西。``summary`` 双语，``payload`` 是将要写入的确切内容。"""

    preview_id: Identifier
    student_id: Identifier
    kind: ActionKind
    summary: LocalizedText
    payload: dict[str, Any]
    reversible: bool = True

    def fingerprint(self) -> str:
        """预览内容的指纹。回执绑定它，改一个字就对不上。"""
        material = f"{self.preview_id}|{self.kind}|{sorted(self.payload.items())}"
        return hashlib.sha256(material.encode()).hexdigest()[:32]


@dataclasses.dataclass(frozen=True)
class ConsentReceipt:
    """不可变的同意记录。审计日志的主键。"""

    receipt_id: Identifier
    preview_id: Identifier
    preview_fingerprint: str
    student_id: Identifier
    granted_at: datetime
    actor: ActorRole = ActorRole.STUDENT


@dataclasses.dataclass(frozen=True)
class ActionOutcome:
    receipt_id: Identifier
    idempotency_key: str
    result: Literal["succeeded", "failed", "replayed"]
    external_ref: str | None = None
    failure_reason: str | None = None


@dataclasses.dataclass(frozen=True)
class AuditEntry:
    """§7「大学可治理」的落点：谁、在什么时候、对什么、做了什么、依据哪份同意。"""

    entry_id: Identifier
    student_id: Identifier
    kind: ActionKind
    receipt_id: Identifier | None
    at: datetime
    outcome: str
    detail: str


def approve(preview: ActionPreview, *, receipt_id: str, at: datetime) -> ConsentReceipt:
    return ConsentReceipt(
        receipt_id=receipt_id,
        preview_id=preview.preview_id,
        preview_fingerprint=preview.fingerprint(),
        student_id=preview.student_id,
        granted_at=at,
    )


@dataclasses.dataclass
class ActionService:
    """执行与审计。写入副作用由注入的 ``executor`` 完成，便于测试与替换 Provider。"""

    _outcomes: dict[str, ActionOutcome] = dataclasses.field(default_factory=dict)
    _audit: list[AuditEntry] = dataclasses.field(default_factory=list)

    @property
    def audit_log(self) -> tuple[AuditEntry, ...]:
        return tuple(self._audit)

    def execute(
        self,
        preview: ActionPreview,
        receipt: ConsentReceipt,
        *,
        idempotency_key: str,
        at: datetime,
        executor: Callable[[ActionPreview], str] | None = None,
    ) -> ActionOutcome:
        if receipt.student_id != preview.student_id:
            raise NotApproved("回执与预览属于不同学生")
        if receipt.preview_id != preview.preview_id:
            raise PreviewMismatch("回执对应的不是这份预览")
        if receipt.preview_fingerprint != preview.fingerprint():
            raise PreviewMismatch(
                "预览内容在确认之后被改动过——学生同意的不是现在要执行的东西"
            )

        existing = self._outcomes.get(idempotency_key)
        if existing is not None:
            replayed = dataclasses.replace(existing, result="replayed")
            self._record(preview, receipt, at, "replayed", "幂等重放，未重复写入")
            return replayed

        try:
            external_ref = executor(preview) if executor else None
            outcome = ActionOutcome(
                receipt_id=receipt.receipt_id,
                idempotency_key=idempotency_key,
                result="succeeded",
                external_ref=external_ref,
            )
            self._record(preview, receipt, at, "succeeded", external_ref or "")
        except Exception as exc:                     # noqa: BLE001 - 失败也要进审计
            outcome = ActionOutcome(
                receipt_id=receipt.receipt_id,
                idempotency_key=idempotency_key,
                result="failed",
                failure_reason=repr(exc),
            )
            self._record(preview, receipt, at, "failed", repr(exc))
            self._outcomes[idempotency_key] = outcome
            return outcome

        self._outcomes[idempotency_key] = outcome
        return outcome

    def _record(
        self, preview: ActionPreview, receipt: ConsentReceipt | None,
        at: datetime, outcome: str, detail: str,
    ) -> None:
        self._audit.append(
            AuditEntry(
                entry_id=f"AUD-{len(self._audit) + 1:05d}",
                student_id=preview.student_id,
                kind=preview.kind,
                receipt_id=receipt.receipt_id if receipt else None,
                at=at,
                outcome=outcome,
                detail=detail,
            )
        )

    def record_refusal(self, preview: ActionPreview, at: datetime, reason: str) -> None:
        """被拒绝的写入同样进审计——只记成功的日志无法回答"为什么没写"。"""
        self._record(preview, None, at, "refused", reason)
