#!/usr/bin/env bash
# 每日源巡检的云端形态（C4）：Cloud Run Job + Cloud Scheduler（09:00 HKT）。
#
# ⚠️ 用户裁定（2026-08-02）：分支并入 main 前**不部署**——默认 dry-run，
#    真执行需显式 --apply。成本：每日一次 Job（约 2 分钟）≈ <HK$5/月；
#    赠金 2026-09-27 过期前记得 `bash infra/sources_job.sh delete --apply`。
set -euo pipefail

PROJECT="keen-opus-498918-m8"
REGION="asia-east2"
JOB="campuspath-sources-refresh"
SCHEDULER="campuspath-sources-daily"
API_URL="https://campuspath-api-786160486093.asia-east2.run.app"

MODE="${1:-plan}"; APPLY="${2:-}"
run() { echo "+ $*"; [[ "$APPLY" == "--apply" ]] && "$@" || true; }

case "$MODE" in
  create)
    # Job 复用 API 镜像（仓库根 Dockerfile），入口换成巡检脚本
    run gcloud run jobs deploy "$JOB" \
      --project "$PROJECT" --region "$REGION" \
      --source . \
      --command python3 --args jobs/sources_refresh.py \
      --set-env-vars "API_BASE=$API_URL" \
      --max-retries 1 --task-timeout 10m
    # 每日 09:00 HKT（01:00 UTC）
    run gcloud scheduler jobs create http "$SCHEDULER" \
      --project "$PROJECT" --location "$REGION" \
      --schedule "0 1 * * *" \
      --uri "https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/$JOB:run" \
      --http-method POST \
      --oauth-service-account-email "$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
    ;;
  run-once)
    run gcloud run jobs execute "$JOB" --project "$PROJECT" --region "$REGION" --wait
    ;;
  delete)
    run gcloud scheduler jobs delete "$SCHEDULER" --project "$PROJECT" --location "$REGION" --quiet
    run gcloud run jobs delete "$JOB" --project "$PROJECT" --region "$REGION" --quiet
    ;;
  *)
    echo "用法: bash infra/sources_job.sh {create|run-once|delete} [--apply]"; exit 1;;
esac
[[ "$APPLY" == "--apply" ]] || echo "（dry-run：以上命令未执行，加 --apply 才会真跑）"
