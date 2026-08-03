"""Student State & Memory Platform（Spec §8.4 的四层）。**零 LLM。**

| 层 | 这里的实现 |
|---|---|
| L0 Canonical Profile | :class:`StudentStateStore` 的当前状态，只能经 Proposal 更新 |
| L1 Episodic Timeline | append-only 事件流，只追加，错误用更正事件处理 |
| L2 Semantic Memory | :class:`MemoryProvider` 接口 + 内存参考实现（可换 Memory Bank） |
| L3 Evidence & Notes | Evidence Index 与 Private Vault 引用，**独立于 Profile 留存** |

三条不变式，每条都对应一项验收：

1. **B3**：Profile 的唯一写入路径是"已确认的 Proposal"。
   ``apply_decision`` 之外没有别的写入方法——不是约定，是没有那个函数。
2. **Spec §8.2.3**：Evidence 与 Note 不随 Profile 更新消失。
   删 Profile 条目不会碰 Evidence Index。
3. **Spec §8.4**：语义记忆不得覆盖结构化事实。
   ``MemoryEntry.authority`` 在契约层已锁死为 ``advisory``，
   这里的检索接口也不提供任何"用记忆改写 Profile"的入口。
"""

from __future__ import annotations

import dataclasses
import threading
from datetime import datetime
from typing import Protocol

from campuspath_contracts.memory import (
    MemoryEntry,
    MemoryProposal,
    MemoryRecallQuery,
    MemoryRecallResult,
    RecalledMemory,
)
from campuspath_contracts.profile import (
    EvidenceRecord,
    Note,
    ProfileChangeEvent,
    ProfileUpdateProposal,
    ProposalStatus,
    StudentProfile,
)


class UnconfirmedWrite(PermissionError):
    """试图绕过学生确认写 Profile。B3 的判定入口。"""


class ProposalNotFound(KeyError):
    pass


