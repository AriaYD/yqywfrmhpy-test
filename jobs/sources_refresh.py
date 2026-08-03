#!/usr/bin/env python3
"""每日源巡检（C4，2026-08-02）。

遍历源注册表，对真实源做抓取 + 内容哈希变更检测，把变更/健康态打到
运行中的 API（复用 POST /v1/ops/sources/{id}/refresh 的全部业务逻辑：
政策卡、官方直发、去重——不在这里重写一遍）。

用法：
    make sources-refresh                    # 本地（API 需在 :8000）
    API_BASE=https://... python3 jobs/sources_refresh.py   # 云端 Job 形态

Cloud Run Job + Cloud Scheduler（每日 09:00 HKT）的部署脚本见
infra/sources_job.sh——**分支并入 main 前不实际部署**（用户裁定 2026-08-02）。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
ROLE_HEADER = {"X-CampusPath-Role": "connector_admin"}
#: p2 源两天跑一轮也够；Job 层先全跑（92 源 × 1s 礼貌间隔 ≈ 2 分钟）
PRIORITIES = ("p0", "p1", "p2")


def call(method: str, path: str):
    req = urllib.request.Request(f"{API_BASE}{path}", method=method, headers=ROLE_HEADER)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    sources = call("GET", "/v1/ops/sources")
    counts = {"changed": 0, "unchanged": 0, "error": 0, "skipped": 0}
    for source in sources:
        if not source["is_real_fetch"] or source["priority"] not in PRIORITIES:
            counts["skipped"] += 1
            continue
        if source["render"] == "js":
            counts["skipped"] += 1   # JS 渲染页需可选引擎，本轮如实跳过
            continue
        try:
            updated = call("POST", f"/v1/ops/sources/{source['source_id']}/refresh")
        except Exception as exc:
            print(f"  !! {source['source_id']}: {exc}")
            counts["error"] += 1
            continue
        if updated["last_fetch_status"] != "ok":
            counts["error"] += 1
            print(f"  ×  {source['source_id']}: {updated['last_fetch_status']}")
        elif updated["last_changed_at"] and updated["last_checked_at"] == updated["last_changed_at"]:
            counts["changed"] += 1
            print(f"  Δ  {source['source_id']}")
        else:
            counts["unchanged"] += 1
    attempted = counts["changed"] + counts["unchanged"] + counts["error"]
    print(f"sources-refresh: changed={counts['changed']} unchanged={counts['unchanged']} "
          f"error={counts['error']} skipped={counts['skipped']}")
    # 92 源全量巡检：个别源抖动（外站限流/临时不可达）是常态，健康板会标红；
    # 只有错误率超 10% 才算 Job 失败（0 容忍会让每日 Job 长期假红）
    return 0 if attempted == 0 or counts["error"] / attempted <= 0.10 else 1


if __name__ == "__main__":
    sys.exit(main())
