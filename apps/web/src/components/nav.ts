import type { MessageKey } from "@/i18n";

/**
 * D1 的 14 个页面。**这份数组是唯一出处**——导航、面包屑、
 * 以及"页面完整性"的浏览器实测脚本都从这里取，
 * 所以"少做了一页"不可能只在某一处被发现。
 *
 * 导航项按其**内容**命名（"Pathway Timeline"、"Memory Center"），
 * 不用 "Home" 这类伞状词：具体的名字才能让人预判点进去看到什么。
 */
export type NavItem = {
  href: string;
  labelKey: MessageKey;
  groupKey: MessageKey;
  /** 归属门户。学生端只见学生项，校方端只见校方项——**互不可见**。 */
  portal: "student" | "institution";
  /** 不出现在导航里，但门户守卫仍认它（并入他页后保留深链接）。 */
  hidden?: boolean;
  /**
   * R7-A：校方项只属于列出的岗位。以哪个岗位登录就只见（也只进得去）
   * 自己职责的工作台——advisor 连 Publisher 投稿台的导航项都看不到。
   * 未列出 = 该门户所有身份可见（学生项不用填）。
   */
  roles?: readonly string[];
};

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/onboarding", labelKey: "page.onboarding", groupKey: "nav.group.start", portal: "student" },

  { href: "/profile", labelKey: "page.profile", groupKey: "nav.group.me", portal: "student" },
  // 用户裁定（2026-08-01）：成长动态跟踪讲的是"我"的证据链，归「我」分组，
  // 紧跟成长档案——档案是存量、跟踪是增量，读序自然
  { href: "/gaps", labelKey: "page.gaps", groupKey: "nav.group.me", portal: "student" },
  { href: "/reflections", labelKey: "page.reflections", groupKey: "nav.group.me", portal: "student" },
  { href: "/memory", labelKey: "page.memory", groupKey: "nav.group.me", portal: "student" },

  // 第三轮调整（2026-07-31 用户裁定 I）：
  // 选课与学位规划 + 课外活动规划（原路径时间线）合并为 /planner 的同页分页；
  // 行动中心恢复为独立导航项（从时间线分页拎出）；身心容量仍并入日历。
  // /timeline 与 /wellbeing 的路由保留（深链接不断），只是不出现在导航里。
  { href: "/goals", labelKey: "page.goals", groupKey: "nav.group.direction", portal: "student" },
  // 导航名点明双重身份（用户裁定 2026-08-01）；页内分页标签仍各自用
  // page.calendar / page.wellbeing，不动
  { href: "/calendar", labelKey: "nav.calendarWellbeing", groupKey: "nav.group.direction", portal: "student" },
  { href: "/actions", labelKey: "page.actions", groupKey: "nav.group.direction", portal: "student" },
  { href: "/planner", labelKey: "page.planner", groupKey: "nav.group.direction", portal: "student", hidden: true },
  { href: "/timeline", labelKey: "page.timeline", groupKey: "nav.group.direction", portal: "student", hidden: true },
  { href: "/wellbeing", labelKey: "page.wellbeing", groupKey: "nav.group.direction", portal: "student", hidden: true },

  { href: "/for-you", labelKey: "page.forYou", groupKey: "nav.group.discover", portal: "student" },
  { href: "/checkin", labelKey: "checkin.title", groupKey: "nav.group.discover", portal: "student", hidden: true },
  { href: "/square", labelKey: "page.square", groupKey: "nav.group.discover", portal: "student" },

  { href: "/settings", labelKey: "page.settings", groupKey: "nav.group.system", portal: "student" },

  // 校方门户。曾与学生端同一份导航"按角色路由"（Plan §165 的旧决定）——
  // 用户裁定推翻：两端必须各自登录、界面互不混排。D5 的隔离验证不受影响：
  // /console 里仍以校方身份对学生禁区端点做主动探测，全部 403 才算通过。
  // R7-A：一岗一台。旧的细分角色（reviewer/curator/connector_admin）
  // 归并到 Career Center 控制台；wellbeing_coordinator 是心理咨询室部门，
  // 有自己的工作台（outreach 队列），不与 Career Center 混排。
  { href: "/publisher", labelKey: "publisher.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["publisher"] },
  { href: "/console", labelKey: "console.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "reviewer", "curator", "connector_admin"] },
  // 用户裁定（2026-08-01）：审核队列独立成页；广场总览给管理端只读监看
  { href: "/review", labelKey: "console.reviewQueue", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "reviewer"] },
  { href: "/plaza-admin", labelKey: "console.plaza.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin", "curator"] },
  { href: "/quality-reports", labelKey: "reports.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["career_center_admin"] },
  { href: "/wellbeing-desk", labelKey: "wellbeingDesk.title", groupKey: "nav.group.institution", portal: "institution",
    roles: ["wellbeing_coordinator"] },
  { href: "/advisor-desk", labelKey: "advisor.deskTitle", groupKey: "nav.group.institution", portal: "institution",
    roles: ["advisor"] },
] as const;

export type NavSession =
  | { portal: "student" }
  | { portal: "institution"; role: string };

export function itemsFor(session: NavSession): NavItem[] {
  return NAV_ITEMS.filter(
    (item) =>
      item.portal === session.portal &&
      (item.roles === undefined ||
        session.portal !== "institution" ||
        item.roles.includes(session.role)),
  );
}

/** 导航栏显示用：过滤掉并入他页的隐藏项。守卫请用 itemsFor（含隐藏项）。 */
export function visibleItemsFor(session: NavSession): NavItem[] {
  return itemsFor(session).filter((item) => !item.hidden);
}

/**
 * 落地页跟着身份走：学生进档案；校方进自己岗位的第一个（通常唯一的）
 * 工作台。没有任何可见项的身份回登录页——不该发生，发生了也别死循环。
 */
export function homeFor(session: NavSession): string {
  if (session.portal === "student") return "/profile";
  return visibleItemsFor(session)[0]?.href ?? "/login";
}

export const NAV_GROUPS: readonly MessageKey[] = [
  "nav.group.start",
  "nav.group.me",
  "nav.group.direction",
  "nav.group.plan",
  "nav.group.discover",
  "nav.group.system",
  "nav.group.institution",
] as const;
