"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { I18nProvider } from "@/i18n";
import { setRole as setApiRole } from "@/lib/api";
import { clearResourceCache } from "@/lib/useResource";

/* ------------------------------------------------------------------ */
/* 主题：唯一浅色（2026-08-03 用户裁定禁用深色——ThemeProvider/切换器/  */
/* 暗色 CSS 已整体移除，localStorage 残留的 campuspath.theme 无人读取） */
/* ------------------------------------------------------------------ */
/* 会话（两个门户，各自登录）                                            */
/* ------------------------------------------------------------------ */

/**
 * 学生端与校方端是**两个门户**：各自登录、各自导航、互不可见。
 * 曾经是同一个壳里一个角色下拉随便切——学生页面和校方控制台混在一起，
 * 一次角色残留（reviewer 留在 localStorage）就让学生页整页 403。
 *
 * D1 要求 3 个本科求职 Demo Persona 可切换，且**前端零硬编码**——
 * 会话只存 student_id，姓名、专业、年级一律从 `/profile` 读。
 *
 * 前端会话是**合成登录**（Synthetic / Demo）：声明身份，判定在服务端——
 * `X-CampusPath-Role` 是授权层的输入，不是认证。真实部署换成 IAM 断言时，
 * 这个 Provider 整个消失，而服务端一行不用改。D5 的隔离验证仍然成立：
 * 以校方身份登录后对学生禁区端点的主动探测全部 403（见 /console）。
 */
export const PERSONA_IDS = ["STU-A", "STU-B", "STU-C"] as const;
export type PersonaId = (typeof PERSONA_IDS)[number];

export const INSTITUTION_ROLES = [
  "publisher",
  "reviewer",
  "curator",
  "connector_admin",
  "career_center_admin",
  "wellbeing_coordinator",
  "advisor",
] as const;

/**
 * R6-B（2026-08-01）：登录入口只有 4 类。Career Center 现实中一人身兼
 * 审核/策展/接入三职——合并为复合岗位 career_center_admin；
 * wellbeing_coordinator 即学校心理咨询室部门。
 * 旧的细分角色仍在 INSTITUTION_ROLES 里（会话解析兼容 + 真实部署可拆）。
 */
export const LOGIN_INSTITUTION_ROLES = [
  "publisher",
  "career_center_admin",
  "wellbeing_coordinator",
  "advisor",
] as const;
export type InstitutionRole = (typeof INSTITUTION_ROLES)[number];

export const ROLES = ["student", ...INSTITUTION_ROLES] as const;
export type Role = (typeof ROLES)[number];

export type Portal = "student" | "institution";

export type Session =
  | { portal: "student"; studentId: PersonaId }
  | { portal: "institution"; role: InstitutionRole };

export const SESSION_STORAGE_KEY = "campuspath.session";
/** 旧的分离式存储。读到就迁移并删除，防止 reviewer 残留把学生页打成 403。 */
const LEGACY_KEYS = ["campuspath.role", "campuspath.persona"] as const;

/** 合成登录的演示口令（全站 Synthetic / Demo，界面上明示，不装作机密）。 */

function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as Partial<Session> & Record<string, unknown>;
    if (
      data.portal === "student" &&
      (PERSONA_IDS as readonly string[]).includes(String(data.studentId))
    ) {
      return { portal: "student", studentId: data.studentId as PersonaId };
    }
    if (
      data.portal === "institution" &&
      (INSTITUTION_ROLES as readonly string[]).includes(String(data.role))
    ) {
      return { portal: "institution", role: data.role as InstitutionRole };
    }
  } catch {
    /* 损坏的会话按未登录处理 */
  }
  return null;
}

type SessionCtx = {
  session: Session | null;
  /** localStorage 已读完。守卫在 ready 之前不重定向，避免误踢回登录页。 */
  ready: boolean;
  loginStudent: (id: PersonaId) => void;
  loginInstitution: (role: InstitutionRole) => void;
  logout: () => void;
};

const SessionContext = createContext<SessionCtx | null>(null);

function applyApiRole(session: Session | null): void {
  // 未登录回落到 student：api.ts 的纪律是"忘了设等于权限最小"，
  // 而守卫会在任何页面发请求之前把未登录会话送去 /login。
  setApiRole(session === null || session.portal === "student" ? "student" : session.role);
}

function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = parseSession(window.localStorage.getItem(SESSION_STORAGE_KEY));
    LEGACY_KEYS.forEach((key) => window.localStorage.removeItem(key));
    if (stored) {
      setSession(stored);
      applyApiRole(stored);
    }
    setReady(true);
  }, []);

  const persist = useCallback((next: Session | null) => {
    setSession(next);
    applyApiRole(next);
    // 身份变了就清会话数据缓存——残留跨身份是泄漏的前身（审查 M-4）
    clearResourceCache();
    if (next === null) window.localStorage.removeItem(SESSION_STORAGE_KEY);
    else window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(next));
  }, []);

  const value = useMemo<SessionCtx>(
    () => ({
      session,
      ready,
      loginStudent: (id) => persist({ portal: "student", studentId: id }),
      loginInstitution: (role) => persist({ portal: "institution", role }),
      logout: () => persist(null),
    }),
    [session, ready, persist],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionCtx {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession 必须在 <SessionProvider> 内使用");
  return ctx;
}

/* —— 兼容旧接口：14 个页面无需改动 —— */

/**
 * 登录的是谁，整个会话就是谁。**没有 setStudentId**——换学生只有一条路：
 * 退出登录，回 /login 以另一个身份进来。不经登录验证就切到别的学生
 * 看到别人的档案，是被用户明确否决的设计（2026-07-31）。
 */
type PersonaCtx = { studentId: PersonaId };

export function usePersona(): PersonaCtx {
  const { session } = useSession();
  const studentId =
    session?.portal === "student" ? session.studentId : PERSONA_IDS[0];
  return { studentId };
}

/**
 * R6-A：以哪个岗位登录就是哪个岗位——**没有 setRole**。换岗只有一条路：
 * 退出登录重新验证（与学生端同一裁定：切换器=免验证看别人的工作台）。
 */
type RoleCtx = { role: Role };

export function useRole(): RoleCtx {
  const { session } = useSession();
  const role: Role =
    session?.portal === "institution" ? session.role : "student";
  return { role };
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <I18nProvider>
      <SessionProvider>{children}</SessionProvider>
    </I18nProvider>
  );
}
