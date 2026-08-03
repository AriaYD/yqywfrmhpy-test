/** 真实抓取源判定（用户裁定 D，2026-08-02）：
 * 广场与 For You 卡片必须一眼分清「官方实抓」与「合成演示」。
 * 判定按 source_id / 条目 id 前缀，与服务端源注册表的真实源集合对应：
 * - hkust_engage：入库冻结的官方活动快照
 * - OPP-LIVE-*：全链源（活动日历）运行时直发的官方条目
 * - OPP-POL-*：政策源变更提醒卡（回链政府/校方官方页面）
 */
// ⚠️ 待办（审查 #19）：这份名单与 source_registry.json 的 is_real_fetch 存在
// 漂移风险——正解是后端在 Opportunity 上带派生字段。新增真实源上广场时同步这里。
const REAL_SOURCE_IDS = new Set(["hkust_engage", "hkust-event-calendar"]);

export function isOfficialLive(opportunity: {
  source_id?: string | null;
  opportunity_id: string;
}): boolean {
  return (
    REAL_SOURCE_IDS.has(opportunity.source_id ?? "") ||
    opportunity.opportunity_id.startsWith("OPP-LIVE-") ||
    opportunity.opportunity_id.startsWith("OPP-POL-")
  );
}
