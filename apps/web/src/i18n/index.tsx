"use client";

/**
 * 双语运行时。三条约束：
 *
 * 1. **组件里不允许出现任何一种语言的字面量**——一律走 `t(key)`。
 *    漏掉的键 TypeScript 会当场报错（`MessageKey` 是联合类型）。
 * 2. 选择**持久化**到 localStorage，并同步写 `<html lang>`，
 *    这样屏幕阅读器和 `:lang()` 选择器都跟着变。
 * 3. 首帧不能闪：`layout.tsx` 里有一段内联脚本在 hydration 前就把
 *    lang / data-theme 打到 <html> 上。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { en, type MessageKey } from "./en";
import { toHant } from "./hant";
import { zhHans } from "./zh-Hans";
import { zhHant } from "./zh-Hant";

export const LOCALES = ["zh-Hans", "zh-Hant", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DICTS: Record<Locale, Record<MessageKey, string>> = {
  "zh-Hans": zhHans,
  "zh-Hant": zhHant,
  en,
};

export const LOCALE_STORAGE_KEY = "campuspath.locale";
export const DEFAULT_LOCALE: Locale = "zh-Hans";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

type Ctx = {
  locale: Locale;
  setLocale: (next: Locale) => void;
  t: (key: MessageKey) => string;
};

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  // 读回持久化的选择。放在 effect 里，服务端渲染与首帧保持一致，
  // 真正防闪的是 layout 里那段内联脚本。
  useEffect(() => {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (isLocale(stored) && stored !== locale) setLocaleState(stored);
    // 仅在挂载时读一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
  }, []);

  const t = useCallback(
    (key: MessageKey) => DICTS[locale][key] ?? DICTS[DEFAULT_LOCALE][key] ?? key,
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n 必须在 <I18nProvider> 内使用");
  return ctx;
}

/**
 * 契约里的 `LocalizedText` 按当前语言取值，缺失时回落到另一种语言而不是空白。
 * 契约只有 zh_Hans / en 两个字段——繁体界面下取简体值并**确定性**转换（OpenCC），
 * 不改契约、不调模型。
 */
export function localized(
  text: { zh_Hans?: string | null; en?: string | null } | null | undefined,
  locale: Locale,
): string {
  if (!text) return "";
  const wantsChinese = locale.startsWith("zh");
  const primary = wantsChinese ? text.zh_Hans : text.en;
  const fallback = wantsChinese ? text.en : text.zh_Hans;
  const value = primary || fallback || "";
  return locale === "zh-Hant" && value === (text.zh_Hans ?? "")
    ? toHant(value)
    : value;
}

/**
 * 组件内联双语文案的取用口。**这是组件里唯一允许出现中文字面量的通道**——
 * 简体原文进来，繁体界面下自动转换；不用它而写 `locale === "zh-Hans"` 三目，
 * 繁体用户就会拿到英文。
 */
export function pickLang(locale: Locale, zh: string, en_: string): string {
  if (!locale.startsWith("zh")) return en_;
  return locale === "zh-Hant" ? toHant(zh) : zh;
}

export type { MessageKey };
