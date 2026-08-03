#!/usr/bin/env bash
# Moodle 沙箱 VM（Spec §11.4）。**单独一个脚本，因为它是唯一有实质月成本的资源。**
#
#   bash infra/moodle.sh status              # 只看状态
#   bash infra/moodle.sh create --apply      # 创建（约 HK$195/月，夜间停机可减半）
#   bash infra/moodle.sh start|stop --apply  # 手动起停
#   bash infra/moodle.sh schedule --apply    # 装夜间停机策略
#   bash infra/moodle.sh delete --apply      # 删除（会二次确认）
#
# 成本纪律（Plan R7）：这台机器只在需要 Demo 或调试 Moodle MCP 时开。
# 赠金 2026-09-27 过期，别让一台闲置 VM 吃掉本该给模型调用的额度。

set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.sh

ACTION="${1:-status}"; shift || true
parse_common_flags "$@"

INSTANCE_EXISTS=0
if gcloud compute instances describe "$MOODLE_INSTANCE" --zone="$MOODLE_ZONE" \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  INSTANCE_EXISTS=1
fi

# 启动脚本：装 docker + moodle-docker。凭据不写在这里——
# Web Services token 建好后由人工放进 Secret Manager（见 config.sh 的 REQUIRED_SECRETS）。
STARTUP_SCRIPT='#!/bin/bash
set -eux
apt-get update
apt-get install -y docker.io docker-compose git
systemctl enable --now docker
install -d -o 1000 -g 1000 /opt/moodle
cd /opt/moodle
if [ ! -d moodle-docker ]; then
  git clone --depth 1 https://github.com/moodlehq/moodle-docker.git
fi
# 实际的 Moodle 启动与 Seed 注入由 WP3 的脚本完成，不在开机脚本里做——
# 开机脚本失败没人看得见，而 WP3 的脚本会把失败摆在面前。
echo "moodle host ready" > /opt/moodle/READY
'

case "$ACTION" in
  status)
    banner
    if [ "$INSTANCE_EXISTS" -eq 1 ]; then
      gcloud compute instances describe "$MOODLE_INSTANCE" --zone="$MOODLE_ZONE" \
        --project="$PROJECT_ID" \
        --format='table(name,status,machineType.basename(),networkInterfaces[0].accessConfigs[0].natIP)'
      STATE=$(gcloud compute instances describe "$MOODLE_INSTANCE" --zone="$MOODLE_ZONE" \
        --project="$PROJECT_ID" --format='value(status)')
      if [ "$STATE" = "RUNNING" ]; then
        warn "实例正在运行，正在计费。不用时：bash infra/moodle.sh stop --apply"
      else
        ok "实例已停止，不产生计算费用（磁盘仍计费，约每月 HK\$8）"
      fi
    else
      ok "实例不存在，零成本"
    fi
    ;;

  create)
    banner
    if [ "$INSTANCE_EXISTS" -eq 1 ]; then
      ok "实例已存在，无需创建"
      exit 0
    fi
    warn "将创建 $MOODLE_MACHINE_TYPE 实例，约 HK\$195/月（持续运行）"
    warn "夜间停机后约减半。赠金 2026-09-27 过期，请按需开关。"
    run gcloud compute instances create "$MOODLE_INSTANCE" \
      --project="$PROJECT_ID" \
      --zone="$MOODLE_ZONE" \
      --machine-type="$MOODLE_MACHINE_TYPE" \
      --image-family=ubuntu-2404-lts-amd64 \
      --image-project=ubuntu-os-cloud \
      --boot-disk-size=30GB \
      --boot-disk-type=pd-balanced \
      --service-account="${SA_MOODLE_READER}@${PROJECT_ID}.iam.gserviceaccount.com" \
      --scopes=https://www.googleapis.com/auth/cloud-platform \
      --metadata=startup-script="$STARTUP_SCRIPT" \
      --tags=campuspath-moodle \
      --labels=project=campuspath,component=moodle-sandbox
    warn "Moodle 只监听内网。需要访问时用："
    warn "  gcloud compute ssh $MOODLE_INSTANCE --zone=$MOODLE_ZONE -- -L 8080:localhost:8080"
    warn "**不要**开 0.0.0.0 的防火墙规则——沙箱里有合成学生数据，没有理由暴露到公网"
    ;;

  schedule)
    banner
    # 资源策略：每天 23:00 停、09:00 开（香港时间）。
    # 用 GCE 的 instance schedule 而不是 cron：机器关着的时候 cron 也不会跑。
    POLICY="campuspath-moodle-nightly"
    run gcloud compute resource-policies create instance-schedule "$POLICY" \
      --project="$PROJECT_ID" --region="$APP_REGION" \
      --vm-start-schedule='0 9 * * *' \
      --vm-stop-schedule='0 23 * * *' \
      --timezone='Asia/Hong_Kong' \
      --description='CampusPath Moodle 夜间停机，省一半计算费用'
    run gcloud compute instances add-resource-policies "$MOODLE_INSTANCE" \
      --project="$PROJECT_ID" --zone="$MOODLE_ZONE" --resource-policies="$POLICY"
    ;;

  start)
    banner
    run gcloud compute instances start "$MOODLE_INSTANCE" \
      --zone="$MOODLE_ZONE" --project="$PROJECT_ID"
    ;;

  stop)
    banner
    run gcloud compute instances stop "$MOODLE_INSTANCE" \
      --zone="$MOODLE_ZONE" --project="$PROJECT_ID"
    ;;

  delete)
    banner
    if [ "$DRY_RUN" -eq 0 ]; then
      bad "即将**永久删除** $MOODLE_INSTANCE 及其磁盘（含 Seed 注入的 Moodle 数据）"
      printf "确认请输入实例名：" && read -r CONFIRM
      if [ "$CONFIRM" != "$MOODLE_INSTANCE" ]; then
        bad "输入不匹配，已取消"
        exit 1
      fi
    fi
    run gcloud compute instances delete "$MOODLE_INSTANCE" \
      --zone="$MOODLE_ZONE" --project="$PROJECT_ID" --quiet
    ;;

  *)
    bad "未知动作：$ACTION"
    echo "用法：bash infra/moodle.sh {status|create|schedule|start|stop|delete} [--apply]"
    exit 1
    ;;
esac
