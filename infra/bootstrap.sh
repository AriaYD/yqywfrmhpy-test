#!/usr/bin/env bash
# 一条命令建好 CampusPath 需要的全部 GCP 资源（不含 Moodle VM）。
#
#   bash infra/bootstrap.sh            # dry-run，只打印将要执行什么
#   bash infra/bootstrap.sh --apply    # 真的执行
#
# 幂等：重复跑不会报错，也不会重复创建。
# 不含 Moodle VM —— 那是唯一有实质月成本的资源，单独放 infra/moodle.sh，
# 免得"跑一下 bootstrap"顺手开出一台每月 HK$195 的机器。

set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.sh
parse_common_flags "$@"
banner

# ── 0. 前置：项目必须挂在赠金账号上 ─────────────────────────────────
step "计费绑定"
CURRENT_BILLING=$(gcloud billing projects describe "$PROJECT_ID" \
  --format='value(billingAccountName)' 2>/dev/null | sed 's|billingAccounts/||' || true)
if [ "$CURRENT_BILLING" != "$BILLING_ACCOUNT" ]; then
  bad "项目挂在 ${CURRENT_BILLING:-<无>}，不是赠金账号 $BILLING_ACCOUNT"
  bad "继续下去开销会打到个人信用卡。先修计费绑定，再跑本脚本。"
  exit 1
fi
ok "项目挂在赠金账号 $BILLING_ACCOUNT"

# ── 1. API ──────────────────────────────────────────────────────────
# 只启用真正要用的。generativelanguage 不在列表里，也不该在——
# 那是 AI Studio 路径，不吃赠金（见 CLAUDE.md）。
step "启用 API"
REQUIRED_APIS=(
  aiplatform.googleapis.com          # Vertex AI：**唯一**允许的模型调用路径
  run.googleapis.com
  firestore.googleapis.com
  storage.googleapis.com
  secretmanager.googleapis.com
  artifactregistry.googleapis.com
  cloudbuild.googleapis.com
  compute.googleapis.com             # Moodle 沙箱
  iam.googleapis.com
  logging.googleapis.com
  monitoring.googleapis.com
  cloudtrace.googleapis.com          # Agent trace 是 D2 的治理证据
  billingbudgets.googleapis.com
)
ENABLED=$(gcloud services list --enabled --format='value(config.name)' 2>/dev/null || true)
MISSING=()
for api in "${REQUIRED_APIS[@]}"; do
  if echo "$ENABLED" | grep -qx "$api"; then
    ok "$api"
  else
    MISSING+=("$api")
    warn "$api 未启用"
  fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
  run gcloud services enable "${MISSING[@]}" --project="$PROJECT_ID"
fi

# ── 2. Firestore ────────────────────────────────────────────────────
# Native 模式。Event Store 用 append-only collection，省掉 Cloud SQL 运维（Plan §2）。
step "Firestore"
if gcloud firestore databases describe --database="$FIRESTORE_DATABASE" \
     --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
  ok "数据库已存在"
else
  run gcloud firestore databases create \
    --database="$FIRESTORE_DATABASE" \
    --location="$APP_REGION" \
    --type=firestore-native \
    --project="$PROJECT_ID"
fi

# ── 3. Cloud Storage：Private Vault ─────────────────────────────────
# Evidence 附件按 student_id 前缀隔离（Plan §2）。
# uniform bucket-level access：关掉 per-object ACL，避免"某个对象被单独设成公开"。
step "Private Vault（Cloud Storage）"
if gcloud storage buckets describe "gs://$EVIDENCE_BUCKET" \
     --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "桶已存在：gs://$EVIDENCE_BUCKET"
else
  run gcloud storage buckets create "gs://$EVIDENCE_BUCKET" \
    --project="$PROJECT_ID" \
    --location="$APP_REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi

# ── 4. Artifact Registry ────────────────────────────────────────────
step "Artifact Registry"
if gcloud artifacts repositories describe "$ARTIFACT_REPO" \
     --location="$APP_REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  ok "仓库已存在：$ARTIFACT_REPO"
else
  run gcloud artifacts repositories create "$ARTIFACT_REPO" \
    --repository-format=docker \
    --location="$APP_REGION" \
    --project="$PROJECT_ID" \
    --description="CampusPath 容器镜像"
fi

# ── 5. 服务账户：两个 Runtime 分开 ──────────────────────────────────
# Spec §8.1：Student Path Runtime 与 Opportunity Operations Runtime 是**安全边界**。
# A4 处理不可信外部内容，它的身份不该能读任何学生数据。
step "服务账户"
create_sa() {
  local name="$1" display="$2"
  if gcloud iam service-accounts describe \
       "${name}@${PROJECT_ID}.iam.gserviceaccount.com" \
       --project="$PROJECT_ID" >/dev/null 2>&1; then
    ok "$name 已存在"
  else
    run gcloud iam service-accounts create "$name" \
      --display-name="$display" --project="$PROJECT_ID"
  fi
}
create_sa "$SA_STUDENT_RUNTIME"     "CampusPath Student Path Runtime (A0/A1/A2/A3/A5)"
create_sa "$SA_OPPORTUNITY_RUNTIME" "CampusPath Opportunity Ops Runtime (A4)"
create_sa "$SA_MOODLE_READER"       "CampusPath Moodle read-only reader"

step "IAM 授权（最小权限）"
grant() {
  local sa="$1" role="$2"
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="$role" --condition=None --quiet
}
# Student Runtime：能调模型、读写 Firestore、读写自己的 Vault、写 trace
grant "$SA_STUDENT_RUNTIME" "roles/aiplatform.user"
grant "$SA_STUDENT_RUNTIME" "roles/datastore.user"
grant "$SA_STUDENT_RUNTIME" "roles/cloudtrace.agent"
grant "$SA_STUDENT_RUNTIME" "roles/secretmanager.secretAccessor"

# Opportunity Runtime（A4）：能调模型、写 trace。
# **没有 datastore.user** —— A4 没有学生数据访问权（Spec §8.9.1 第 2 条）。
# 这不是配置疏漏，是契约。改这里之前先去看 D2 的安全契约测试。
grant "$SA_OPPORTUNITY_RUNTIME" "roles/aiplatform.user"
grant "$SA_OPPORTUNITY_RUNTIME" "roles/cloudtrace.agent"

# Moodle reader：只读 Secret（取 WS token），不碰 Firestore
grant "$SA_MOODLE_READER" "roles/secretmanager.secretAccessor"

# Vault 的对象权限只给 Student Runtime，且只在这个桶上
run gcloud storage buckets add-iam-policy-binding "gs://$EVIDENCE_BUCKET" \
  --member="serviceAccount:${SA_STUDENT_RUNTIME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# ── 6. Secret Manager：只建容器，不放值 ─────────────────────────────
step "Secret Manager（只创建空密钥，值由人工注入）"
for secret in "${REQUIRED_SECRETS[@]}"; do
  if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    ok "$secret 已存在"
  else
    run gcloud secrets create "$secret" \
      --replication-policy=user-managed --locations="$APP_REGION" \
      --project="$PROJECT_ID"
    warn "$secret 尚无版本。注入方式：printf '%s' \"\$VALUE\" | gcloud secrets versions add $secret --data-file=-"
  fi
done

step "完成"
if [ "$DRY_RUN" -eq 1 ]; then
  printf "${YEL}以上均未执行。确认无误后：bash infra/bootstrap.sh --apply${NC}\n"
else
  ok "资源就绪。下一步跑 bash infra/verify.sh 实测每一项是否真的存在"
fi
