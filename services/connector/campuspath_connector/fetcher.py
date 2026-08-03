"""共享抓取器与内容变更检测（C2，2026-08-02）。

三个 seed/scrape_hkust_*.py 脚本各自维护的 fetch 逻辑抽取到这里：
stdlib urllib（零第三方依赖，B11 扫描友好）+ 磁盘缓存 + 1s 礼貌间隔 + 统一 UA。
新增变更检测：归一化正文的 sha256 —— registry 存上次哈希，
比对结果只有 changed / unchanged / error 三态，不做任何语义判断。

registry 里标 `render: "js"` 的源（如 studyabroad program-search）需要浏览器
渲染，本模块的 stdlib 抓取对它们只能拿到壳——调用方应按 render 字段跳过或
换用可选引擎（Crawl4AI，未装则如实报 error，不假装抓到了）。
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CampusPath-research/1.0"
DELAY = 1.0  # 秒；礼貌间隔，别改小
TIMEOUT = 30

_TAG_SCRIPT = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_ANY = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def fetch(url: str, cache_dir: pathlib.Path | None = None, cache_key: str | None = None,
          *, delay: float = DELAY) -> str:
    """带可选磁盘缓存的 GET。缓存命中就不发请求（离线可重复）。"""
    if cache_dir is not None and cache_key is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"{cache_key}.html"
        if cached.exists():
            return cached.read_text(encoding="utf-8", errors="ignore")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        html = r.read().decode("utf-8", errors="ignore")
    if cache_dir is not None and cache_key is not None:
        (cache_dir / f"{cache_key}.html").write_text(html, encoding="utf-8")
    time.sleep(delay)
    return html


def normalize_text(html: str) -> str:
    """去 script/style/标签/空白——只留可见正文，让哈希对无关噪声免疫。"""
    text = _TAG_SCRIPT.sub(" ", html)
    text = _TAG_ANY.sub(" ", text)
    return _WS.sub(" ", text).strip()


def content_hash(html: str) -> str:
    return hashlib.sha256(normalize_text(html).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProbeResult:
    outcome: Literal["changed", "unchanged", "error"]
    new_hash: str | None = None
    detail: str | None = None
    text_excerpt: str | None = None  # changed 时带归一化正文（供 A4 抽取）


def probe(url: str, previous_hash: str | None, *, delay: float = DELAY,
          excerpt_chars: int = 20_000) -> ProbeResult:
    """抓一次并与上次哈希比对。**永不抛异常**——error 是合法结果，
    调用方据此更新 Source Health，而不是让整轮巡检崩掉。"""
    try:
        html = fetch(url, delay=delay)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return ProbeResult(outcome="error", detail=f"{type(exc).__name__}: {exc}")
    digest = content_hash(html)
    if previous_hash is not None and digest == previous_hash:
        return ProbeResult(outcome="unchanged", new_hash=digest)
    return ProbeResult(
        outcome="changed",
        new_hash=digest,
        text_excerpt=normalize_text(html)[:excerpt_chars],
    )
