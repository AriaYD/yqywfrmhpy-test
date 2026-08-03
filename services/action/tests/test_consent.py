"""Action & Consent Service：预览 → 同意 → 幂等执行 → 审计。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from campuspath_contracts.common import LocalizedText

from campuspath_action.consent import (
    ActionPreview,
    ActionService,
    NotApproved,
    PreviewMismatch,
    approve,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


def preview(**kw) -> ActionPreview:
    base = dict(
        preview_id="PV-1", student_id="STU-A", kind="calendar_write",
        summary=LocalizedText(zh_Hans="写入 3 个学习时段", en="Write 3 study blocks"),
        payload={"slots": 3, "title": "COMP 3711 复习"},
    )
    base.update(kw)
    return ActionPreview(**base)


def test_approved_action_executes_and_is_audited():
    service = ActionService()
    pv = preview()
    receipt = approve(pv, receipt_id="RCPT-1", at=NOW)
    outcome = service.execute(pv, receipt, idempotency_key="k1", at=NOW,
                              executor=lambda p: "ext-123")
    assert outcome.result == "succeeded"
    assert outcome.external_ref == "ext-123"
    assert len(service.audit_log) == 1
    assert service.audit_log[0].receipt_id == "RCPT-1"


def test_repeat_execution_is_idempotent():
    """学生手滑点两次，不该出现两个日历事件。"""
    service = ActionService()
    pv = preview()
    receipt = approve(pv, receipt_id="RCPT-1", at=NOW)
    calls: list[str] = []

    def executor(p):
        calls.append(p.preview_id)
        return "ext-123"

    service.execute(pv, receipt, idempotency_key="k1", at=NOW, executor=executor)
    second = service.execute(pv, receipt, idempotency_key="k1", at=NOW, executor=executor)
    assert second.result == "replayed"
    assert calls == ["PV-1"], "第二次不得再次调用 executor"


def test_receipt_for_another_student_is_refused():
    service = ActionService()
    pv = preview()
    receipt = approve(preview(student_id="STU-B", preview_id="PV-1"),
                      receipt_id="RCPT-X", at=NOW)
    with pytest.raises(NotApproved):
        service.execute(pv, receipt, idempotency_key="k", at=NOW)


def test_receipt_for_another_preview_is_refused():
    service = ActionService()
    receipt = approve(preview(preview_id="PV-OTHER"), receipt_id="RCPT-1", at=NOW)
    with pytest.raises(PreviewMismatch):
        service.execute(preview(), receipt, idempotency_key="k", at=NOW)


def test_payload_changed_after_approval_is_refused():
    """已知会失败的样例：学生确认了 3 个时段，执行时变成 30 个。"""
    service = ActionService()
    pv = preview()
    receipt = approve(pv, receipt_id="RCPT-1", at=NOW)
    tampered = preview(payload={"slots": 30, "title": "COMP 3711 复习"})
    with pytest.raises(PreviewMismatch) as excinfo:
        service.execute(tampered, receipt, idempotency_key="k", at=NOW)
    assert "同意的不是现在要执行的东西" in str(excinfo.value)


def test_execute_cannot_be_called_without_a_receipt():
    """结构性保证：execute 的参数类型就是回执，编不出来就调不动。"""
    import inspect

    signature = inspect.signature(ActionService.execute)
    assert "receipt" in signature.parameters
    assert signature.parameters["receipt"].default is inspect.Parameter.empty


def test_failure_is_audited_too():
    service = ActionService()
    pv = preview()
    receipt = approve(pv, receipt_id="RCPT-1", at=NOW)

    def boom(p):
        raise RuntimeError("provider down")

    outcome = service.execute(pv, receipt, idempotency_key="k", at=NOW, executor=boom)
    assert outcome.result == "failed"
    assert service.audit_log[0].outcome == "failed"


def test_refusal_is_audited():
    """只记成功的日志无法回答"为什么这条没写进去"。"""
    service = ActionService()
    service.record_refusal(preview(), NOW, "学生未授权日历写入")
    assert service.audit_log[0].outcome == "refused"
    assert service.audit_log[0].receipt_id is None


def test_fingerprint_changes_with_payload():
    assert preview().fingerprint() != preview(payload={"slots": 4}).fingerprint()
