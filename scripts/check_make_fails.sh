#!/usr/bin/env bash
# H5 用在构建系统上：注入一个**已知会失败**的测试，断言 make 真的非零退出。
#
#   bash scripts/check_make_fails.sh
#
# 为什么需要这个：2026-07-29 的审查发现 `make check` 在有测试失败时依然返回 0
# （`pytest | tail -1` 把退出码吃掉了，for 循环又不累积状态）。
# 那意味着此前每一句"全绿"都没有验证力。修好之后必须有东西守住它，
# 否则下一次有人为了排版好看再加一个管道，同样的洞会悄悄回来。

set -uo pipefail
cd "$(dirname "$0")/.."

PROBE="services/capacity/tests/test_harness_probe.py"
cleanup() { rm -f "$PROBE"; }
trap cleanup EXIT

cat > "$PROBE" <<'PYEOF'
"""临时探针，由 scripts/check_make_fails.sh 生成并删除。"""


def test_probe_must_fail():
    assert False, "探针：验证链必须因此非零退出"
PYEOF

FAILURES=0
for target in test-services llm-free; do
  # llm-free 只跑 test_llm_free.py，探针不在其中，跳过它的断言
  [ "$target" = "llm-free" ] && continue
  if make "$target" >/dev/null 2>&1; then
    printf "  \033[31m✗\033[0m make %s 在有失败测试时仍返回 0\n" "$target"
    FAILURES=$((FAILURES+1))
  else
    printf "  \033[32m✓\033[0m make %s 正确地非零退出\n" "$target"
  fi
done

if make test >/dev/null 2>&1; then
  printf "  \033[31m✗\033[0m make test 在有失败测试时仍返回 0\n"
  FAILURES=$((FAILURES+1))
else
  printf "  \033[32m✓\033[0m make test 正确地非零退出\n"
fi

cleanup
trap - EXIT

# 反向：探针移除后必须恢复绿色，否则这个脚本会把真实故障也说成"符合预期"
if make test-services >/dev/null 2>&1; then
  printf "  \033[32m✓\033[0m 移除探针后 make test-services 恢复为 0\n"
else
  printf "  \033[31m✗\033[0m 移除探针后仍失败——存在真实故障，不是探针的问题\n"
  FAILURES=$((FAILURES+1))
fi

if [ "$FAILURES" -gt 0 ]; then
  printf "\033[31m验证链自检失败 %d 项\033[0m\n" "$FAILURES"
  exit 1
fi
printf "\033[32m验证链自检通过：失败会被传出，成功会恢复\033[0m\n"
