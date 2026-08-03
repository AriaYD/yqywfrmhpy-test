"""B11 LLM-free Path Integrity —— monitor 那一段。

判定逻辑在 ``campuspath_contracts.llm_free``（九个服务共用一份）。
此前每个服务各有一份 sed 复制出来的检查代码，第二层对真实发行名
（``google-cloud-aiplatform``）根本不匹配——九份一起无效，谁也没发现。
"""

from __future__ import annotations

import importlib
import pathlib
import pkgutil
import sys

import pytest

import campuspath_monitor
from campuspath_contracts.guards import imported_model_sdks
from campuspath_contracts.llm_free import (
    MODEL_SDK_DISTRIBUTIONS,
    declared_dependency_violations,
    dynamic_access_violations,
    source_import_violations,
)

PACKAGE_ROOT = pathlib.Path(campuspath_monitor.__file__).resolve().parent
DISTRIBUTION = "campuspath-monitor"


def test_scanner_would_catch_a_model_sdk():
    """H5：先证明这个检查真的会失败。"""
    assert imported_model_sdks(["vertexai.generative_models", "json"]) == {
        "vertexai.generative_models"
    }


def test_distribution_names_are_real_pypi_names():
    """曾经用 module.split('.')[0] 推导发行名，得到 'google'——
    真实依赖 google-cloud-aiplatform 一个都匹配不上。"""
    assert "google-cloud-aiplatform" in MODEL_SDK_DISTRIBUTIONS
    assert "google" not in MODEL_SDK_DISTRIBUTIONS


def test_layer1_runtime_imports():
    for info in pkgutil.iter_modules(campuspath_monitor.__path__):
        importlib.import_module(f"campuspath_monitor.{info.name}")
    hits = imported_model_sdks(list(sys.modules))
    assert hits == set(), f"运行时依赖里出现了模型 SDK：{sorted(hits)}"


def test_layer2_declared_dependency_tree():
    assert declared_dependency_violations(DISTRIBUTION) == []


def test_layer3_source_imports():
    assert source_import_violations(PACKAGE_ROOT) == []


def test_layer4_dynamic_and_network_access():
    """惰性导入与裸 HTTP：前三层都挡不住。"""
    assert dynamic_access_violations(PACKAGE_ROOT) == []
