#!/usr/bin/env bash
# CampusPath 基础设施配置 —— 资源命名与区域的**唯一事实来源**。
#
# 所有 infra/ 脚本 source 这个文件。不要在别处硬编码项目号、区域或桶名：
# 散在五个脚本里的常量迟早会出现三种写法。
#
# 这里**不含任何密钥**。凭据一律走 Secret Manager 或环境变量（Plan §9）。

set -euo pipefail

# ── 项目与计费 ──────────────────────────────────────────────────────
# 赠金 HK$1,568.39，2026-09-27 过期，挂在这个计费账号上。
# preflight.sh 每次开工复检项目是否仍挂在它上面——曾经挂错过，赠金 100% 未生效。
PROJECT_ID="${CAMPUSPATH_PROJECT_ID:-keen-opus-498918-m8}"
BILLING_ACCOUNT="BILLING-ACCOUNT-REDACTED"

# ── 区域 ────────────────────────────────────────────────────────────
# 应用与数据放香港：离 HKUST 最近，直接影响 T9（常见交互 P50 < 3s）。
APP_REGION="${CAMPUSPATH_APP_REGION:-asia-east2}"

# 模型调用的区域**单独配置**：Gemini 的可用区域与 Cloud Run 不一定重合，
# 而且它会变。所以这里给默认值，由 verify.sh 在运行时**实测**该区域是否真的可用，
# 而不是靠这份文件里的一句断言。
VERTEX_LOCATION="${CAMPUSPATH_VERTEX_LOCATION:-us-central1}"

# GCE Moodle 沙箱。asia-east2-a 与 APP_REGION 同区，省跨区流量。
MOODLE_ZONE="${CAMPUSPATH_MOODLE_ZONE:-asia-east2-a}"
MOODLE_INSTANCE="campuspath-moodle"
MOODLE_MACHINE_TYPE="e2-medium"

# ── 资源命名 ────────────────────────────────────────────────────────
# 桶名全球唯一，因此带项目号后缀。
EVIDENCE_BUCKET="campuspath-evidence-${PROJECT_ID}"
ARTIFACT_REPO="campuspath"
FIRESTORE_DATABASE="(default)"

# 服务账户：一个 Runtime 一个，最小权限。
# Spec §8.1 的两个 Runtime 是**安全边界**，共用一个服务账户等于把边界抹掉。
SA_STUDENT_RUNTIME="campuspath-student-runtime"
SA_OPPORTUNITY_RUNTIME="campuspath-opportunity-runtime"
SA_MOODLE_READER="campuspath-moodle-reader"

# ── Secret Manager 里应当存在的密钥名 ───────────────────────────────
# 只列**名字**。值由人工 `gcloud secrets versions add` 注入，绝不进仓库。
REQUIRED_SECRETS=(
  "campuspath-google-oauth-client"      # Calendar 模式 A 的 OAuth client
  "campuspath-moodle-ws-token"          # Moodle Web Services token
  "campuspath-counseling-inbox"         # Wellbeing outreach 的测试收件箱
)

# ── 成本护栏 ────────────────────────────────────────────────────────
# Plan R7：每日成本检查。超过这个数就该去看是什么在烧钱。
DAILY_COST_ALERT_HKD="${CAMPUSPATH_DAILY_COST_ALERT_HKD:-40}"

# ── 输出辅助 ────────────────────────────────────────────────────────
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; NC=$'\033[0m'
ok()   { printf "  ${GRN}✓${NC} %s\n" "$1"; }
warn() { printf "  ${YEL}!${NC} %s\n" "$1"; }
bad()  { printf "  ${RED}✗${NC} %s\n" "$1"; }
step() { printf "\n${DIM}── %s ──${NC}\n" "$1"; }

# DRY_RUN 默认为真：infra 脚本**默认不动任何东西**。
# 花钱和建资源都必须显式 --apply，手滑跑一次脚本不该产生账单。
DRY_RUN=1
parse_common_flags() {
  for arg in "$@"; do
    case "$arg" in
      --apply) DRY_RUN=0 ;;
      --dry-run) DRY_RUN=1 ;;
    esac
  done
}

# run：dry-run 时只打印，--apply 时才执行。
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "  ${DIM}[dry-run]${NC} %s\n" "$*"
  else
    printf "  ${DIM}\$${NC} %s\n" "$*"
    "$@"
  fi
}

# run_idempotent：命令可能因"已存在"而失败，那不算失败。
run_idempotent() {
  local exists_pattern="$1"; shift
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "  ${DIM}[dry-run]${NC} %s\n" "$*"
    return 0
  fi
  printf "  ${DIM}\$${NC} %s\n" "$*"
  local output
  if output=$("$@" 2>&1); then
    return 0
  fi
  if echo "$output" | grep -qi "$exists_pattern"; then
    warn "已存在，跳过"
    return 0
  fi
  echo "$output" >&2
  return 1
}

banner() {
  printf "\n${DIM}CampusPath infra · project=%s · app=%s · vertex=%s${NC}\n" \
    "$PROJECT_ID" "$APP_REGION" "$VERTEX_LOCATION"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "${YEL}DRY RUN —— 不会改动任何资源。确认无误后加 --apply。${NC}\n"
  else
    printf "${RED}APPLY —— 将真实创建/修改资源。${NC}\n"
  fi
}
