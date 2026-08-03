"use client";

/**
 * 交互原语（B2，clay 重构新增）。
 *
 * 样式的单一出处在 globals.css 的 `.btn/.field/.chip` 类——这里只是
 * React 糖衣：把类名组合、按压反馈与 `{...rest}` 全量透传封装起来。
 * **透传是硬要求**：`data-*` 断言、aria、事件一个都不能被组件吃掉
 * （教训见 ui.tsx 的 Card 注释）。
 *
 * 存量页面的手写 button 不强制迁移到这里；本组件用于**本就要重写 JSX**
 * 的位置。批量存量替换走 `.btn-*` 类名映射（见实施方案 §新原语）。
 */

import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  className = "",
  children,
  ...rest
}: {
  variant?: ButtonVariant;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`pressable btn btn-${variant} t-meta font-medium ${className}`}
    >
      {children}
    </button>
  );
}

export function Input({
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={`field t-meta w-full ${className}`} />;
}

export function Select({
  className = "",
  children,
  ...rest
}: { children: ReactNode } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={`field t-meta w-full ${className}`}>
      {children}
    </select>
  );
}

/** pastel 语义色块标签。刻意没有 ochre 档——UNKNOWN 只能走 TriState/斜纹。 */
export function Chip({
  tone = "neutral",
  className = "",
  children,
  ...rest
}: {
  tone?: "sage" | "mist" | "blossom" | "peach" | "neutral";
  children: ReactNode;
} & Record<string, unknown>) {
  return (
    <span {...rest} className={`chip chip-${tone} t-meta ${className}`}>
      {children}
    </span>
  );
}
