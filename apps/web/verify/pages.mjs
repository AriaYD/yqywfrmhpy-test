/**
 * D1「页面完整性」的机器化点检清单。
 *
 * 为什么不写成 `expect(page).toHaveText(...)`：这份清单要被
 * **chrome-devtools 的 evaluate_script 直接吃**，所以它只是数据，
 * 断言在浏览器里跑。判定依据一律是 `data-*` 属性——
 * 用文案做断言会在切到另一种语言时全线失败，那样双语实测就变成了摆设。
 */

export const PAGES = [
  {
    path: "/onboarding",
    // 四项授权逐项独立。「outreach 默认关闭」是**状态断言**，不放在
    // 浏览器门禁里——用户合法授权一次它就永远红（2026-08-04 实发：
    // 用户测身心链路点过授权，门禁误报）。该不变量钉在
    // services/api/tests/test_wellbeing_balance.py::
    // test_outreach_consent_defaults_off_for_every_student
    // （fresh seed 全学生遍历），浏览器只断言控件在场。
    must: [
      "[data-consent='academic']",
      "[data-consent='calendar']",
      "[data-consent='wellbeing']",
      "[data-consent='outreach']",
      "[data-onboarding-finish]",
    ],
  },
  {
    path: "/profile",
    must: ["[data-tab-panel='overview']", "[data-proposal]"],
  },
  { path: "/reflections", must: ["[data-note]", "[data-reflection-boundary]"] },
  { path: "/memory", must: ["[data-memory]", "[data-memory-export]"] },
  { path: "/goals", must: ["[data-goal-role='primary']", "[data-goal-role='candidate']"] },
  { path: "/gaps", must: ["[data-unknowns]"] },
  {
    path: "/timeline",
    // 三个时间视图与 G4 成长曲线
    must: ["[data-trajectory]", "[data-trajectory-chart]", "[data-plan-items]", "[data-plan-item]"],
  },
  {
    path: "/planner",
    must: ["[data-prereq-counts]", "[data-course]", "[data-course-search]"],
  },
  {
    path: "/calendar",
    must: ["[data-capacity-snapshot]", "[data-availability-grid]", "[data-calendar-legend]"],
  },
  {
    path: "/wellbeing",
    // 2026-08-02 睡眠-负荷平衡批：容量超载信号卡 → 平衡卡；其余四信号
    // 数据链未接入时列表为空（诚实空态），故断言平衡卡而非 [data-signal]
    must: ["[data-zero-llm]", "[data-balance-card]", "[data-wellbeing-disclaimer]", "[data-outreach-request]"],
  },
  { path: "/actions", must: ["[data-schedule-proposal],[data-action-item],[data-state='empty']"] },
  { path: "/for-you", must: ["[data-match],[data-state='unavailable']"] },
  {
    path: "/square",
    must: ["[data-square-filters]", "[data-opportunity]", "[data-why-not]", "[data-square-count]"],
  },
  {
    path: "/settings",
    must: ["[data-consent-scope]", "[data-delete-data]", "[data-synthetic-badge]"],
  },
];

/** 每一页都要成立的全站不变量。 */
export const GLOBAL_MUST = [
  "[data-synthetic-badge]", // D1：全站 Synthetic / Demo Data 标记
  "[data-sidebar]",
  "nav [data-nav-link]",
];
