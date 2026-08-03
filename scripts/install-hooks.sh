#!/usr/bin/env bash
# 安装 git hooks。克隆仓库后跑一次（hook 不随 git 传播）。
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .git ] || { echo "✗ 不在 git 仓库里"; exit 1; }
cp scripts/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit scripts/preflight.sh scripts/pre-commit scripts/install-hooks.sh
echo "✓ pre-commit hook 已安装"
