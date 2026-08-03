"""B11 的可复用检查器：确定性服务不得以**任何方式**接触模型。

九个服务此前各有一份 sed 复制出来的 ``test_llm_free.py``。复制品会各自漂移，
而且第二层当时对真实的发行名（``google-cloud-aiplatform``）根本不匹配——
九份一起无效。判定逻辑集中到这里，测试只负责调用。

四层，各挡一种躲法：

1. **运行时** —— 导入整个包后 ``sys.modules`` 里不能出现模型 SDK；
2. **依赖树** —— 声明的依赖（含传递）不能出现模型 SDK 的**发行名**；
3. **源码 import** —— 静态的 ``import x`` / ``from x import y``；
4. **动态与网络** —— ``importlib.import_module("vertexai")`` 这类惰性导入，
   以及直接对 ``aiplatform.googleapis.com`` 发裸 HTTP。

第 4 层是审查实测出来的：前三层挡不住把 import 挪进函数体再用字符串拼，
也挡不住绕开 SDK 直接 POST。
"""

from __future__ import annotations

import ast
import importlib.metadata
import pathlib
import re

from .guards import MODEL_SDK_MODULES, imported_model_sdks

__all__ = [
    "MODEL_SDK_DISTRIBUTIONS",
    "MODEL_ENDPOINT_HOSTS",
    "declared_dependency_violations",
    "source_import_violations",
    "dynamic_access_violations",
]

#: PyPI 上的**发行名**，与 import 名不同。
#: 曾经的实现用 ``module.split(".")[0].replace("_", "-")`` 推导，得到的是
#: ``google``——真实依赖 ``google-cloud-aiplatform`` 一个都匹配不上，
#: 而那恰恰是 CLAUDE.md 指定的那个 SDK。
MODEL_SDK_DISTRIBUTIONS = frozenset(
    {
        "google-cloud-aiplatform",
        "google-generativeai",   # ai-studio-denylist
        "google-genai",
        "google-adk",
        "langchain-google-genai",
        "vertexai",
        "openai",
        "anthropic",
        "litellm",
        "transformers",
    }
)

#: 绕开 SDK 直接发请求同样是"接触模型"。
MODEL_ENDPOINT_HOSTS = frozenset(
    {
        "aiplatform.googleapis.com",
        "generativelanguage.googleapis.com",   # ai-studio-denylist
        "api.openai.com",
        "api.anthropic.com",
    }
)

_DYNAMIC_IMPORTERS = {"import_module", "__import__"}


def declared_dependency_violations(distribution: str) -> list[str]:
    """遍历声明的依赖（含传递），按**发行名**匹配。"""
    seen: set[str] = set()
    frontier = [distribution]
    while frontier:
        name = frontier.pop()
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            requires = importlib.metadata.requires(name) or []
        except importlib.metadata.PackageNotFoundError:
            continue
        for requirement in requires:
            if "extra ==" in requirement:
                continue
            dependency = re.split(r"[<>=!~\[; ]", requirement.strip(), 1)[0]
            if dependency:
                frontier.append(dependency)
    return sorted(d for d in seen if d in MODEL_SDK_DISTRIBUTIONS)


def source_import_violations(root: pathlib.Path) -> list[str]:
    """静态 import 语句。用 AST 而非正则，免得被续行或缩进骗过。"""
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                      # pragma: no cover
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for hit in imported_model_sdks(names):
                offenders.append(f"{path.name}:{node.lineno} import {hit}")
    return offenders


def dynamic_access_violations(root: pathlib.Path) -> list[str]:
    """惰性导入与裸 HTTP。

    审查实测：把 ``import vertexai`` 换成函数体里的
    ``importlib.import_module("vertexai.generative_models")``，
    或者直接 ``urllib.request`` POST 到 aiplatform 端点，
    前三层**全部**放行。
    """
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")

        for host in sorted(MODEL_ENDPOINT_HOSTS):
            for match in re.finditer(re.escape(host), source):
                line_no = source.count("\n", 0, match.start()) + 1
                line = source.splitlines()[line_no - 1]
                if "ai-studio-denylist" in line or "MODEL_ENDPOINT_HOSTS" in line:
                    continue
                offenders.append(f"{path.name}:{line_no} 直接访问 {host}")

        try:
            tree = ast.parse(source)
        except SyntaxError:                      # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name) else ""
            )
            if name not in _DYNAMIC_IMPORTERS:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if imported_model_sdks([arg.value]):
                        offenders.append(
                            f"{path.name}:{node.lineno} 动态导入 {arg.value}"
                        )
                else:
                    offenders.append(
                        f"{path.name}:{node.lineno} 动态导入的模块名不是字面量，无法静态判定"
                    )
    return offenders
