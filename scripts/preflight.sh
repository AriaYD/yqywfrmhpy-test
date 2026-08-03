#!/usr/bin/env bash
# CampusPath 开工前自检。任何 FAIL 先解决再继续。
#   bash scripts/preflight.sh
set -uo pipefail

PROJECT_ID="keen-opus-498918-m8"
BILLING_ACCOUNT="BILLING-ACCOUNT-REDACTED"
CREDIT_EXPIRY="2026-09-27"
PASS=0; FAIL=0; WARN=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; WARN=$((WARN+1)); }

echo "═══ CampusPath Preflight ═══"; echo
echo "[1/6] 工具链"
command -v gcloud  >/dev/null 2>&1 && ok "gcloud $(gcloud --version 2>/dev/null | head -1 | awk '{print $4}')" || bad "gcloud 未安装"
command -v git     >/dev/null 2>&1 && ok "git"     || bad "git 未安装"
command -v python3 >/dev/null 2>&1 && ok "python3" || bad "python3 未安装"
echo

echo "[2/6] 计费绑定"
if command -v gcloud >/dev/null 2>&1; then
  ACTUAL=$(gcloud billing projects describe "$PROJECT_ID" --format="value(billingAccountName)" 2>/dev/null)
  if [ "$ACTUAL" = "billingAccounts/$BILLING_ACCOUNT" ]; then
    ok "项目挂在赠金账号上 ($BILLING_ACCOUNT)"
  elif [ -z "$ACTUAL" ]; then
    bad "读不到计费信息——是否已 gcloud auth login？"
  else
    bad "计费账号错误！当前=$ACTUAL 应为=billingAccounts/$BILLING_ACCOUNT"
    echo "      修复: gcloud billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT"
  fi
  DAYS=$(python3 -c "from datetime import date;print((date.fromisoformat('$CREDIT_EXPIRY')-date.today()).days)" 2>/dev/null)
  if [ -n "${DAYS:-}" ]; then
    if   [ "$DAYS" -lt 0 ]  ; then bad  "赠金已于 $CREDIT_EXPIRY 过期"
    elif [ "$DAYS" -lt 14 ] ; then warn "赠金仅剩 $DAYS 天（$CREDIT_EXPIRY 到期）"
    else                           ok   "赠金剩余 $DAYS 天（$CREDIT_EXPIRY 到期）"; fi
  fi
else
  warn "跳过计费检查（无 gcloud）"
fi
echo

echo "[3/6] 密钥卫生"
[ -f .env ] && ok ".env 存在" || warn ".env 不存在"
if [ -f .env ]; then
  PERM=$(stat -f "%OLp" .env 2>/dev/null || stat -c "%a" .env 2>/dev/null)
  [ "$PERM" = "600" ] && ok ".env 权限 600" || warn ".env 权限为 $PERM，建议 chmod 600 .env"
fi
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git check-ignore -q .env 2>/dev/null && ok ".env 已被 git 忽略" || bad ".env 未被忽略！"
  if git ls-files --error-unmatch .env >/dev/null 2>&1; then
    bad ".env 已被 git 跟踪！立即 git rm --cached .env"
  else ok ".env 不在版本控制中"; fi
  [ -f .git/hooks/pre-commit ] && ok "pre-commit hook 已安装" || warn "hook 缺失，跑 bash scripts/install-hooks.sh"
fi
echo

echo "[4/6] 禁用路径扫描（只查代码，文档提及不算）"
# 交给 scripts/check_ai_studio.py：现行的 google-genai SDK 两种后端都支持，
# 区分 `genai.Client(vertexai=True)` 与 `genai.Client(api_key=...)` 需要邻近判断，
# grep 做不到。一刀切按包名禁掉又会挡住我们自己该走的 Vertex 路径。
PYBIN=".venv/bin/python"; [ -x "$PYBIN" ] || PYBIN="python3"
HITS=$(git ls-files -z 2>/dev/null \
       | grep -zE '\.(py|ts|tsx|js|jsx|mjs|cjs|json|toml|ya?ml|sh|ipynb)$' \
       | xargs -0 "$PYBIN" scripts/check_ai_studio.py 2>&1 || true)
if [ -n "$HITS" ]; then
  bad "代码中发现 AI Studio 路径（绕过赠金，直扣信用卡）："
  echo "$HITS" | sed 's/^/      /'
else
  ok "代码中无 AI Studio 路径引用"
fi
echo

echo "[5/6] 模型后端（决定钱扣在哪里）"
# ADK/google-genai 靠环境变量选后端；源码扫描看不见这条路径。
# 这里只对**已存在的 .env** 做检查——还没配 Agent 时不该报错。
if [ -f .env ]; then
  # shellcheck disable=SC1091
  set -a; . ./.env 2>/dev/null || true; set +a
  if [ "${GOOGLE_GENAI_USE_VERTEXAI:-}" = "TRUE" ] || [ "${GOOGLE_GENAI_USE_VERTEXAI:-}" = "true" ]; then
    ok "GOOGLE_GENAI_USE_VERTEXAI 已开启（走 Vertex，吃赠金）"
  else
    warn "GOOGLE_GENAI_USE_VERTEXAI 未开启——构造 Agent 时会被守卫拒绝（见 .env.example）"
  fi
  if [ -n "${GOOGLE_API_KEY:-}${GEMINI_API_KEY:-}" ]; then   # ai-studio-denylist
    bad "环境里存在 API key——那是 AI Studio 的认证方式，赠金不覆盖"
  else
    ok "无 API key（Vertex 走 ADC）"
  fi
else
  warn "无 .env，跳过后端检查"
fi
echo

echo "[6/6] 基线文档"
[ -f CLAUDE.md ] && ok "CLAUDE.md" || bad "CLAUDE.md 缺失"
[ -f CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md ] && ok "Spec V4.1（唯一基线）" || bad "Spec V4.1 缺失"
[ -f CampusPath_Implementation_Plan_V2.md ] && ok "Implementation Plan V2" || bad "Plan V2 缺失"
echo

echo "═══════════════════════════"
printf "通过 %d  警告 %d  失败 %d\n" "$PASS" "$WARN" "$FAIL"
[ "$FAIL" -gt 0 ] && { echo "❌ 有失败项，先修复再开工"; exit 1; }
echo "✅ 可以开工"
