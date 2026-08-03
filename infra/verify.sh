#!/usr/bin/env bash
# 实测每一项资源是否真的存在、权限是否真的如预期。**只读，不改任何东西。**
#
#   bash infra/verify.sh
#
# 为什么单独有这个脚本：bootstrap.sh 跑完不报错，只说明命令没返回非零；
# 它不说明资源真的建成了、权限真的生效了。Plan §10 H3 要求"报告实测值，
# 不报告预期值"——这个脚本就是去取实测值的。
#
# 最有价值的是**否定式检查**：A4 的服务账户**不该**有学生数据权限。
# 肯定式检查只能发现"忘了建"，否定式检查才能发现"多给了"。

set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.sh
DRY_RUN=1   # 本脚本永远只读

PASS=0; FAIL=0; WARN_COUNT=0
pass() { ok "$1"; PASS=$((PASS+1)); }
fail() { bad "$1"; FAIL=$((FAIL+1)); }
soft() { warn "$1"; WARN_COUNT=$((WARN_COUNT+1)); }

printf "\n${DIM}CampusPath infra verify · project=%s${NC}\n" "$PROJECT_ID"

# ── 1. 计费 ─────────────────────────────────────────────────────────
step "计费"
CURRENT_BILLING=$(gcloud billing projects describe "$PROJECT_ID" \
  --format='value(billingAccountName)' 2>/dev/null | sed 's|billingAccounts/||' || true)
if [ "$CURRENT_BILLING" = "$BILLING_ACCOUNT" ]; then
  pass "挂在赠金账号 $BILLING_ACCOUNT"
else
  fail "挂在 ${CURRENT_BILLING:-<无>}，赠金不会生效，开销会打到个人卡"
fi

# ── 2. 资源存在性 ───────────────────────────────────────────────────
step "资源"
if gcloud firestore databases describe --database="$FIRESTORE_DATABASE" \
     --project="$PROJECT_ID" --format='value(locationId)' >/dev/null 2>&1; then
  LOC=$(gcloud firestore databases describe --database="$FIRESTORE_DATABASE" \
        --project="$PROJECT_ID" --format='value(locationId)')
  pass "Firestore 存在（location=${LOC}）"
else
  fail "Firestore 数据库不存在"
fi

if gcloud storage buckets describe "gs://$EVIDENCE_BUCKET" \
     --project="$PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
  PAP=$(gcloud storage buckets describe "gs://$EVIDENCE_BUCKET" \
        --format='value(public_access_prevention)' 2>/dev/null || echo "unknown")
  UBLA=$(gcloud storage buckets describe "gs://$EVIDENCE_BUCKET" \
         --format='value(uniform_bucket_level_access)' 2>/dev/null || echo "unknown")
  pass "Private Vault 桶存在"
  [ "$PAP" = "enforced" ] && pass "  公开访问已阻断" || fail "  public_access_prevention=${PAP}，学生附件可能被公开访问"
  [ "$UBLA" = "True" ] || soft "  uniform_bucket_level_access=${UBLA}（建议开启，避免单个对象被设成公开）"
else
  fail "Private Vault 桶不存在"
fi

if gcloud artifacts repositories describe "$ARTIFACT_REPO" \
     --location="$APP_REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  pass "Artifact Registry 存在"
else
  fail "Artifact Registry 不存在"
fi

# ── 3. 服务账户与权限 ───────────────────────────────────────────────
step "服务账户"
POLICY=$(gcloud projects get-iam-policy "$PROJECT_ID" --format=json 2>/dev/null || echo '{}')

roles_of() {
  local sa="$1"
  echo "$POLICY" | python3 -c "
import json,sys
policy = json.load(sys.stdin)
member = 'serviceAccount:$sa@$PROJECT_ID.iam.gserviceaccount.com'
print('\n'.join(sorted(
    b['role'] for b in policy.get('bindings', []) if member in b.get('members', [])
)))
"
}

for sa in "$SA_STUDENT_RUNTIME" "$SA_OPPORTUNITY_RUNTIME" "$SA_MOODLE_READER"; do
  if gcloud iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
       --project="$PROJECT_ID" >/dev/null 2>&1; then
    pass "$sa 存在"
  else
    fail "$sa 不存在"
  fi
done

