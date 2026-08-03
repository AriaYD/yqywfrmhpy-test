#!/usr/bin/env bash
# Agent Engine 运行时管理（R7-D）。
#
#   bash infra/agent_engine.sh status            # 列出运行时与状态
#   bash infra/agent_engine.sh query <name片段> "<消息>"   # 真机试问
#   bash infra/agent_engine.sh delete <name片段>  # 下线（省赠金）
#
# ⚠️ 钱：Agent Engine 按运行时 vCPU/内存小时计费，挂着不用也在烧赠金。
# 演示排练完就 delete，要用再重新 `adk deploy agent_engine`（约 5–10 分钟）。

set -euo pipefail
cd "$(dirname "$0")/.."
source infra/config.sh

PY=".venv/bin/python"
ACTION="${1:-status}"

case "$ACTION" in
  status)
    "$PY" - "$PROJECT_ID" "$VERTEX_LOCATION" <<'EOF'
import sys
import vertexai
from vertexai import agent_engines

vertexai.init(project=sys.argv[1], location=sys.argv[2])
rows = list(agent_engines.list())
if not rows:
    print("（没有已部署的 Agent Engine 运行时）")
for engine in rows:
    ops = engine.operation_schemas()
    print(f"- {engine.display_name}")
    print(f"  resource: {engine.resource_name}")
    print(f"  updated:  {engine.update_time}")
    print(f"  operations: {[s.get('name') for s in ops]}")
EOF
    ;;
  query)
    "$PY" - "$PROJECT_ID" "$VERTEX_LOCATION" "$2" "$3" <<'EOF'
import json
import sys
import vertexai
from vertexai import agent_engines

vertexai.init(project=sys.argv[1], location=sys.argv[2])
needle, message = sys.argv[3].lower(), sys.argv[4]
engine = next(e for e in agent_engines.list()
              if needle in e.display_name.lower()
              or needle in e.resource_name.lower())
print(f"→ {engine.display_name} ({engine.resource_name})")
for event in engine.stream_query(user_id="infra-probe", message=message):
    print(json.dumps(event, ensure_ascii=False, default=str)[:2000])
EOF
    ;;
  delete)
    "$PY" - "$PROJECT_ID" "$VERTEX_LOCATION" "$2" <<'EOF'
import sys
import vertexai
from vertexai import agent_engines

vertexai.init(project=sys.argv[1], location=sys.argv[2])
needle = sys.argv[3].lower()
for engine in agent_engines.list():
    if needle in engine.display_name.lower() or needle in engine.resource_name.lower():
        print(f"删除 {engine.display_name} ({engine.resource_name}) …")
        engine.delete(force=True)
        print("已删除")
        break
else:
    print(f"没找到匹配 {needle!r} 的运行时")
EOF
    ;;
  start)
    # F1（2026-08-02）：demo 一键启动两个运行时（约 5–10 分钟/个，按小时计费）。
    STAGING="gs://${PROJECT_ID}-agent-staging"
    gsutil ls "$STAGING" >/dev/null 2>&1 || gsutil mb -l "$VERTEX_LOCATION" -p "$PROJECT_ID" "$STAGING"
    for spec in "orchestrator_agent:campuspath-orchestrator"                 "opportunity_scout_agent:campuspath-opportunity-scout"; do
      dir="agents/cloud/${spec%%:*}"; name="${spec##*:}"
      echo "== deploying $name from $dir =="
      ".venv/bin/adk" deploy agent_engine         --project "$PROJECT_ID" --region "$VERTEX_LOCATION"         --staging_bucket "$STAGING" --display_name "$name" "$dir"
    done
    ;;
  stop)
    "$PY" - "$PROJECT_ID" "$VERTEX_LOCATION" <<'PYEOF'
import sys
import vertexai
from vertexai import agent_engines

vertexai.init(project=sys.argv[1], location=sys.argv[2])
found = False
for engine in list(agent_engines.list()):
    found = True
    print(f"删除 {engine.display_name} ({engine.resource_name}) …")
    engine.delete(force=True)
print("已全部删除" if found else "（本就没有运行中的运行时）")
PYEOF
    ;;
  *)
    echo "用法: $0 status | start | stop | query <name片段> <消息> | delete <name片段>" >&2
    exit 1
    ;;
esac
