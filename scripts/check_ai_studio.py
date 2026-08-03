#!/usr/bin/env python3
"""B12：扫描源码里的 AI Studio 路径。供 preflight.sh 与 pre-commit 共用。

为什么不用 grep：现行的 `google-genai` SDK **两种后端都支持**——

    genai.Client(vertexai=True, project=..., location=...)   → Vertex，吃赠金 ✅
    genai.Client(api_key=...)                                → AI Studio，直扣个人卡 ❌

要区分这两者需要看构造点附近有没有 `vertexai=True`，grep 做不了邻近判断。
一刀切按包名禁掉又会在 WP6 挡住我们自己该走的 Vertex 路径。

用法：
    python3 scripts/check_ai_studio.py <文件...>      # 退出码非零表示有命中
    python3 scripts/check_ai_studio.py --self-test    # 用已知会失败的样例验证扫描器
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "contracts"))

from campuspath_contracts.guards import ai_studio_violations  # noqa: E402

CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                 ".json", ".toml", ".yaml", ".yml", ".sh", ".ipynb"}

#: H5：扫描器必须先被已知会失败的样例验证过。
_PROBES: tuple[tuple[str, str, bool], ...] = (
    ("旧版 AI Studio SDK", "import google.generativeai as g\n", True),                  # ai-studio-denylist
    ("AI Studio 端点", 'U = "https://generativelanguage.googleapis.com/v1beta"\n', True),  # ai-studio-denylist
    ("API key 环境变量", 'k = os.environ["GEMINI_API_KEY"]\n', True),                    # ai-studio-denylist
    ("GOOGLE_API_KEY", 'GOOGLE_API_KEY = "AIza..."\n', True),                          # ai-studio-denylist
    ("双后端 SDK 未指定 Vertex", "c = genai.Client(api_key=k)\n", True),                 # ai-studio-denylist
    (
        "双后端 SDK 跨行指定 Vertex",
        "c = genai.Client(\n    vertexai=True,\n    project=P,\n)\n",
        False,
    ),
    ("双后端 SDK 同行指定 Vertex", "c = genai.Client(vertexai=True, project=P)\n", False),
    ("正当的禁用词表", 'B = ("google.generativeai",)  # ai-studio-denylist\n', False),      # ai-studio-denylist
    ("无关代码", "from vertexai import init\ninit(project=P)\n", False),
)


def self_test() -> int:
    failures = 0
    for label, source, should_flag in _PROBES:
        flagged = bool(ai_studio_violations(source))
        if flagged != should_flag:
            print(f"  ✗ {label}：期望 {'拦截' if should_flag else '放行'}，实际相反", file=sys.stderr)
            failures += 1
        else:
            print(f"  ✓ {label}：{'拦截' if should_flag else '放行'}")
    if failures:
        print(f"\n扫描器自检失败 {failures} 项", file=sys.stderr)
        return 1
    print(f"\n扫描器对全部 {len(_PROBES)} 个样例判断正确")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()

    paths = [pathlib.Path(a) for a in argv if not a.startswith("-")]
    offenders: list[str] = []
    for path in paths:
        if path.suffix not in CODE_SUFFIXES or not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for hit in ai_studio_violations(source):
            offenders.append(f"{path}:{hit}")

    if offenders:
        print("代码中引用了 AI Studio 路径（赠金不覆盖，会直扣信用卡，见 CLAUDE.md）：",
              file=sys.stderr)
        for line in offenders[:10]:
            print(f"    {line}", file=sys.stderr)
        print("    → 改用 Vertex：genai.Client(vertexai=True, ...) 或 ADK 的 Vertex 后端",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
