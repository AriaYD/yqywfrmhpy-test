"use client";

/**
 * 全站共用的视觉原语。
 *
 * 两个"签名元素"在这里定义，全站复用，别处不再自造：
 *
 * * :func:`TriState` —— 三值指示器。UNKNOWN 用**斜纹**，既不是绿也不是红。
 *   产品的整个论证建立在"解析不出来 ≠ 你不合格"上，配色必须承认第三种状态。
 * * :func:`CredentialChip` —— 凭据票根。任何来自 Rules 的结论都挂着它，
 *   带真实的 validation_id。看得见的审计链比一句"我们很严谨"有用。
 */

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n, type MessageKey } from "@/i18n";

/* ------------------------------------------------------------------ */
/* 布局                                                                */
/* ------------------------------------------------------------------ */

export function PageHeader({
  titleKey,
  leadKey,
  children,
}: {
  titleKey: MessageKey;
  leadKey?: MessageKey;
  children?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <header className="mb-8">
      <h1 className="t-display text-fg">{t(titleKey)}</h1>
      {leadKey && (
        <p className="t-body mt-3 max-w-[60ch] text-fg-muted">{t(leadKey)}</p>
      )}
      {children && <div className="mt-5">{children}</div>}
    </header>
  );
}

/**
 * ``...rest`` 是有意的：不透传的话 `<Card data-x="…">` 会**静默丢掉**那个属性，
 * 而浏览器实测正是靠 `data-*` 断言的——一条断言查不到东西，
 * 分不清是"页面坏了"还是"属性被组件吃了"。实测里踩过一次。
 */