@dataclasses.dataclass
class StudentStateStore:
    """单个学生的状态。生产实现换成 Firestore，接口与不变式不变。"""

    profile: StudentProfile
    _proposals: dict[str, ProfileUpdateProposal] = dataclasses.field(default_factory=dict)
    _events: list[ProfileChangeEvent] = dataclasses.field(default_factory=list)
    _evidence: dict[str, EvidenceRecord] = dataclasses.field(default_factory=dict)
    _notes: dict[str, Note] = dataclasses.field(default_factory=dict)

    # ── L1 事件流 ───────────────────────────────────────────────────

    @property
    def events(self) -> tuple[ProfileChangeEvent, ...]:
        """append-only。返回元组，调用方拿不到可变引用。"""
        return tuple(self._events)

    # ── L3 Evidence / Note：独立留存 ────────────────────────────────

    def put_evidence(self, evidence: EvidenceRecord) -> None:
        self._evidence[evidence.evidence_id] = evidence

    def put_note(self, note: Note) -> None:
        self._notes[note.note_id] = note

    def evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._evidence.get(evidence_id)

    def note(self, note_id: str) -> Note | None:
        return self._notes.get(note_id)

    @property
    def evidence_count(self) -> int:
        return len(self._evidence)

    # ── L0 Profile：唯一写入路径 ────────────────────────────────────

    def submit_proposal(self, proposal: ProfileUpdateProposal) -> None:
        """A1 提交更新建议。**必须是 pending**——Agent 不得自行置为已确认。"""
        if proposal.status is not ProposalStatus.PENDING:
            raise UnconfirmedWrite(
                f"提案 {proposal.proposal_id} 提交时状态为 {proposal.status.value}；"
                "只有学生的决定能推进状态（B3）"
            )
        if proposal.student_id != self.profile.student_id:
            raise UnconfirmedWrite("提案属于另一个学生")
        self._proposals[proposal.proposal_id] = proposal

    def pending_proposals(self) -> tuple[ProfileUpdateProposal, ...]:
        return tuple(
            p for _, p in sorted(self._proposals.items())
            if p.status is ProposalStatus.PENDING
        )

    def proposals(self) -> tuple[ProfileUpdateProposal, ...]:
        """全部提案（含已裁决的）。读接口——写仍只有 apply_decision 一条路。"""
        return tuple(p for _, p in sorted(self._proposals.items()))

    def apply_decision(
        self,
        proposal_id: str,
        decision: ProposalStatus,
        *,
        decided_at: datetime,
        actor: str = "student",
        changed_fields: tuple[str, ...] = (),
    ) -> ProfileChangeEvent:
        """学生的决定是**唯一**能改变 Profile 版本的动作。

        拒绝也会写事件（Spec §8.2.2「保留事件，不写入当前 Profile」），
        只是不 bump 版本——契约层的 validator 会强制这一点。
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise ProposalNotFound(proposal_id)
        if decision is ProposalStatus.PENDING:
            raise UnconfirmedWrite("pending 不是一个决定")

        wrote = decision in {ProposalStatus.CONFIRMED, ProposalStatus.EDITED}
        before = self.profile.version
        after = before + 1 if wrote else before

        event = ProfileChangeEvent(
            event_id=f"PCE-{self.profile.student_id}-{len(self._events) + 1:04d}",
            student_id=self.profile.student_id,
            profile_version_before=before,
            profile_version_after=after,
            actor=actor,  # type: ignore[arg-type]
            decision=decision,
            timestamp=decided_at,
            changed_fields=changed_fields if wrote else (),
            proposal_id=proposal_id,
        )
        self._events.append(event)
        self._proposals[proposal_id] = proposal.model_copy(
            update={"status": decision, "decided_at": decided_at}
        )
        if wrote:
            self.profile = self.profile.model_copy(
                update={"version": after, "updated_at": decided_at}
            )
        return event

    def profile_version_at(self, when: datetime) -> int:
        """按事件流回放到某一时刻的版本号。审计与"入学时 vs 现在"对比都靠它。"""
        version = 1
        for event in self._events:
            if event.timestamp <= when:
                version = event.profile_version_after
        return version


# --------------------------------------------------------------------------
# L2 语义记忆
# --------------------------------------------------------------------------


class MemoryProvider(Protocol):
    """Spec §8.7 预留的可替换接口。MVP 用 ADK Memory Bank，降级用 Firestore + embedding。"""

    def write(self, entry: MemoryEntry) -> None: ...

    def recall(self, query: MemoryRecallQuery) -> MemoryRecallResult: ...

    def list_for(self, student_id: str) -> list[MemoryEntry]:
        """某个学生的全部条目。

        Memory Center 要求"可查看/纠正/锁定/删除/导出"（D2），
        而 ``recall`` 是**按任务做最小化召回**的——用它来当列表，
        学生就永远看不到那些没被当前任务命中的记忆。
        两者用途不同，不能互相顶替。
        """
        ...


class MemoryLocked(RuntimeError):
    """试图修改或取代一条学生锁定的记忆。"""


@dataclasses.dataclass
class InMemoryMemoryProvider:
    """参考实现：关键词重合度检索。

    刻意不做向量检索——**接口契约才是要冻结的东西**，
    换成 Memory Bank 时这套测试必须原样通过。

    并发：FastAPI 的同步 handler 跑在线程池里，读-判-写若不加锁，
    两个并发的 forget 会一个 200 一个 500（审查实测复现）。
    所有变更走同一把锁；纠正条目的序号也从锁内计数器取，
    不再依赖 ``len(entries)``——忘记过条目之后那个数字会回退并撞号。
    """

    entries: dict[str, MemoryEntry] = dataclasses.field(default_factory=dict)
    _mutex: threading.RLock = dataclasses.field(
        default_factory=threading.RLock, repr=False
    )
    _sequence: int = 0

    def next_sequence(self) -> int:
        with self._mutex:
            self._sequence += 1
            return self._sequence

    def write(self, entry: MemoryEntry) -> None:
        with self._mutex:
            existing = self.entries.get(entry.memory_id)
            if existing is not None and existing.student_locked:
                # 同 id 直写同样受锁保护——否则重放一次「收藏」就能
                # 顶掉一条学生锁定的偏好并把锁悄悄归零（审查实测复现）
                raise MemoryLocked(
                    f"记忆 {entry.memory_id} 已被学生锁定，不能被同 id 覆盖"
                )
            if entry.supersedes is not None:
                old = self.entries.get(entry.supersedes)
                if old is not None:
                    if old.student_locked:
                        # 学生锁定 = 系统不得修改或取代。想改就先由学生解锁。
                        raise MemoryLocked(
                            f"记忆 {old.memory_id} 已被学生锁定，不能被取代"
                        )
                    # 不静默覆盖：旧条目保留，只标记被取代（Spec §8.6）
                    self.entries[old.memory_id] = old.model_copy(
                        update={"superseded_by": entry.memory_id}
                    )
            self.entries[entry.memory_id] = entry

    def lock(self, memory_id: str) -> MemoryEntry:
        """学生锁定。锁定后 supersede 与同 id 覆盖都会被拒绝（见 :meth:`write`）。"""
        with self._mutex:
            entry = self.entries[memory_id]
            locked = entry.model_copy(update={"student_locked": True})
            self.entries[memory_id] = locked
            return locked

    def forget(self, memory_id: str) -> MemoryEntry | None:
        """「忘记」= 真正移除。幂等：已经不在了就返回 None，不抛错。"""
        with self._mutex:
            return self.entries.pop(memory_id, None)

    def list_for(self, student_id: str) -> list[MemoryEntry]:
        """按 memory_id 排序，保证同一份数据两次调用顺序一致（D6.7 可复现）。"""
        return sorted(
            (e for e in self.entries.values() if e.student_id == student_id),
            key=lambda e: e.memory_id,
        )

    def recall(self, query: MemoryRecallQuery, *, now: datetime | None = None) -> MemoryRecallResult:
        now = now or query.as_of or datetime.now(tz=None)
        tokens = {t for t in _tokenise(query.task_context) if len(t) > 1}
        scored: list[RecalledMemory] = []
        for _, entry in sorted(self.entries.items()):
            if entry.student_id != query.student_id:
                continue
            if query.types and entry.type not in query.types:
                continue
            overlap = tokens & {t for t in _tokenise(entry.content) if len(t) > 1}
            if not overlap:
                continue
            stale = _is_stale(entry, now)
            scored.append(
                RecalledMemory(
                    entry=entry,
                    relevance=min(1.0, len(overlap) / max(len(tokens), 1)),
                    stale=stale,
                )
            )
        scored.sort(key=lambda r: (-r.relevance, r.entry.memory_id))
        return MemoryRecallResult(
            query=query, recalled=tuple(scored[: query.top_k]), retrieved_at=now
        )


def _tokenise(text: str) -> set[str]:
    """空格词 + 中文字符二元组。

    纯空格切分对无空格的中文是恒失败的：整句变成一个 token，
    只有逐字相同的两句才会"相关"。中文按连续汉字串切二元组
    （串长为 1 时保留单字），ASCII 词保持原样，互不影响。
    """
    separators = " ,.;:!?，。；：！？、\n\t（）()「」『』【】《》—·"
    for sep in separators:
        text = text.replace(sep, " ")
    tokens: set[str] = set()
    for word in text.split():
        word = word.lower()
        run = ""
        ascii_run = ""
        for ch in word:
            if "一" <= ch <= "鿿":
                if ascii_run:
                    tokens.add(ascii_run)
                    ascii_run = ""
                run += ch
            else:
                if run:
                    tokens.update(_cjk_bigrams(run))
                    run = ""
                ascii_run += ch
        if run:
            tokens.update(_cjk_bigrams(run))
        if ascii_run:
            tokens.add(ascii_run)
    return tokens


def _cjk_bigrams(run: str) -> set[str]:
    if len(run) == 1:
        return {run}
    return {run[i : i + 2] for i in range(len(run) - 1)}


def _is_stale(entry: MemoryEntry, now: datetime) -> bool:
    if entry.superseded_by is not None:
        return True
    if entry.review_at is not None and now > entry.review_at:
        return True
    return False


def accept_memory_proposal(
    provider: MemoryProvider, proposal: MemoryProposal, *, student_confirmed: bool
) -> MemoryEntry:
    """高影响或有冲突的记忆建议必须先经学生确认（Spec §8.5）。"""
    if proposal.requires_student_confirmation and not student_confirmed:
        raise UnconfirmedWrite(
            f"记忆建议 {proposal.proposal_id} 需要学生确认后才能写入"
        )
    provider.write(proposal.entry)
    return proposal.entry
