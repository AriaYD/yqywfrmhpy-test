"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n } from "@/i18n";
import { api } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Card,
  Empty,
  Failure,
  Loading,
  PageHeader,
} from "@/components/ui";

/**
 * D2 要求记忆"可查看/纠正/锁定/删除/导出"。
 *
 * 列表走 `/memory` 而不是 `/memory/recall`——后者是**按任务做最小化召回**，
 * 拿它当列表，学生就永远看不见没被当前任务命中的那些记忆。
 * 两者用途不同，不能互相顶替。
 */
export default function MemoryPage() {
  const { t } = useI18n();
  const { studentId } = usePersona();
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [correction, setCorrection] = useState("");
  // S4（审查）：单条删除也是不可逆操作，与 settings 删数据同一纪律——两段确认
  const [confirmingForget, setConfirmingForget] = useState<string | null>(null);

  const entries = useResource(() => api.memory(studentId), [studentId]);

  function exportAll() {
    const blob = new Blob([JSON.stringify(entries.data ?? [], null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `campuspath-memory-${studentId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader titleKey="memory.title" leadKey="memory.lead">
        <button
          type="button"
          data-memory-export
          onClick={exportAll}
          className="pressable btn btn-secondary t-meta"
        >
          {t("memory.export")}
        </button>
      </PageHeader>

      {entries.loading && <Loading />}
      {entries.error && <Failure error={entries.error} onRetry={entries.reload} />}
      {entries.data?.length === 0 && <Empty messageKey="memory.empty" />}

      <ul className="flex flex-col gap-3">
        {entries.data?.map((entry) => {
          const isLocked = entry.student_locked;
          // S3（审查）：服务端早就写了 supersedes 链，界面却把新旧渲染得
          // 一模一样——与本页"旧条目会保留并标记被取代"的承诺不符。
          const superseded = Boolean(entry.superseded_by);
          return (
            <Card key={entry.memory_id} as="li">
              <div
                data-memory={entry.memory_id}
                data-memory-locked={String(isLocked)}
                data-memory-superseded={String(superseded)}
              >
                <div className="t-micro flex flex-wrap items-center gap-3 text-fg-faint">
                  <span>{entry.type}</span>
                  <span>
                    {t("memory.origin")}: {entry.origin}
                  </span>
                  <span className="tabular-nums">
                    {Math.round(entry.confidence * 100)}%
                  </span>
                  {superseded && (
                    <span className="chip chip-neutral t-micro" data-superseded-badge>
                      {t("memory.superseded")} · {t("memory.supersededBy")}{" "}
                      {entry.superseded_by}
                    </span>
                  )}
                </div>
                <p
                  className="t-body mt-2"
                  style={
                    superseded
                      ? { color: "var(--fg-faint)", textDecoration: "line-through" }
                      : { color: "var(--fg)" }
                  }
                >
                  {entry.content}
                </p>
                <div className="t-mono mt-2 text-fg-faint">
                  {entry.valid_from.slice(0, 10)} · {entry.authority} ·{" "}
                  {entry.visibility}
                </div>

                {correcting === entry.memory_id && (
                  <div className="mt-3 flex flex-col gap-2">
                    <textarea
                      data-memory-correction-input
                      value={correction}
                      onChange={(e) => setCorrection(e.target.value)}
                      rows={2}
                      className="field w-full px-3 py-2"
                      placeholder={t("memory.correct.placeholder")}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        data-memory-correction-submit={entry.memory_id}
                        disabled={!correction.trim()}
                        onClick={async () => {
                          await api.correctMemory(studentId, entry.memory_id, correction.trim());
                          setCorrecting(null);
                          setCorrection("");
                          entries.reload();
                        }}
                        className="pressable btn btn-primary t-meta font-medium disabled:opacity-40"
                      >
                        {t("memory.correct.submit")}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setCorrecting(null); setCorrection(""); }}
                        className="pressable btn btn-ghost t-meta"
                      >
                        {t("memory.correct.cancel")}
                      </button>
                    </div>
                  </div>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-memory-correct={entry.memory_id}
                    onClick={() => setCorrecting(entry.memory_id)}
                    className="pressable btn btn-ghost t-meta"
                  >
                    {t("memory.correct")}
                  </button>
                  <button
                    type="button"
                    data-memory-lock={entry.memory_id}
                    disabled={isLocked}
                    onClick={async () => {
                      await api.lockMemory(studentId, entry.memory_id);
                      entries.reload();
                    }}
                    className="pressable t-meta rounded-md border px-2.5 py-1 disabled:opacity-60"
                    style={{
                      borderColor: isLocked ? "var(--accent)" : "var(--line)",
                      color: isLocked ? "var(--accent-deep)" : "var(--fg-muted)",
                    }}
                  >
                    {t(isLocked ? "memory.locked" : "memory.lock")}
                  </button>
                  <button
                    type="button"
                    data-memory-forget={entry.memory_id}
                    onClick={() => setConfirmingForget(entry.memory_id)}
                    className="pressable btn btn-danger t-meta"
                  >
                    {t("memory.delete")}
                  </button>
                </div>

                {confirmingForget === entry.memory_id && (
                  <div
                    className="mt-3 flex flex-wrap items-center gap-2 rounded-md p-2.5"
                    role="alertdialog"
                    data-memory-forget-confirm={entry.memory_id}
                    style={{
                      border: "1px solid var(--color-clay-500)",
                      background: "var(--color-clay-100)",
                    }}
                  >
                    <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                      {t("memory.delete.confirm")}
                    </span>
                    <button
                      type="button"
                      data-memory-forget-go={entry.memory_id}
                      onClick={async () => {
                        await api.forgetMemory(studentId, entry.memory_id);
                        setConfirmingForget(null);
                        entries.reload();
                      }}
                      className="pressable t-meta rounded-md px-3 py-1.5 font-medium"
                      style={{
                        background: "var(--color-clay-600)",
                        color: "var(--color-clay-100)",
                      }}
                    >
                      {t("memory.delete")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingForget(null)}
                      className="pressable btn btn-ghost t-meta"
                    >
                      {t("memory.correct.cancel")}
                    </button>
                  </div>
                )}
              </div>
            </Card>
          );
        })}
      </ul>
    </>
  );
}