export function Card({
  children,
  className = "",
  as: Tag = "section",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "div" | "li";
} & Record<string, unknown>) {
  return (
    <Tag
      {...rest}
      className={`rounded-lg border border-line bg-card p-5 ${className}`}
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      {children}
    </Tag>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="t-section mb-3 text-fg">{children}</h2>;
}

export function Grid({
  children,
  min = 260,
}: {
  children: ReactNode;
  min?: number;
}) {
  return (
    <div
      className="grid gap-4"
      style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))` }}
    >
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 签名元素 1：三值状态                                                 */
/* ------------------------------------------------------------------ */

export type TriValue = "met" | "not_met" | "unknown";

const TRI_KEY: Record<TriValue, MessageKey> = {
  met: "state.met",
  not_met: "state.notMet",
  unknown: "state.unknown",
};

export function TriState({ value, label }: { value: TriValue; label?: string }) {
  const { t } = useI18n();
  const text = label ?? t(TRI_KEY[value]);
  const shared =
    "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 t-meta font-medium";

  if (value === "unknown") {
    return (
      <span
        className={`${shared} hatch-unknown`}
        style={{ borderColor: "var(--hatch)", color: "var(--hatch-ink)" }}
        title={t("state.unknown.explain")}
        data-tri="unknown"
      >
        <span
          aria-hidden
          className="h-2 w-2 rounded-full border-[1.5px]"
          style={{ borderColor: "var(--hatch)" }}
        />
        {text}
      </span>
    );
  }
  const met = value === "met";
  return (
    <span
      className={shared}
      data-tri={value}
      style={{
        borderColor: met ? "var(--color-moss-500)" : "var(--color-clay-500)",
        color: met ? "var(--color-moss-600)" : "var(--color-clay-600)",
        background: met ? "var(--color-moss-100)" : "var(--color-clay-100)",
      }}
    >
      <span
        aria-hidden
        className="h-2 w-2 rounded-full"
        style={{
          background: met ? "var(--color-moss-500)" : "var(--color-clay-500)",
        }}
      />
      {text}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* 签名元素 2：凭据票根                                                 */
/* ------------------------------------------------------------------ */

export function CredentialChip({ validationId }: { validationId?: string | null }) {
  const { t } = useI18n();
  if (!validationId) {
    return (
      <span className="t-mono text-fg-faint" data-credential="none">
        {t("credential.none")}
      </span>
    );
  }
  return (
    <span
      className="credential-chip inline-flex items-center gap-1.5 rounded-sm px-2 py-[3px]"
      style={{
        border: "1px dashed var(--hatch)",
        color: "var(--hatch-ink)",
        background: "color-mix(in srgb, var(--hatch) 8%, transparent)",
      }}
      title={t("credential.explain")}
      data-credential={validationId}
    >
      <span className="t-micro" style={{ letterSpacing: "0.08em" }}>
        {t("credential.label")}
      </span>
      <code className="t-mono">{validationId.slice(0, 12)}…</code>
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* 状态                                                                */
/* ------------------------------------------------------------------ */

export function Loading() {
  const { t } = useI18n();
  return (
    <p className="t-meta text-fg-faint" role="status" data-state="loading">
      {t("app.loading")}
    </p>
  );
}

export function Empty({ messageKey }: { messageKey?: MessageKey }) {
  const { t } = useI18n();
  return (
    <p className="t-meta text-fg-faint" data-state="empty">
      {t(messageKey ?? "app.empty")}
    </p>
  );
}

/**
 * 错误态。**503 与 404 分开说**：
 * 503 = 这条路做完了但依赖不可用；404 = 这个学生现在真的没有这个东西。
 * 都写成"加载失败"会让人以为前端坏了。
 */
export function Failure({
  error,
  emptyKey,
  onRetry,
}: {
  error: Error & { isUnavailable?: boolean; isMissing?: boolean; status?: number };
  emptyKey?: MessageKey;
  onRetry?: () => void;
}) {
  const { t } = useI18n();
  if (error.isMissing) return <Empty messageKey={emptyKey} />;
  return (
    <div
      className="rounded-md border border-line bg-bg-sunk p-4"
      role="alert"
      data-state={error.isUnavailable ? "unavailable" : "error"}
    >
      <p className="t-meta text-fg-muted">
        {error.isUnavailable ? t("app.offline") : t("app.error")}
      </p>
      <p className="t-mono mt-1 text-fg-faint">{error.message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="pressable btn btn-secondary t-meta mt-3"
        >
          {t("app.retry")}
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 数据条与数值                                                         */
/* ------------------------------------------------------------------ */

export function Metric({
  label,
  value,
  unit,
  tone = "default",
}: {
  label: string;
  value: string | number;
  unit?: string;
  tone?: "default" | "warn" | "good";
}) {
  const color =
    tone === "warn"
      ? "var(--color-clay-600)"
      : tone === "good"
        ? "var(--color-moss-600)"
        : "var(--fg)";
  return (
    <div>
      <div className="t-micro text-fg-faint">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span
          className="tabular-nums"
          style={{ color, fontSize: "1.5rem", fontWeight: 700, letterSpacing: "-0.02em", fontFamily: "var(--font-display, ui-sans-serif), var(--font-sans)" }}
        >
          {value}
        </span>
        {unit && <span className="t-meta text-fg-faint">{unit}</span>}
      </div>
    </div>
  );
}

/** 水平占比条。宽度用 spring 过渡，可被随时打断（ui-ux-pro-max interruptible）。 */
export function Bar({
  ratio,
  tone = "accent",
}: {
  ratio: number;
  tone?: "accent" | "warn" | "hatch";
}) {
  const reduce = useReducedMotion();
  const clamped = Math.max(0, Math.min(1, ratio));
  const background =
    tone === "warn"
      ? "var(--color-clay-500)"
      : tone === "hatch"
        ? "var(--hatch)"
        : "var(--accent)";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-bg-sunk">
      <motion.div
        className="h-full rounded-full"
        style={{ background }}
        initial={{ width: 0 }}
        animate={{ width: `${clamped * 100}%` }}
        transition={
          reduce
            ? { duration: 0.12 }
            : { type: "spring", bounce: 0, duration: 0.4 }
        }
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 开关与分段控件                                                       */
/* ------------------------------------------------------------------ */

export function Toggle({
  checked,
  onChange,
  labelledBy,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  labelledBy?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      onClick={() => onChange(!checked)}
      className="pressable relative h-[26px] w-[46px] shrink-0 rounded-full border"
      style={{
        background: checked ? "var(--accent)" : "var(--bg-sunk)",
        borderColor: checked ? "var(--accent)" : "var(--line-strong)",
      }}
    >
      <motion.span
        className="absolute top-[2px] block h-[20px] w-[20px] rounded-full bg-white"
        style={{ boxShadow: "0 1px 3px rgb(0 0 0 / 0.3)" }}
        animate={{ x: checked ? 22 : 2 }}
        transition={
          reduce ? { duration: 0.12 } : { type: "spring", bounce: 0.2, duration: 0.3 }
        }
      />
    </button>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className="pressable t-meta relative rounded-sm px-3 py-1.5"
            style={{
              color: active ? "var(--accent-fg)" : "var(--fg-muted)",
              background: active ? "var(--accent-deep)" : "transparent",
              fontWeight: active ? 600 : 500,
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 抽屉                                                                */
/* ------------------------------------------------------------------ */

/**
 * 侧滑面板。进出**走同一条路径**（ui-ux-pro-max continuity/modal-motion），
 * 材质是 blur + scale 一起动，读起来像一层真的玻璃到位，而不是简单淡入。
 */
export function Drawer({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  const reduce = useReducedMotion();
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50" data-drawer="open">
      <motion.button
        type="button"
        aria-label={title}
        onClick={onClose}
        className="absolute inset-0 bg-black/45"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: reduce ? 0.12 : 0.22 }}
      />
      <motion.div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="material-modal absolute inset-y-0 right-0 w-full max-w-[440px] overflow-y-auto rounded-l-lg border-l border-line p-6"
        initial={reduce ? { opacity: 0 } : { x: 32, opacity: 0, scale: 0.99 }}
        animate={reduce ? { opacity: 1 } : { x: 0, opacity: 1, scale: 1 }}
        transition={
          reduce ? { duration: 0.12 } : { type: "spring", bounce: 0, duration: 0.34 }
        }
      >
        {children}
      </motion.div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 合成数据标记（D1 要求全站可见）                                       */
/* ------------------------------------------------------------------ */

export function SyntheticBadge({ full = false }: { full?: boolean }) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  return (
    <div data-synthetic-badge className={full ? "block w-full" : "inline-block"}>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="pressable t-micro inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
        style={{
          border: "1px solid var(--hatch)",
          color: "var(--hatch-ink)",
          background: "color-mix(in srgb, var(--hatch) 10%, transparent)",
        }}
      >
        <span aria-hidden className="hatch-unknown h-2.5 w-2.5 rounded-[2px] border" />
        {t("app.synthetic")}
      </button>
      {(expanded || full) && (
        /* 用户裁定 2026-08-02：说明分行排版、宽度与下方模块自适应对齐
           （不再截 46ch；父容器改 block 让宽度跟随页面栏宽）；
           真实源逐条编号，尾注单独一行 */
        <div className="t-meta mt-2 w-full text-fg-faint" data-synthetic-detail>
          <p>{t("app.syntheticFull")}</p>
          <ol className="mt-1.5 flex list-none flex-col gap-1 ps-0">
            {(["1", "2", "3", "4"] as const).map((n) => (
              <li key={n} className="flex gap-1.5">
                <span aria-hidden>
                  {{ "1": "①", "2": "②", "3": "③", "4": "④" }[n]}
                </span>
                <span className="min-w-0">
                  {t(`app.realSource.${n}` as Parameters<typeof t>[0])}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-1.5">{t("app.realSourceNote")}</p>
        </div>
      )}
    </div>
  );
}
