import { toHant } from "@/i18n/hant";
import type { Locale, MessageKey } from "@/i18n";

/**
 * 要求类别 → 三层归类（K/L，2026-07-31 用户裁定）：
 * 硬性要求 / 软实力 / 特殊约束——与目标拆解 Pack 的三层一致。
 *
 * 归层按 LinkedIn 通用写法：语言与证书可考证、可出示 → 硬性；
 * 沟通协作人脉是从经历取证的个人素质 → 软实力；身份资格 → 特殊约束。
 * （Pack 内个别类别按方向有出入——如读研方向把 network 视为硬性——
 * 这里是**展示层**的统一归类，拆解面板仍显示 Pack 自己的分层。）
 */
export type RequirementLayer = "hard" | "soft" | "constraint";

export const LAYERS: readonly RequirementLayer[] = ["hard", "soft", "constraint"];

export const LAYER_KEY: Record<RequirementLayer, MessageKey> = {
  hard: "goals.decomp.hard",
  soft: "goals.decomp.soft",
  constraint: "goals.decomp.constraint",
};

export const LAYER_OF: Record<string, RequirementLayer> = {
  coursework: "hard",
  technical_skill: "hard",
  research_experience: "hard",
  industry_experience: "hard",
  project_portfolio: "hard",
  credential: "hard",
  language: "hard",
  teamwork_evidence: "soft",
  communication: "soft",
  network: "soft",
  eligibility_status: "constraint",
};

/** 类别的可读双语标签（契约枚举 → 展示文案，两侧都有出处，不现翻）。 */
export const CATEGORY_LABEL: Record<string, { zh: string; en: string }> = {
  coursework: { zh: "课程修读", en: "Coursework" },
  technical_skill: { zh: "技术技能", en: "Technical skills" },
  research_experience: { zh: "科研经历", en: "Research experience" },
  industry_experience: { zh: "行业经历", en: "Industry experience" },
  project_portfolio: { zh: "项目作品集", en: "Project portfolio" },
  teamwork_evidence: { zh: "团队协作证据", en: "Teamwork evidence" },
  communication: { zh: "沟通表达", en: "Communication" },
  credential: { zh: "证书资质", en: "Credentials" },
  language: { zh: "语言能力", en: "Languages" },
  network: { zh: "人脉网络", en: "Network" },
  eligibility_status: { zh: "资格身份", en: "Eligibility status" },
};

export function layerOf(category: string): RequirementLayer {
  return LAYER_OF[category] ?? "hard";
}

export function categoryLabel(category: string, locale: Locale): string {
  const entry = CATEGORY_LABEL[category];
  if (!entry) return category;
  if (!locale.startsWith("zh")) return entry.en;
  return locale === "zh-Hant" ? toHant(entry.zh) : entry.zh;
}

/** `REQ-{goal_id}-{category}` → category（类别值只含下划线，取最后一段安全）。 */
export function categoryFromRequirementId(id: string): string {
  return id.slice(id.lastIndexOf("-") + 1);
}
