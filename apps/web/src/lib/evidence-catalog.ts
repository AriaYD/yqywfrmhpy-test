/** 权威证据参考表（A，2026-08-02）。
 * 数据由 seed/compile_employment_pack.py 生成（单一出处，勿手改）：
 * 每条带官方 URL 与核查时间，goals 页把 facet.evidence_refs 展开为可点链接。 */
import catalog from "@/data/evidence-catalog.json";

export type EvidenceEntry = {
  id: string;
  name_zh: string;
  name_en: string;
  kind: "competition" | "credential" | "activity";
  organizer: string;
  tier: "national" | "provincial" | "city_campus" | "industry_flagship";
  applicable_roles: string[];
  official_url: string;
  checked_at: string;
  note_zh: string;
};

export const EVIDENCE_BY_ID: ReadonlyMap<string, EvidenceEntry> = new Map(
  (catalog.entries as EvidenceEntry[]).map((entry) => [entry.id, entry]),
);
