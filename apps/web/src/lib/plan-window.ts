import type { PlanItem } from "./api";

/**
 * 规划条目的时间窗口口径——「课外活动规划」与「行动中心·近两周」共用，
 * 单一出处（2026-08-03 用户报障：行动中心按 status==="in_progress" 筛，
 * 那是演示夹具时代的档期编码；A5 真生成后条目全是 proposed，该区恒空，
 * 与课外规划页互相矛盾。两页改读同一套函数后不可能再各说各话）。
 */
export const NEAR_WINDOW_DAYS = 14;

/**
 * 学生选定的规划强度（S1 三档，本地持久化）。读规划的页面**都**要带上
 * 它——行动中心此前裸调 pathway 落在 balanced，与课外规划页（读此值）
 * 各拿一份不同强度的规划，近两周条数对不上。
 */
const INTENSITIES = new Set(["low_load", "balanced", "ambitious"]);

export function storedIntensity(): string {
  if (typeof window === "undefined") return "balanced";
  const stored = window.localStorage.getItem("campuspath.intensity");
  // 白名单：localStorage 的脏值原样进 ?intensity= 会换来 422（审查 L-6）
  return stored !== null && INTENSITIES.has(stored) ? stored : "balanced";
}

/** 课程不算活动：kind=course 属于选课与学位规划页（I 裁定）。 */
export function planActivities(items: readonly PlanItem[]): PlanItem[] {
  return items.filter((item) => item.kind !== "course");
}

/**
 * 窗口锚点 = 最早活动开始日（演示时钟：合成数据锚在种子快照期，
 * 用"今天"当锚会让所有窗口口径漂移），没有活动时退回当前时刻。
 */
export function planAnchor(activities: readonly PlanItem[]): Date {
  return activities.length
    ? new Date(
        Math.min(...activities.map((i) => new Date(i.date_range.start).getTime())),
      )
    : new Date();
}

export function withinWindow(item: PlanItem, days: number, from: Date): boolean {
  const start = new Date(item.date_range.start);
  const horizon = new Date(from.getTime() + days * 86_400_000);
  return start <= horizon;
}
