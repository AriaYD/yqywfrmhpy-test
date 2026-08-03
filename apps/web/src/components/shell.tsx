"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { LOCALES, useI18n, type Locale } from "@/i18n";
import { useSession } from "@/app/providers";
import { NAV_GROUPS, NAV_ITEMS, homeFor, itemsFor, visibleItemsFor } from "./nav";
import { SyntheticBadge } from "./ui";

export function LocaleSwitch() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div
      className="inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
      role="group"
      aria-label={t("chrome.language")}
    >
      {LOCALES.map((code: Locale) => {
        const active = code === locale;
        return (
          <button
            key={code}
            type="button"
            data-locale-option={code}
            aria-pressed={active}
            onClick={() => setLocale(code)}
            className="pressable t-meta rounded-sm px-2.5 py-1"
            style={{
              background: active ? "var(--accent-deep)" : "transparent",
              color: active ? "var(--accent-fg)" : "var(--fg-muted)",
              fontWeight: active ? 600 : 500,
            }}
          >
            {code === "zh-Hans" ? "简" : code === "zh-Hant" ? "繁" : "EN"}
          </button>
        );
      })}
    </div>
  );
}

/**
 * 登录学生的身份徽章。**只读，不能切换**——以谁登录就是谁，
 * 换学生必须退出登录重新验证（用户裁定 2026-07-31：切换器等于免验证看别人档案）。
 */
function PersonaBadge() {
  const { session } = useSession();
  const { t } = useI18n();
  if (session?.portal !== "student") return null;
  return (
    <span
      aria-label={t("chrome.persona")}
      data-persona-badge
      className="t-meta rounded-md border border-line bg-card px-2.5 py-1.5 text-fg-muted"
    >
      {session.studentId}
    </span>
  );
}

/**
 * R6-A：校方岗位徽章。**只读，不能切换**——以哪个岗位登录就是哪个岗位，
 * 换岗必须退出登录重新验证（与学生端同一裁定：切换器=免验证看别人的工作台）。
 */
function InstitutionRoleSwitch() {
  const { session } = useSession();
  const { t } = useI18n();
  if (session?.portal !== "institution") return null;
  return (
    <span
      aria-label={t("console.actingAs")}
      data-role-badge
      className="t-meta rounded-md border border-line bg-card px-2.5 py-1.5 text-fg-muted"
    >
      {t(`login.role.${session.role}` as Parameters<typeof t>[0])}
    </span>
  );
}

/** F1（2026-08-02 用户裁定）：demo 顶栏一键启停 Vertex Agent Engine。
 * 运行时按小时计费——这颗按钮的意义就是「演示前启动、演示完关闭」。
 * 任务在服务端跑（切页不中断）；环境不可控（云端容器无 adk）时按钮不出现。 */
