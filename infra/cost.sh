#!/usr/bin/env bash
# 每日成本检查（Plan R7）。**只读。**
#
#   bash infra/cost.sh
#
# 赠金 HK$1,568.39，2026-09-27 过期。这个脚本回答两个问题：
#   1. 还剩多少天；
#   2. 现在有什么在持续烧钱。
#
# 它**不查精确账单**：准确的用量数据要导出到 BigQuery 才拿得到，
# 为看一眼花销而建一条 BigQuery 导出管道并不划算。
# 与其给一个不准的数字，不如给准确的"哪些资源正在计费"。

set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.sh

EXPIRY="2026-09-27"
TODAY=$(date +%Y-%m-%d)
DAYS_LEFT=$(( ( $(date -j -f "%Y-%m-%d" "$EXPIRY" +%s 2>/dev/null || date -d "$EXPIRY" +%s) \
              - $(date -j -f "%Y-%m-%d" "$TODAY" +%s 2>/dev/null || date -d "$TODAY" +%s) ) / 86400 ))

printf "\n${DIM}CampusPath 成本检查 · %s${NC}\n" "$TODAY"

step "赠金"
if [ "$DAYS_LEFT" -lt 0 ]; then
  bad "赠金已于 $EXPIRY 过期，此后开销打到个人卡"
elif [ "$DAYS_LEFT" -lt 14 ]; then
  bad "赠金剩 $DAYS_LEFT 天（$EXPIRY 到期）——比比赛截止更硬的死线"
else
  ok "赠金剩 $DAYS_LEFT 天（$EXPIRY 到期）"
fi

step "正在计费的资源"
BILLING_NOW=0

RUNNING_VMS=$(gcloud compute instances list --project="$PROJECT_ID" \
  --filter='status=RUNNING' --format='value(name,machineType.basename(),zone)' 2>/dev/null || true)
if [ -n "$RUNNING_VMS" ]; then
  BILLING_NOW=1
  bad "运行中的 VM（按小时计费）："
  echo "$RUNNING_VMS" | sed 's/^/      /'
  warn "  不用时：bash infra/moodle.sh stop --apply"
else
  ok "无运行中的 VM"
fi

STOPPED_VMS=$(gcloud compute instances list --project="$PROJECT_ID" \
  --filter='status!=RUNNING' --format='value(name)' 2>/dev/null || true)
if [ -n "$STOPPED_VMS" ]; then
  warn "已停止但保留磁盘的 VM（磁盘仍计费，约 HK\$8/月每 30GB）："
  echo "$STOPPED_VMS" | sed 's/^/      /'
fi

SERVICES=$(gcloud run services list --project="$PROJECT_ID" \
  --format='value(metadata.name,status.url)' 2>/dev/null || true)
if [ -n "$SERVICES" ]; then
  ok "Cloud Run 服务（按请求计费，闲置时近零）："
  echo "$SERVICES" | sed 's/^/      /'
else
  ok "无 Cloud Run 服务"
fi

BUCKET_SIZE=$(gcloud storage du -s "gs://$EVIDENCE_BUCKET" 2>/dev/null | awk '{print $1}' || echo "")
if [ -n "$BUCKET_SIZE" ]; then
  ok "Private Vault 用量：$(( BUCKET_SIZE / 1024 / 1024 )) MB"
fi

step "预算告警"
BUDGETS=$(gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
  --format='value(displayName)' 2>/dev/null || true)
if [ -n "$BUDGETS" ]; then
  ok "已配置预算告警：$(echo "$BUDGETS" | tr '\n' ' ')"
else
  bad "未发现预算告警——赠金烧完不会有人通知你"
fi

step "精确账单"
printf "  控制台：https://console.cloud.google.com/billing/%s/reports?project=%s\n" \
  "$BILLING_ACCOUNT" "$PROJECT_ID"
printf "  ${DIM}命令行拿不到准确的实时用量；要长期跟踪需把账单导出到 BigQuery。${NC}\n"

if [ "$BILLING_NOW" -eq 1 ]; then
  printf "\n${YEL}有资源正在按时间计费，确认是否需要。${NC}\n"
fi