STUDENT_ROLES=$(roles_of "$SA_STUDENT_RUNTIME")
for role in roles/aiplatform.user roles/datastore.user; do
  echo "$STUDENT_ROLES" | grep -qx "$role" \
    && pass "Student Runtime 有 $role" \
    || fail "Student Runtime 缺 $role"
done

# ★ 否定式检查：A4 不得有学生数据权限（Spec §8.9.1 第 2 条）
step "安全边界（否定式检查）"
OPS_ROLES=$(roles_of "$SA_OPPORTUNITY_RUNTIME")
FORBIDDEN_FOR_A4=(
  roles/datastore.user
  roles/datastore.owner
  roles/storage.objectAdmin
  roles/storage.objectViewer
  roles/editor
  roles/owner
)
A4_CLEAN=1
for role in "${FORBIDDEN_FOR_A4[@]}"; do
  if echo "$OPS_ROLES" | grep -qx "$role"; then
    fail "Opportunity Runtime（A4）持有 $role —— 它不该能碰学生数据（Spec §8.9.1）"
    A4_CLEAN=0
  fi
done
[ "$A4_CLEAN" -eq 1 ] && pass "A4 无任何学生数据权限"

# Vault 桶的对象权限只该给 Student Runtime
VAULT_MEMBERS=$(gcloud storage buckets get-iam-policy "gs://$EVIDENCE_BUCKET" \
  --format=json 2>/dev/null | python3 -c "
import json,sys
try:
    policy = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for b in policy.get('bindings', []):
    if b['role'].startswith('roles/storage.object'):
        for m in b.get('members', []):
            print(m)
" || true)
if echo "$VAULT_MEMBERS" | grep -q "$SA_OPPORTUNITY_RUNTIME"; then
  fail "A4 的服务账户出现在 Private Vault 的对象权限里"
else
  pass "Private Vault 未授予 A4"
fi

# ── 4. Secret Manager ───────────────────────────────────────────────
step "Secret Manager"
for secret in "${REQUIRED_SECRETS[@]}"; do
  if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    VERSIONS=$(gcloud secrets versions list "$secret" --project="$PROJECT_ID" \
      --filter='state=ENABLED' --format='value(name)' 2>/dev/null | wc -l | tr -d ' ')
    if [ "$VERSIONS" -gt 0 ]; then
      pass "${secret}（$VERSIONS 个可用版本）"
    else
      soft "$secret 存在但**没有值**；用到它的功能会在运行时失败"
    fi
  else
    fail "$secret 不存在"
  fi
done

# ── 5. Vertex AI 可用性：实测，不靠断言 ─────────────────────────────
# config.sh 里的 VERTEX_LOCATION 只是默认值。区域支持哪些模型会变，
# 所以这里去问一次 API，而不是在文档里写一句"我们用 us-central1"。
step "Vertex AI（实测区域可用性）"
if gcloud ai models list --region="$VERTEX_LOCATION" --project="$PROJECT_ID" \
     --limit=1 >/dev/null 2>&1; then
  pass "Vertex AI 在 $VERTEX_LOCATION 可访问"
else
  soft "无法在 $VERTEX_LOCATION 列出模型——可能是区域不支持或权限不足，接入前需确认"
fi

# ── 6. B12：账号层面确认没有走 AI Studio ────────────────────────────
# 代码扫描在 preflight.sh 与各服务的 test_llm_free.py；这里查的是**账号层面**：
# 只要这个 API 没启用，即使代码里漏了一行，调用也会直接失败。
step "AI Studio 路径（B12）"
ENABLED_APIS=$(gcloud services list --enabled --format='value(config.name)' 2>/dev/null || true)
if echo "$ENABLED_APIS" | grep -q generativelanguage; then   # ai-studio-denylist
  fail "该 API 已启用——那是不吃赠金的 AI Studio 路径，应停用"  # ai-studio-denylist
else
  pass "generativelanguage API 未启用"
fi

# ── 结果 ────────────────────────────────────────────────────────────
printf "\n${DIM}═══════════════════════════${NC}\n"
printf "通过 %d  警告 %d  失败 %d\n" "$PASS" "$WARN_COUNT" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf "${RED}❌ 基础设施未就绪${NC}\n"
  exit 1
fi
printf "${GRN}✅ 基础设施就绪${NC}\n"
