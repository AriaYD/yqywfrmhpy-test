"""B11 LLM-free Path Integrity / B12 AI Studio 路径 —— 契约层的那一段。

完整的依赖树扫描属于 CI（WP5 收尾时接入确定性服务平面），
这里守住的是**地基**：契约包本身被确定性服务 import，
一旦它拖进模型 SDK，Rules / Capacity / Wellbeing 三个零 LLM 模块同时失守。

按 H5，扫描器用已知会失败的输入验证过（见 ``test_scanner_flags_known_bad_imports``）。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

import pytest

import campuspath_contracts
from campuspath_contracts.guards import (
    MODEL_SDK_MODULES,
    ai_studio_violations,
    imported_model_sdks,
)

#: 契约包中承担确定性判定的模块。这些是 Rules / Capacity / Composer 直接依赖的。
DETERMINISTIC_MODULES = (
    "campuspath_contracts.common",
    "campuspath_contracts.validation",
    "campuspath_contracts.calendar",
    "campuspath_contracts.wellbeing",
    "campuspath_contracts.aggregation",
    "campuspath_contracts.guards",
)


def _all_contract_modules() -> list[str]:
    names = [campuspath_contracts.__name__]
    for info in pkgutil.iter_modules(campuspath_contracts.__path__):
        names.append(f"campuspath_contracts.{info.name}")
    return names


def test_scanner_flags_known_bad_imports():
    """H5：先证明扫描器会失败。"""
    bad = ["json", "google.generativeai", "vertexai.generative_models"]  # ai-studio-denylist
    assert imported_model_sdks(bad) == {"google.generativeai", "vertexai.generative_models"}  # ai-studio-denylist


def test_scanner_does_not_flag_lookalikes():
    """``openaiutils`` 不是 ``openai``；前缀匹配必须按模块边界。"""
    assert imported_model_sdks(["openaiutils", "vertexaitools", "anthropicish"]) == set()


def test_contract_package_imports_no_model_sdk():
    for name in _all_contract_modules():
        importlib.import_module(name)
    hits = imported_model_sdks(list(sys.modules))
    assert hits == set(), f"契约层的依赖树里出现了模型 SDK：{sorted(hits)}"


@pytest.mark.parametrize("module_name", DETERMINISTIC_MODULES)
def test_deterministic_modules_have_no_sdk_in_their_globals(module_name):
    module = importlib.import_module(module_name)
    referenced = {
        getattr(value, "__name__", "")
        for value in vars(module).values()
        if getattr(value, "__name__", "")
    }
    assert imported_model_sdks(referenced) == set()


def test_ai_studio_path_is_in_the_banned_list():
    """B12：AI Studio 路径不吃赠金，会直扣个人信用卡。"""
    assert "google.generativeai" in MODEL_SDK_MODULES  # ai-studio-denylist


def test_no_source_file_references_the_ai_studio_path():
    """B12：与 ``scripts/preflight.sh`` **同一个扫描器**，不是同口径的另一份实现。

    此前这里是按**文件名**豁免（``path.name != "guards.py"``），
    于是往 guards.py 里塞一个不带标注的 AI Studio 端点常量，全绿——
    而 preflight 会拦。Plan §10.2 第 7 个坑的修法是"按行判定 + 同行标注"，
    这条测试当时没跟着改，停留在已被判定为错误的形态上。
    """
    import pathlib as _pathlib

    root = _pathlib.Path(campuspath_contracts.__file__).parent
    offenders = [
        f"{path.name}:{hit}"
        for path in sorted(root.rglob("*.py"))
        for hit in ai_studio_violations(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], offenders


def test_every_enforcement_point_uses_the_same_scanner():
    """三处 B12 检查必须共用一个判定，不能各写一份。

    此前它们是三份独立实现：契约测试按文件名整份跳过、preflight 与 pre-commit
    按行标注。同一个"提到它以禁止它"的误报被修了两次，第三处没跟上——
    往 guards.py 塞一个不带标注的端点常量，契约测试全绿而 preflight 会拦。
    """
    import pathlib as _p

    repo = _p.Path(campuspath_contracts.__file__).resolve().parents[2]
    for script in ("scripts/preflight.sh", "scripts/pre-commit"):
        source = (repo / script).read_text(encoding="utf-8")
        assert "check_ai_studio.py" in source, f"{script} 没有走共用扫描器"
    assert "ai_studio_violations" in _p.Path(__file__).read_text(encoding="utf-8")