function RuntimeToggle() {
  const { t } = useI18n();
  type Status = Awaited<ReturnType<typeof import("@/lib/api").api.agentRuntime>>;
  const [status, setStatus] = useState<Status | null>(null);
  const [gone, setGone] = useState(false);
  useEffect(() => {
    let stop = false;
    async function poll() {
      try {
        const { api } = await import("@/lib/api");
        const next = await api.agentRuntime();
        if (!stop) setStatus(next);
      } catch (err) {
        if ((err as { status?: number }).status === 503 && !stop) setGone(true);
      }
    }
    poll();
    const timer = setInterval(() => {
      // 空闲态低频、过渡态高频
      poll();
    }, status?.state === "starting" || status?.state === "stopping" ? 5000 : 30000);
    return () => { stop = true; clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.state]);

  async function toggle() {
    if (!status) return;
    const action = status.state === "running" ? "stop" : "start";
    try {
      const { api } = await import("@/lib/api");
      setStatus(await api.agentRuntimeCommand(action));
    } catch (err) {
      if ((err as { status?: number }).status === 503) setGone(true);
    }
  }

  // unknown = 后端如实承认"本环境探测不到运行时"——灯与按钮都不显示。
  // 2026-08-03 起云端探测走 Vertex REST 回退，线上通常能给出真值。
  if (!status || status.state === "unknown") return null;
  const busy = status.state === "starting" || status.state === "stopping";
  const running = status.state === "running";
  // 状态灯（2026-08-03 用户需求）：绿 = 引擎运行中 = 正在按小时计费；
  // 灰 = 已停止。灯只依赖 GET 探测——控制按钮不可用（云端 503）时灯照亮。
  const light = (
    <span
      data-runtime-light={status.state}
      title={t(running ? "runtime.light.running" : "runtime.light.stopped")}
      className="t-meta inline-flex items-center gap-1.5 text-fg-muted"
    >
      <span
        aria-hidden
        style={{
          width: 8, height: 8, borderRadius: 999,
          background: running ? "var(--color-moss-500)" : "var(--line-strong)",
          boxShadow: running ? "0 0 0 3px var(--color-moss-100)" : "none",
          animation: running ? "cp-pulse 1.6s ease-in-out infinite" : "none",
        }}
      />
      {t(running ? "runtime.light.on" : "runtime.light.off")}
    </span>
  );
  if (gone) return light;   // 本环境无控制通道：只报状态，不给会 503 的按钮
  return (
    <span className="inline-flex items-center gap-2.5">
      {light}
      <button
        type="button"
        data-runtime-toggle
        data-runtime-state={status.state}
        disabled={busy}
        onClick={toggle}
        title={status.error ?? undefined}
        className="pressable btn t-meta"
        style={{
          border: `1px solid ${running ? "var(--color-clay-500)" : "var(--line-strong)"}`,
          color: running ? "var(--color-clay-600)" : "var(--fg-muted)",
          background: running ? "var(--color-clay-100)" : "transparent",
          opacity: busy ? 0.7 : 1,
        }}
      >
        {busy
          ? `${t(status.state === "starting" ? "runtime.starting" : "runtime.stopping")} ${status.progress}%`
          : t(running ? "runtime.stop" : "runtime.start")}
      </button>
    </span>
  );
}

/** 「睡眠-负荷平衡」预警弹窗（2026-08-02 用户裁定，全链零 LLM）。
 *
 * warning（14 天内 ≥10 个「睡眠<7h 且学习>11h」日）→ 温和提醒，可关闭
 * （按 qualifying 数记忆，不重复骚扰）；assessment（28 天内 ≥20 日）→
 * 引导完成 ISI+PSS-10，**完成后（last_assessment_at 落档）自动解除**；
 * 分流由既有 §16.8 链路接手（初级自动联系辅导员 / 高压引导预约咨询室）。
 * 在 /wellbeing 页不弹——学生正在那里填表。 */
function WellbeingNudge() {
  const { t } = useI18n();
  const { session } = useSession();
  const pathname = usePathname();
  type Esc = Awaited<ReturnType<typeof import("@/lib/api").api.wellbeingEscalation>>;
  const [esc, setEsc] = useState<Esc | null>(null);
  const [acked, setAcked] = useState(false);
  const studentId = session?.portal === "student" ? session.studentId : null;
  useEffect(() => {
    if (!studentId) return;
    let stop = false;
    import("@/lib/api").then(({ api }) =>
      api.wellbeingEscalation(studentId)
        .then((next) => { if (!stop) setEsc(next); })
        .catch(() => {}));
    return () => { stop = true; };
  }, [studentId, pathname]);

  if (!esc || esc.tier === "none" || pathname === "/wellbeing") return null;
  const ackKey = `campuspath.wellbeing.ack.${studentId}.${esc.qualifying_days_14}`;
  if (esc.tier === "warning") {
    if (acked || (typeof window !== "undefined" && localStorage.getItem(ackKey))) {
      return null;
    }
  }
  if (esc.tier === "assessment" && esc.last_assessment_at) return null;

  const assessment = esc.tier === "assessment";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-5"
         data-wellbeing-nudge={esc.tier}
         style={{ background: "color-mix(in srgb, var(--fg) 30%, transparent)" }}>
      <div className="material-card w-full max-w-[460px] rounded-lg bg-card p-6">
        <div className="t-section text-fg">
          {t(assessment ? "wellbeing.nudge.assessTitle" : "wellbeing.nudge.title")}
        </div>
        <p className="t-body mt-2 text-fg-muted">
          {t(assessment ? "wellbeing.nudge.assessBody" : "wellbeing.nudge.body")
            .replace("{d14}", String(esc.qualifying_days_14))
            .replace("{d28}", String(esc.qualifying_days_28))}
        </p>
        <p className="t-micro mt-2 text-fg-faint">{t("wellbeing.nudge.basis")}</p>
        <div className="mt-4 flex items-center justify-end gap-2">
          {assessment ? (
            <Link href="/wellbeing" data-nudge-go
                  className="pressable btn btn-primary t-meta font-medium">
              {t("wellbeing.nudge.goAssess")}
            </Link>
          ) : (
            <>
              <Link href="/calendar" data-nudge-calendar
                    className="pressable btn btn-secondary t-meta">
                {t("wellbeing.nudge.goCalendar")}
              </Link>
              <button type="button" data-nudge-dismiss
                      className="pressable btn btn-primary t-meta font-medium"
                      onClick={() => {
                        localStorage.setItem(ackKey, "1");
                        setAcked(true);
                      }}>
                {t("wellbeing.nudge.dismiss")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LogoutButton() {
  const { session, logout } = useSession();
  const router = useRouter();
  const { t } = useI18n();
  if (!session) return null;
  return (
    <button
      type="button"
      data-logout
      onClick={() => {
        logout();
        router.replace("/login");
      }}
      className="pressable btn btn-ghost t-meta"
    >
      {t("auth.logout")}
    </button>
  );
}

function Sidebar() {
  const pathname = usePathname();
  const { t } = useI18n();
  const { session } = useSession();
  const reduce = useReducedMotion();

  if (!session) return null;
  const items = visibleItemsFor(session);

  return (
    <nav aria-label={t("app.name")} className="flex flex-col gap-6" data-sidebar>
      {NAV_GROUPS.map((groupKey) => {
        const groupItems = items.filter((i) => i.groupKey === groupKey);
        if (!groupItems.length) return null;
        return (
          <div key={groupKey}>
            <div className="t-micro mb-1.5 px-2 text-fg-faint">{t(groupKey)}</div>
            <ul className="flex flex-col gap-0.5">
              {groupItems.map((item) => {
                const active = pathname === item.href;
                return (
                  <li key={item.href} className="relative">
                    {active && (
                      // 选中态的位移用 layoutId 做共享过渡：切页时它是**滑过去**的，
                      // 不是在两处各自淡入淡出——位置关系因此始终连续。
                      <motion.span
                        layoutId="nav-active"
                        className="absolute inset-0 rounded-md"
                        style={{ background: "var(--accent-soft)" }}
                        transition={
                          reduce
                            ? { duration: 0.12 }
                            : { type: "spring", bounce: 0, duration: 0.35 }
                        }
                      />
                    )}
                    <Link
                      href={item.href}
                      data-nav-link={item.href}
                      aria-current={active ? "page" : undefined}
                      className="pressable relative flex items-center gap-2 rounded-md px-2 py-1.5"
                      style={{
                        color: active ? "var(--accent-deep)" : "var(--fg-muted)",
                        fontWeight: active ? 600 : 450,
                        fontSize: "0.875rem",
                      }}
                    >
                      <span
                        aria-hidden
                        className="h-1 w-1 shrink-0 rounded-full"
                        style={{
                          background: active ? "var(--accent)" : "var(--line-strong)",
                        }}
                      />
                      {t(item.labelKey)}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

/**
 * 门户守卫。三条规则，全部在跳转层面强制（服务端 RBAC 是第二道，独立成立）：
 *
 * 1. 未登录 → `/login`；
 * 2. 会话访问不属于自己的页面 → 送回**自己身份**的落地页。
 *    R7-A：这不只隔离两个门户，也隔离校方内部的岗位——advisor 直开
 *    /publisher 或 /console，对这个会话来说等于页面不存在；
 * 3. 已登录访问 `/login` → 送回自己身份的落地页。
 */
function usePortalGuard(): "checking" | "login" | "app" {
  const { session, ready } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  const onLogin = pathname === "/login";
  const guarded = NAV_ITEMS.find(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  const wrongDesk =
    session !== null &&
    guarded !== undefined &&
    !itemsFor(session).some((item) => item.href === guarded.href);

  useEffect(() => {
    if (!ready) return;
    if (session === null && !onLogin) router.replace("/login");
    else if (session !== null && (onLogin || wrongDesk)) {
      router.replace(homeFor(session));
    }
  }, [ready, session, onLogin, wrongDesk, router]);

  if (!ready) return "checking";
  if (onLogin) return session === null ? "login" : "checking";
  if (session === null || wrongDesk) return "checking";
  return "app";
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const { session } = useSession();
  const phase = usePortalGuard();

  // 登录页不带导航壳——门户的导航只属于登录后的那个门户
  if (phase === "login") return <>{children}</>;
  if (phase === "checking") return <div className="min-h-dvh" data-guard-checking />;

  const items = session ? visibleItemsFor(session) : [];

  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        {t("chrome.skipToContent")}
      </a>

      <header className="material-chrome sticky top-0 z-40 border-b border-line">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-3 px-5 py-3">
          <Link
            href={session ? homeFor(session) : "/login"}
            className="flex items-baseline gap-2"
          >
            <span
              className="t-title"
              style={{ color: "var(--accent)", letterSpacing: "-0.03em" }}
            >
              {t("app.name")}
            </span>
            <span className="t-meta hidden text-fg-faint sm:inline" data-portal-tag>
              {session?.portal === "institution"
                ? t("auth.portal.institution")
                : t("app.tagline")}
            </span>
          </Link>
          <div className="ms-auto flex flex-wrap items-center gap-2">
            <SyntheticBadge />
            <InstitutionRoleSwitch />
            <PersonaBadge />
            <LocaleSwitch />
            <RuntimeToggle />
            <LogoutButton />
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1240px] gap-8 px-5 py-8">
        <aside className="sticky top-[74px] hidden h-fit w-[210px] shrink-0 lg:block">
          <Sidebar />
        </aside>
        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>

      {session?.portal === "student" && <WellbeingNudge />}

      {/* 窄屏：导航折到底部，仍然是同一份门户过滤后的 items */}
      <div className="material-chrome sticky bottom-0 z-40 border-t border-line px-4 py-3 lg:hidden">
        <div className="flex gap-2 overflow-x-auto">
          {items.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="t-meta whitespace-nowrap rounded-sm border border-line px-2.5 py-1 text-fg-muted"
            >
              {t(item.labelKey)}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
