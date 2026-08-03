"use client";

import { useState } from "react";
import { useI18n } from "@/i18n";
import { ActionsContent } from "@/app/actions/page";
import { ActivityPlanContent } from "@/app/timeline/page";
import { PlannerContent } from "@/app/planner/page";

/**
 * R4-L（2026-07-31）：行动中心 / 课外活动规划 / 选修课推荐 合并为一页三分页。
 * 三个深链接（/actions /timeline /planner）各自落在对应分页，导航只留一项。
 * 模块间的引用都发生在渲染时，页面模块间的循环引用因此无害。
 */
export type PlanTab = "actions" | "activities" | "electives";

const TAB_KEY = {
  actions: "page.actions",
  activities: "page.timeline",
  electives: "page.planner",
} as const;

export function PlanHub({ initial }: { initial: PlanTab }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<PlanTab>(initial);
  return (
    <>
      {/* 页面级分页：全站统一分段控件样式（用户裁定 2026-08-01，与日历页一致） */}
      <div
        className="mb-5 inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
        data-page-tabs
      >
        {(["actions", "activities", "electives"] as const).map((tabKey) => (
          <button
            key={tabKey}
            type="button"
            data-page-tab={tabKey}
            aria-pressed={tab === tabKey}
            onClick={() => setTab(tabKey)}
            className="pressable t-meta rounded-sm px-3 py-1.5"
            style={{
              background: tab === tabKey ? "var(--accent-deep)" : "transparent",
              color: tab === tabKey ? "var(--accent-fg)" : "var(--fg-muted)",
              fontWeight: tab === tabKey ? 600 : 500,
            }}
          >
            {t(TAB_KEY[tabKey])}
          </button>
        ))}
      </div>
      {tab === "actions" && <ActionsContent />}
      {tab === "activities" && <ActivityPlanContent />}
      {tab === "electives" && <PlannerContent />}
    </>
  );
}
