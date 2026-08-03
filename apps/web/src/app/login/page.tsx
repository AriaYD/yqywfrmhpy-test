"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { useI18n } from "@/i18n";
import {
  LOGIN_INSTITUTION_ROLES,
  PERSONA_IDS,
  useSession,
  type InstitutionRole,
  type PersonaId,
} from "@/app/providers";
import { homeFor } from "@/components/nav";
import { LocaleSwitch } from "@/components/shell";
import { SyntheticBadge } from "@/components/ui";

/**
 * 两个门户各自的登录入口——同一页、两张卡，但**提交后进入的是完全
 * 不同的壳**：学生会话只装学生导航，校方会话只装校方导航。
 *
 * 这是合成登录（口令由服务端环境变量校验，不在界面上）：认证是演示性的，授权是真实的——
 * 服务端 RBAC 按 `X-CampusPath-Role` 判定，越权一律 403（D5）。
 */

function PortalCard({
  side,
  children,
}: {
  side: "student" | "institution";
  children: React.ReactNode;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.section
      data-login-card={side}
      initial={reduce ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", bounce: 0, duration: 0.45, delay: side === "student" ? 0.05 : 0.12 }}
      className="flex-1 rounded-lg border border-line bg-card p-6"
      style={{ minWidth: "min(100%, 320px)", boxShadow: "var(--shadow-card)" }}
    >
      {children}
    </motion.section>
  );
}

function PasswordField({
  id,
  value,
  onChange,
  error,
}: {
  id: string;
  value: string;
  onChange: (next: string) => void;
  error: boolean;
}) {
  const { t } = useI18n();
  return (
    <label className="block">
      <span className="t-meta mb-1 block text-fg-muted">{t("login.password")}</span>
      <input
        id={id}
        type="password"
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error || undefined}
        className="field w-full px-3 py-2"
        style={{ borderColor: error ? "var(--color-clay-600)" : "var(--line)" }}
      />
      <span
        className="t-meta mt-1 block"
        style={{ color: error ? "var(--color-clay-600)" : "var(--fg-faint)" }}
        data-password-hint
      >
        {error ? t("login.wrongPassword") : t("login.passwordHint")}
      </span>
    </label>
  );
}

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { loginStudent, loginInstitution } = useSession();

  const [studentId, setStudentId] = useState<PersonaId>(PERSONA_IDS[0]);
  const [studentPw, setStudentPw] = useState("");
  const [studentError, setStudentError] = useState(false);

  const [role, setRole] = useState<InstitutionRole>(LOGIN_INSTITUTION_ROLES[0]);
  const [rolePw, setRolePw] = useState("");
  const [roleError, setRoleError] = useState(false);

  // 2026-08-02 用户裁定：口令校验移到服务端（/api/auth/passcode 比对
  // 环境变量并签发门 cookie）——代码、快照、界面上都没有口令本体；
  // 本地未设变量时门不存在，任何输入放行。
  const verifyPasscode = async (passcode: string): Promise<boolean> => {
    try {
      const res = await fetch("/api/auth/passcode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode }),
      });
      return res.ok;
    } catch {
      return false;
    }
  };

  const submitStudent = async (e: FormEvent) => {
    e.preventDefault();
    if (!(await verifyPasscode(studentPw))) return setStudentError(true);
    loginStudent(studentId);
    router.replace(homeFor({ portal: "student" }));
  };

  const submitInstitution = async (e: FormEvent) => {
    e.preventDefault();
    if (!(await verifyPasscode(rolePw))) return setRoleError(true);
    loginInstitution(role);
    // R7-A：落地页跟着岗位走——advisor 直达工作台，而不是所有人都先看投稿台
    router.replace(homeFor({ portal: "institution", role }));
  };

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="mx-auto flex w-full max-w-[880px] items-center gap-3 px-5 py-4">
        <span className="t-title" style={{ color: "var(--accent)", letterSpacing: "-0.03em" }}>
          {t("app.name")}
        </span>
        <span className="t-meta hidden text-fg-faint sm:inline">{t("app.tagline")}</span>
        <div className="ms-auto flex items-center gap-2">
          <SyntheticBadge />
          <LocaleSwitch />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[880px] flex-1 px-5 pb-16 pt-8">
        <h1 className="t-display mb-2">{t("login.title")}</h1>
        <p className="t-body mb-8 max-w-[560px] text-fg-muted">{t("login.subtitle")}</p>

        <div className="flex flex-wrap gap-5">
          <PortalCard side="student">
            <form onSubmit={submitStudent} className="flex flex-col gap-4">
              <div>
                <h2 className="t-title mb-1">{t("auth.portal.student")}</h2>
                <p className="t-meta text-fg-muted">{t("login.studentLead")}</p>
              </div>
              <label className="block">
                <span className="t-meta mb-1 block text-fg-muted">{t("login.identity")}</span>
                <select
                  data-login-student-id
                  value={studentId}
                  onChange={(e) => setStudentId(e.target.value as PersonaId)}
                  className="field w-full px-3 py-2"
                >
                  {PERSONA_IDS.filter((id) => id === "STU-A").map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
                </select>
              </label>
              <PasswordField
                id="student-password"
                value={studentPw}
                onChange={(next) => {
                  setStudentPw(next);
                  setStudentError(false);
                }}
                error={studentError}
              />
              <button
                type="submit"
                data-login-student
                className="pressable btn btn-primary px-4 py-2.5 font-semibold"
              >
                {t("login.enterStudent")}
              </button>
            </form>
          </PortalCard>

          <PortalCard side="institution">
            <form onSubmit={submitInstitution} className="flex flex-col gap-4">
              <div>
                <h2 className="t-title mb-1">{t("auth.portal.institution")}</h2>
                <p className="t-meta text-fg-muted">{t("login.institutionLead")}</p>
              </div>
              <div>
                <span className="t-meta mb-1 block text-fg-muted">{t("login.identity")}</span>
                {/* R6-B：4 类入口，各带岗位小字说明 */}
                <div className="flex flex-col gap-1.5" data-login-roles>
                  {LOGIN_INSTITUTION_ROLES.map((r) => (
                    <button
                      key={r}
                      type="button"
                      data-login-role-option={r}
                      aria-pressed={role === r}
                      onClick={() => setRole(r)}
                      className="pressable rounded-md border px-3 py-2 text-start"
                      style={{
                        borderColor: role === r ? "var(--accent)" : "var(--line)",
                        background: role === r ? "var(--accent-soft)" : "var(--bg-sunk)",
                      }}
                    >
                      <span className="t-body block text-fg">
                        {t(`login.role.${r}` as Parameters<typeof t>[0])}
                      </span>
                      <span className="t-micro block text-fg-faint">
                        {t(`login.role.${r}.hint` as Parameters<typeof t>[0])}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
              <PasswordField
                id="institution-password"
                value={rolePw}
                onChange={(next) => {
                  setRolePw(next);
                  setRoleError(false);
                }}
                error={roleError}
              />
              <button
                type="submit"
                data-login-institution
                className="pressable btn btn-secondary px-4 py-2.5 font-semibold"
              >
                {t("login.enterInstitution")}
              </button>
            </form>
          </PortalCard>
        </div>
      </main>
    </div>
  );
}
