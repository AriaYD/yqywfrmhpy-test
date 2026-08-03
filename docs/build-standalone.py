#!/usr/bin/env python3
"""
构建可独立托管的 CampusPath 说明网页（中/英两个版本）。

为什么需要构建步骤：
- Artifact 运行时会自动包裹 <!doctype>/<head>/<body>，并原生渲染 mermaid；
- 独立托管（GitHub Pages 等）两者都没有，需要自己补文档骨架并从 CDN 引入 mermaid。

CSS 只维护一份（在中文源文件里），英文源用 /*__SHARED_CSS__*/ 占位，
构建时注入，保证两个语言版本的视觉与行为不会漂移。

产出：
  dist/zh/index.html   中文版（本地查看，不发布）
  dist/en/index.html   英文版（GitHub Pages 发布用）

用法：python3 docs/build-standalone.py
"""

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
SRC_ZH = HERE / "campuspath-visual.html"
SRC_EN = HERE / "campuspath-visual-en.src.html"
DIST = HERE / "dist"

MERMAID_VER = "11.4.1"


def extract_css(text: str) -> str:
    """取中文源文件里的第一个 <style> 块作为共享样式。"""
    m = re.search(r"<style>(.*?)</style>", text, re.S)
    if not m:
        sys.exit("✗ 没有在中文源文件里找到 <style> 块")
    return m.group(1)


def split_title(text: str):
    """把片段自带的 <title> 抽出来，避免文档里出现两个 title。"""
    m = re.search(r"<title>(.*?)</title>\s*", text, re.S)
    if not m:
        return "CampusPath", text
    return m.group(1).strip(), text[: m.start()] + text[m.end() :]


def head(title: str, lang: str) -> str:
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<style>
  /* 与 Artifact 宿主一致的最小重置 */
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 0; }}
  img {{ max-width: 100%; }}
  /* mermaid 渲染完成前隐藏源码文本，避免闪现一屏流程图源码 */
  pre.mermaid {{ visibility: hidden; }}
  pre.mermaid[data-processed="true"] {{ visibility: visible; }}
</style>
</head>
<body>
"""


FOOT = f"""
<script src="https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VER}/dist/mermaid.min.js"></script>
<script>
(function () {{
  if (!window.mermaid) {{        // CDN 不可达时至少把源码显示出来，不留白屏
    document.querySelectorAll('pre.mermaid').forEach(function (p) {{
      p.style.visibility = 'visible';
      p.style.whiteSpace = 'pre-wrap';
      p.style.fontSize = '11px';
    }});
    return;
  }}
  mermaid.initialize({{
    startOnLoad: true,
    securityLevel: 'loose',      // 允许 htmlLabels，F 编号要在 foreignObject 里可点击
    flowchart: {{ htmlLabels: true, useMaxWidth: false }},
    theme: 'base',
    themeVariables: {{
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: '12px',
      primaryColor: '#FFFFFF',
      primaryTextColor: '#0B1A2B',
      primaryBorderColor: '#8A93A2',
      lineColor: '#5C6675',
      clusterBkg: '#E4E7E4',
      clusterBorder: '#B6BBB6',
      edgeLabelBackground: '#F1F2F0'
    }}
  }});
}})();
</script>
</body>
</html>
"""


def build(src: pathlib.Path, out_dir: pathlib.Path, lang: str, css: str | None = None):
    body = src.read_text(encoding="utf-8")
    if css is not None:
        if "/*__SHARED_CSS__*/" not in body:
            sys.exit(f"✗ {src.name} 里缺少 /*__SHARED_CSS__*/ 占位符")
        body = body.replace("/*__SHARED_CSS__*/", css)
    title, body = split_title(body)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(head(title, lang) + body + FOOT, encoding="utf-8")
    (out_dir / ".nojekyll").touch()
    print(f"  {lang:5s} → {out.relative_to(HERE.parent)}  ({out.stat().st_size:,} bytes)")
    return out


def main():
    zh_text = SRC_ZH.read_text(encoding="utf-8")
    css = extract_css(zh_text)
    print(f"共享 CSS: {len(css):,} 字符")
    build(SRC_ZH, DIST / "zh", "zh-Hans")
    build(SRC_EN, DIST / "en", "en", css=css)

    # 一致性自检：两个版本的功能数、箭头数、图数必须相同
    en = (DIST / "en" / "index.html").read_text(encoding="utf-8")
    zh = (DIST / "zh" / "index.html").read_text(encoding="utf-8")
    checks = {
        "mermaid 图": lambda t: t.count('class="mermaid"'),
        "F 功能条目": lambda t: len(re.findall(r"\['F\d{2}',", t)),
        "E 箭头条目": lambda t: len(re.findall(r"\['E\d{1,2}',", t)),
        "Agent 卡": lambda t: len(re.findall(r"id:'A\d'", t)),
    }
    ok = True
    for name, fn in checks.items():
        a, b = fn(zh), fn(en)
        flag = "✓" if a == b else "✗"
        if a != b:
            ok = False
        print(f"  {flag} {name}: 中文 {a} / 英文 {b}")
    if not ok:
        sys.exit("✗ 两个语言版本内容数量不一致")
    print("两版内容对齐 ✓")


if __name__ == "__main__":
    main()
