"""官方信息源注册表（2026-08-02 用户裁定 C）。

`source_registry.json` 是源清单的唯一事实来源：console 源列表、变更检测、
直发广场白名单、Cloud Job 的抓取排程都从这里读。数据条目转录自
`reference/HKUST_student_development_resource_map.md`（2026-08-01 核查）与
国际学生 Context Pack 的官方政策源清单。

真实源 / mock 源同表登记、`is_real_fetch` 显式区分——界面与 Spec 都要
如实标注（用户裁定 D），不许把合成源冒充真实抓取。
"""

from __future__ import annotations

import json
from pathlib import Path

from campuspath_contracts.publishing import RegisteredSource

_REGISTRY_PATH = Path(__file__).resolve().parent / "source_registry.json"


def load_registry(path: Path = _REGISTRY_PATH) -> tuple[RegisteredSource, ...]:
    """加载并逐条通过契约校验；重复 id 直接抛错（宁可启动失败，不可静默覆盖）。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    sources: list[RegisteredSource] = []
    seen: set[str] = set()
    for record in raw["sources"]:
        source = RegisteredSource.model_validate(record)
        if source.source_id in seen:
            raise ValueError(f"source_registry 重复 source_id: {source.source_id}")
        seen.add(source.source_id)
        sources.append(source)
    return tuple(sources)


def registry_version(path: Path = _REGISTRY_PATH) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["registry_version"]
