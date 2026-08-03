#!/usr/bin/env python3
"""导出 JSON Schema 与 OpenAPI 文档。

产出（全部进版本库，契约变更因此在 diff 里可见）：

* ``contracts/schema/<Model>.json`` —— 每个契约模型一份 JSON Schema
* ``contracts/schema/_index.json``  —— 模型清单与契约版本
* ``contracts/openapi/campuspath.json`` —— Agent ↔ 服务的 OpenAPI 3.1 合同

输出是确定性的：键序固定、缩进固定。同样的代码跑两次必须字节一致
（D6.7 要求固定 Seed 可复现），``--check`` 用于在 CI 里断言这一点。

用法::

    python3 scripts/export_schemas.py           # 写文件
    python3 scripts/export_schemas.py --check   # 只校验，有差异则非零退出
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from campuspath_contracts import ROOT_MODELS  # noqa: E402
from campuspath_contracts.common import CONTRACTS_VERSION  # noqa: E402
from campuspath_contracts.openapi import SCHEMA_REF_TEMPLATE, build_openapi  # noqa: E402

SCHEMA_DIR = ROOT / "schema"
OPENAPI_PATH = ROOT / "openapi" / "campuspath.json"


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_outputs() -> dict[pathlib.Path, str]:
    outputs: dict[pathlib.Path, str] = {}
    for name, model in ROOT_MODELS.items():
        schema = model.model_json_schema(ref_template=SCHEMA_REF_TEMPLATE)
        schema["$id"] = f"https://campuspath.invalid/schema/{name}.json"
        outputs[SCHEMA_DIR / f"{name}.json"] = _dump(schema)

    outputs[SCHEMA_DIR / "_index.json"] = _dump(
        {"contracts_version": CONTRACTS_VERSION, "models": sorted(ROOT_MODELS)}
    )
    outputs[OPENAPI_PATH] = _dump(build_openapi(ROOT_MODELS))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验磁盘内容是否与代码一致")
    args = parser.parse_args()

    outputs = build_outputs()
    stale: list[str] = []
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    if args.check:
        # 磁盘上有、但代码里已经不产出的文件同样算不一致——否则删掉一个模型不会被发现
        expected = set(outputs)
        for path in list(SCHEMA_DIR.glob("*.json")):
            if path not in expected:
                stale.append(f"{path.relative_to(ROOT)}（已不再由代码产出）")
        if stale:
            print("契约产物与代码不一致，请重新运行 export_schemas.py：", file=sys.stderr)
            for item in sorted(stale):
                print(f"  - {item}", file=sys.stderr)
            return 1
        print(f"契约产物一致：{len(ROOT_MODELS)} 个模型 + OpenAPI")
        return 0

    print(f"已导出 {len(ROOT_MODELS)} 个模型的 JSON Schema → {SCHEMA_DIR.relative_to(ROOT.parent)}")
    print(f"已导出 OpenAPI → {OPENAPI_PATH.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
