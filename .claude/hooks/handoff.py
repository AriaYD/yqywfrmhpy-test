#!/usr/bin/env python3
"""CampusPath 上下文交接引擎（compact 前写交接，compact 后自动注入）。

四个入口，全部由 .claude/settings.json 里的 hook 调用，stdin 收 hook payload：

  guard         Stop hook。算当前上下文占比，过软阈值就 block 住这一轮，
                逼 Claude 先更新 PROGRESS.md + 写 .claude/handoff/HANDOFF.md。
  precompact    PreCompact hook。把机器可采集的事实快照到 facts.md，置 pending。
  postcompact   PostCompact hook。stdout 会被 Claude Code 作为消息塞回压缩后的上下文
                （已核实：hookResults 计入 compactedMessageCount），这就是"自动提交给
                新上下文"的那一步。
  sessionstart  SessionStart hook。新窗口/resume 时若有 pending 交接，同样注入。

另有两个人工/测试入口：
  build   重建 facts.md 并把完整注入文本打到 stdout（/handoff 命令与自检脚本用）
  pct     打印某份 transcript 的上下文占比（自检脚本用）

阈值语义（对齐 CLI 2.1.220 实测值，见 .claude/hooks/README.md）：
  有效窗口 = 模型窗口 − 输出预留 20k。**模型窗口不是常数**：
  claude-opus-5 这类原生 1M 的模型是 1M（有效 980k），其余按 200k（有效 180k）算。
  分母由 resolve_limit() 判定，判错会让百分比整体失真——这里踩过一次。
  CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80 → CLI 在有效窗口的 80% 处触发 auto-compact
  本 guard 默认 70% 触发，留 10% 的余量给 Claude 写交接
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

#: 本引擎**只服务 CampusPath**：文案里写死了本项目的必读文档与硬约束，
#: 拿到别的项目会注入错误事实。认这个标记文件，认不到就整个静默退出。
PROJECT_MARKER = os.environ.get(
    "CP_PROJECT_MARKER", "CampusPath_Implementation_Plan_V2.md"
)
#: 弹窗策略：action=只在真的做了事时弹（默认）/ all=每次运行都弹 / off=不弹
NOTIFY_MODE = os.environ.get("CP_NOTIFY", "action")

#: 输出预留：CLI 的有效窗口 = 模型窗口 − min(最大输出, 20000)，见 README
OUTPUT_RESERVE = 20000
#: 原生 1M 上下文的模型（CLI 里 `SZc()` 的 `Wb`/`OH` 分支）。账号档位不够时会退回 200k，
#: 所以下面 resolve_limit() 还有一条按实测反推的兜底规则。
MODELS_1M = ("opus-5", "sonnet-5", "fable-5", "mythos")
CTX_LIMIT_ENV = os.environ.get("CP_CTX_LIMIT")
GUARD_PCT = float(os.environ.get("CP_GUARD_PCT", "70"))
COMPACT_PCT = float(os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "80"))
REFRESH_STEP = float(os.environ.get("CP_REFRESH_STEP", "5"))
MAX_FILES = 25
MAX_EXCHANGES = 8
MAX_TEXT = 400


# --------------------------------------------------------------------------
# 基础设施
# --------------------------------------------------------------------------
def project_dir(payload: dict) -> Path | None:
    """定位项目根；不是 CampusPath 就返回 None（调用方随即静默退出）。"""
    # 只信调用方给的位置。都没给才退回脚本自身所在的仓库——
    # 否则"在别的项目里被调用"会被脚本路径救回来，隔离就形同虚设。
    candidates = [c for c in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")) if c]
    if not candidates:
        candidates = [str(Path(__file__).resolve().parents[2])]
    for candidate in candidates:
        if candidate and (Path(candidate) / PROJECT_MARKER).exists():
            return Path(candidate)
    return None


def notify(subtitle: str, message: str, forced: bool = True) -> None:
    """右上角系统通知。best-effort：通知失败绝不能影响 hook 本身。"""
    if NOTIFY_MODE == "off" or (NOTIFY_MODE == "action" and not forced):
        return
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'display notification {} with title "CampusPath 交接引擎" subtitle {}'.format(
                    json.dumps(message[:200]), json.dumps(subtitle[:60])
                ),
            ],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def handoff_dir(root: Path) -> Path:
    d = root / ".claude" / "handoff"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_payload() -> dict:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, timeout=10
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


# --------------------------------------------------------------------------
# transcript 解析
# --------------------------------------------------------------------------
def load_entries(path: str) -> list[dict]:
    entries: list[dict] = []
    if not path:
        return entries
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return entries


def context_tokens(entries: list[dict]) -> int:
    """主线程最后一条 assistant 消息的 usage 即当前上下文规模。

    input + cache_read + cache_creation 是这一轮真实喂进去的量；再加 output，
    因为它会成为下一轮上下文的一部分（宁可略微高估，早一点提醒）。
    子 agent（isSidechain）的 usage 不算主线程上下文，必须排除。
    """
    for entry in reversed(entries):
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        usage = (entry.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        return (
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0)
            + int(usage.get("output_tokens") or 0)
        )
    return 0


def last_model(entries: list[dict]) -> str:
    for entry in reversed(entries):
        if entry.get("type") == "assistant" and not entry.get("isSidechain"):
            model = (entry.get("message") or {}).get("model")
            if model:
                return str(model)
    return ""


def peak_tokens(entries: list[dict]) -> int:
    peak = 0
    for entry in entries:
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        usage = (entry.get("message") or {}).get("usage")
        if not isinstance(usage, dict):
            continue
        peak = max(
            peak,
            int(usage.get("input_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + int(usage.get("cache_creation_input_tokens") or 0),
        )
    return peak


def resolve_limit(entries: list[dict]) -> int:
    """有效上下文窗口。分母搞错整个提醒就是错的，所以这里三层判定：

    1. `CP_CTX_LIMIT` 显式指定 → 一切以它为准；
    2. 实测反推：200k 窗口里 CLI 会在 187k 处硬阻断，真跑到过 187k 以上就说明窗口更大；
    3. 按模型查表：原生 1M 的模型给 1M，其余 200k。
    """
    if CTX_LIMIT_ENV:
        return int(CTX_LIMIT_ENV)
    if peak_tokens(entries) > 200000 - 13000:
        return 1000000 - OUTPUT_RESERVE
    model = last_model(entries).lower()
    if "[1m]" in model or any(tag in model for tag in MODELS_1M):
        return 1000000 - OUTPUT_RESERVE
    return 200000 - OUTPUT_RESERVE


def context_pct(entries: list[dict]) -> tuple[int, float, int]:
    tokens = context_tokens(entries)
    limit = resolve_limit(entries)
    return tokens, round(tokens / limit * 100, 1), limit


def touched_files(entries: list[dict], root: Path) -> list[str]:
    seen: list[str] = []
    for entry in entries:
        if entry.get("isSidechain"):
            continue
        msg = entry.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") not in ("Write", "Edit", "NotebookEdit"):
                continue
            path = (block.get("input") or {}).get("file_path", "")
            if not path:
                continue
            try:
                path = str(Path(path).resolve().relative_to(root))
            except ValueError:
                pass
            if path not in seen:
                seen.append(path)
    return seen[-MAX_FILES:]


def open_tasks(entries: list[dict]) -> list[str]:
    """从 TaskCreate/TaskUpdate 还原未完成任务。"""
    import re

    pending: dict[str, dict] = {}
    tasks: dict[str, dict] = {}
    for entry in entries:
        if entry.get("isSidechain"):
            continue
        msg = entry.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        if msg.get("role") == "assistant":
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                inp = block.get("input") or {}
                if block.get("name") == "TaskCreate":
                    pending[block.get("id", "")] = {
                        "subject": inp.get("subject", ""),
                        "status": "pending",
                    }
                elif block.get("name") == "TaskUpdate":
                    tid = str(inp.get("taskId", ""))
                    if tid in tasks and inp.get("status"):
                        tasks[tid]["status"] = inp["status"]
        else:
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                key = block.get("tool_use_id", "")
                if key not in pending:
                    continue
                body = block.get("content", "")
                if isinstance(body, list):
                    body = " ".join(
                        b.get("text", "")
                        for b in body
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                match = re.search(r"Task #(\d+)", str(body))
                if match:
                    tasks[match.group(1)] = pending.pop(key)
    for idx, data in enumerate(pending.values()):
        tasks[f"?{idx}"] = data
    return [
        f"[{t['status']}] {t['subject']}"
        for t in tasks.values()
        if t["status"] in ("pending", "in_progress") and t["subject"]
    ]


def recent_exchanges(entries: list[dict]) -> list[str]:
    out: list[str] = []
    for entry in entries:
        if entry.get("isSidechain"):
            continue
        msg = entry.get("message") or {}
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content")
        parts: list[str] = []
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    parts.append(f"[{block.get('name')}]")
        text = " ".join(p for p in parts if p).strip()
        if not text or "<system-reminder>" in text or "<command-name>" in text:
            continue
        if text.startswith("[") and text.endswith("]"):
            continue
        label = "USER" if role == "user" else "CLAUDE"
        out.append(f"**{label}**: {text[:MAX_TEXT]}")
    return out[-(MAX_EXCHANGES * 2):]


# --------------------------------------------------------------------------
# 交接内容
# --------------------------------------------------------------------------
INVARIANTS = """## 1. 必读基线（顺序固定，别读错版本）
- `CLAUDE.md` — 项目硬约束，每个会话自动加载，以它为准
- `CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md` — 产品基线（**不是** `reference/` 下的 V4）
- `CampusPath_Implementation_Plan_V2.md` — 执行计划，WP 划分与验收标准
- `PROGRESS.md` — 进度审计。**每个 WP 收尾必须更新**：只记已验证事实，写"完成"必附验证方式

## 2. 硬约束速查（违反 = 返工）
- **钱只走 Vertex AI**：禁 `google.generativeai` / `GOOGLE_API_KEY` / generativelanguage 端点；<!-- ai-studio-denylist -->

  用 `google-cloud-aiplatform` 或 ADK 的 Vertex 后端。pre-commit + 评测 B12 双重强制。
  preflight 报计费账号不对 → 立即停止并告知用户。
- **架构六条**（Spec §8.9）：A5 是唯一做 trade-off 的 Agent；Wellbeing 全链零 LLM；
  Calendar Token 不进任何 LLM 上下文；A4 工具白名单只有 `read_source` + `emit_opportunity_draft`；
  A5 每个 PlanItem 必带 `validation_id`；A1 只向 Aggregation 传结构化 `EventQualityFeedback`。
- Rules / Capacity & Calendar / Wellbeing Composer **构建期禁止 import 模型 SDK**（CI 断言）。
- 功能基线 **F01–F27 零删减**；改实现位置可以，删功能不行。
- 密钥只进 `.env`（600，已 gitignore），绝不进文档/源码/提交信息/网页/录屏。
- **Harness Engineering**：报实测值不报预期值；检查脚本本身要用"已知会失败的样例"验证它真的会失败。
- **UI**：`frontend-design` + `apple-design` 两个 skill 都要用；中英双语走 i18n 资源；
  必须 chrome-devtools 浏览器实测 + `evaluate_script` 断言 DOM + 双语各一遍 + 截图存 `docs/verification/`。
- **提交纪律**：改文件的任务最终回复前必须 commit；只暂存本任务文件；报 commit hash；
  不 push / 不 amend / 不改写历史。编辑前先看 `git status`，已存在的改动视为用户所有。
- **禁止改动项目已有功能代码**，除非任务明确要求改它。
"""

RESUME_PROTOCOL = """## 5. 恢复协议（按顺序做，别跳）
1. 读 `PROGRESS.md` 的「当前状态」段 —— 断点以它为准，不要凭本交接的摘要臆断。
2. `bash scripts/preflight.sh` —— 有 FAIL 先修，别带病往下做。
3. 对照上面「未完成 / 半成品」继续；**已完成项不要重做**。
4. 不确定的地方先用工具核实（`git log`、`make smoke`、读文件），不猜。
5. 本轮改了文件 → 收尾 commit，并按需更新 `PROGRESS.md`。
"""


def build_facts(root: Path, payload: dict, entries: list[dict]) -> str:
    tokens, pct, limit = context_pct(entries)
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    head = git(root, "log", "-1", "--pretty=%h %s") or "?"
    log = git(root, "log", "-5", "--pretty=  %h %s") or "  (无)"
    status = git(root, "status", "--porcelain") or "  (工作区干净)"
    files = touched_files(entries, root)
    tasks = open_tasks(entries)

    lines = [
        "## 4. 机器采集的事实（不经模型加工，可直接信）",
        f"- 采集时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 压缩前上下文：{tokens:,}/{limit:,} tokens ≈ {pct}%"
        f"（阈值 {GUARD_PCT}% 提醒 / {COMPACT_PCT}% 压缩）",
        f"- 会话：`{payload.get('session_id', '?')}`",
        f"- 分支：`{branch}`  HEAD：`{head}`",
        "",
        "**最近 5 个 commit**",
        "```",
        log,
        "```",
        "",
        "**`git status --porcelain`（未提交的改动 = 半成品线索）**",
        "```",
        status,
        "```",
        "",
    ]
    if files:
        lines += ["**本会话写过的文件**"] + [f"- `{f}`" for f in files] + [""]
    if tasks:
        lines += ["**未完成的 Task**"] + [f"- {t}" for t in tasks] + [""]
    exchanges = recent_exchanges(entries)
    if exchanges:
        lines += ["**压缩前最后几轮对话（截断）**"] + exchanges + [""]
    return "\n".join(lines)


def render(root: Path) -> str:
    hd = handoff_dir(root)
    written = hd / "HANDOFF.md"
    facts = hd / "facts.md"

    head = [
        "=== CampusPath 上下文交接（compact 前自动生成，请当作本轮任务的起点）===",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 0. 立刻要做的三件事",
        "1. 把下面第 3 节「断点」当作当前任务状态，**不要重头开始**；",
        "2. 读 `PROGRESS.md` 的「当前状态」核对断点；",
        "3. 按第 5 节恢复协议继续干活。",
        "",
        INVARIANTS,
    ]

    if written.exists():
        age = (time.time() - written.stat().st_mtime) / 60
        body = written.read_text(encoding="utf-8").strip()
        section = [
            f"## 3. 断点：压缩前由 Claude 亲自写下的交接（{age:.0f} 分钟前）",
            "",
            body,
            "",
        ]
    else:
        section = [
            "## 3. 断点",
            "",
            "> ⚠ 压缩前没有留下人工交接（`.claude/handoff/HANDOFF.md` 不存在）。",
            "> 只能靠下面第 4 节的机器事实推断进度：**先读 `PROGRESS.md` 与 `git status`/`git log` 核实，再动手**。",
            "",
        ]

    tail = [facts.read_text(encoding="utf-8") if facts.exists() else "", RESUME_PROTOCOL,
            "=== 交接结束 ==="]
    return "\n".join(head + section + tail)


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
GUARD_INSTRUCTION = """🛑 上下文已到 {pct}%（{tokens:,}/{limit:,} tokens），{compact_pct}% 就会自动压缩。

现在**立刻**做完这两件事，做完就停，不要开新的大动作：

1. 更新 `PROGRESS.md`：把本轮已验证完成的事项按现有表格格式写进去（只写已验证的，附验证方式与 commit hash）；
   有未提交的改动就先按提交纪律 commit 掉。
2. 覆盖写 `.claude/handoff/HANDOFF.md`，严格用这个骨架，写给"一个完全没有本轮记忆的自己"看：

```markdown
# 断点交接 — <YYYY-MM-DD HH:MM>

## 当前任务
<用户这轮真正要的是什么，一两句；引用原话里的关键约束>

## 已完成（每条附验证方式）
- <事项> — 验证：<实跑了什么，结果多少> — commit：<hash 或 未提交>

## 半成品（最关键的一节，写清楚"停在哪一步"）
- <文件路径:行号> — 已经做到哪 / 还差什么 / 为什么停下 / 有没有临时代码要清理

## 下一步（有序，可直接执行）
1. <具体到命令或文件的动作>
2. ...

## 决策与踩坑（压缩后会丢，必须落在这里）
- <决定了什么、为什么、否决了什么方案>
- <踩过的坑与根因，避免重犯>

## 待确认（需要用户拍板的问题）
- <问题；没有就写"无">
```

两件事做完，回复一句"交接已写入"即可，把控制权交回用户。"""


def cmd_guard(payload: dict) -> int:
    if payload.get("stop_hook_active"):
        return 0
    root = project_dir(payload)
    if root is None:
        return 0
    entries = load_entries(payload.get("transcript_path", ""))
    tokens, pct, limit = context_pct(entries)
    if pct < GUARD_PCT:
        notify("Stop 检查通过", f"上下文 {pct}%，未到 {GUARD_PCT}% 阈值", forced=False)
        return 0

    hd = handoff_dir(root)
    state_file = hd / f".guard-{payload.get('session_id', 'unknown')}.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}

    written = hd / "HANDOFF.md"
    written_at = written.stat().st_mtime if written.exists() else 0.0
    fired_at = float(state.get("fired_at", 0))
    fired_pct = float(state.get("fired_pct", 0))

    if written_at > fired_at and pct < fired_pct + REFRESH_STEP:
        notify("Stop 检查通过", f"上下文 {pct}%，交接已是最新", forced=False)
        return 0  # Claude 已照做，且离上次写入还没涨够 REFRESH_STEP
    if written_at <= fired_at and time.time() - fired_at < 120:
        notify("Stop 检查通过", f"上下文 {pct}%，刚提醒过不重复", forced=False)
        return 0  # 刚提醒过还没写，别连环 block

    state_file.write_text(
        json.dumps({"fired_at": time.time(), "fired_pct": pct}), encoding="utf-8"
    )
    (hd / ".pending").write_text(str(time.time()), encoding="utf-8")
    reason = GUARD_INSTRUCTION.format(
        pct=pct, tokens=tokens, limit=limit, compact_pct=COMPACT_PCT
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    notify("已拦下这一轮 ✋", f"上下文 {pct}%，正在要求 Claude 写断点交接")
    return 0


def cmd_precompact(payload: dict) -> int:
    root = project_dir(payload)
    if root is None:
        return 0
    hd = handoff_dir(root)
    entries = load_entries(payload.get("transcript_path", ""))
    (hd / "facts.md").write_text(build_facts(root, payload, entries), encoding="utf-8")
    (hd / ".pending").write_text(str(time.time()), encoding="utf-8")
    has_written = (hd / "HANDOFF.md").exists()
    print(
        f"[handoff] PreCompact({payload.get('trigger', '?')}): facts 已快照，"
        f"人工交接{'存在' if has_written else '缺失（将只带机器事实）'}，压缩后自动注入。"
    )
    notify(
        "压缩前快照 ✓" if has_written else "压缩前快照 ⚠",
        "事实已存档；" + ("手写交接存在" if has_written else "无手写交接，只能带机器事实"),
    )
    return 0


def consume(root: Path, tag: str) -> int:
    hd = handoff_dir(root)
    text = render(root)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (hd / "archive").mkdir(exist_ok=True)
    (hd / "archive" / f"handoff_{stamp}.md").write_text(text, encoding="utf-8")
    (hd / ".pending").unlink(missing_ok=True)
    print(f"[handoff:{tag}] 已注入压缩前的交接上下文，请据此继续任务，不要重做已完成项。")
    print(text)
    has_written = (hd / "HANDOFF.md").exists()
    notify(
        "交接已注入新上下文 ✓" if has_written else "交接已注入（仅机器事实）⚠",
        f"{tag}；{len(text.splitlines())} 行，留档于 archive/",
    )
    return 0


def cmd_postcompact(payload: dict) -> int:
    root = project_dir(payload)
    if root is None:
        return 0
    return consume(root, f"postcompact/{payload.get('trigger', '?')}")


def cmd_sessionstart(payload: dict) -> int:
    source = payload.get("source", "")
    if source == "compact":
        return 0  # 压缩路径由 PostCompact 负责，避免重复注入
    root = project_dir(payload)
    if root is None:
        return 0
    if not (handoff_dir(root) / ".pending").exists():
        notify("会话启动检查", f"source={source or '?'}，无待交接", forced=False)
        # **无待交接也要出一句话。**
        #
        # 这个 hook 以前在这里静默返回，于是"引擎有没有生效"从开头就看不见——
        # 2026-07-30 有一个会话早于配置 17 小时启动，四个 hook 一个都没加载，
        # 一路涨到 87% 才被发现。SessionStart 是**唯一**能在第一回合就
        # 证明自己活着的地方；它不吭声，失效就必然是无声的。
        print(
            f"[handoff] 引擎已武装：≥{GUARD_PCT:.0f}% 时会拦下 Stop 并要求写交接，"
            f"{os.environ.get('CLAUDE_AUTOCOMPACT_PCT_OVERRIDE', '<未设>')}% 触发自动压缩。"
            "水位与是否生效随时可查：`python3 .claude/hooks/handoff.py status`。"
        )
        return 0
    return consume(root, f"sessionstart/{source or '?'}")


def cmd_build(payload: dict) -> int:
    root = project_dir(payload)
    if root is None:
        print("不是 CampusPath 项目（未找到 " + PROJECT_MARKER + "），已退出。", file=sys.stderr)
        return 0
    entries = load_entries(payload.get("transcript_path", ""))
    (handoff_dir(root) / "facts.md").write_text(
        build_facts(root, payload, entries), encoding="utf-8"
    )
    print(render(root))
    return 0


def cmd_status(payload: dict) -> int:
    """引擎**在这个会话里到底有没有生效**。

    2026-07-30 的教训：本会话启动于 07-29 20:32Z，而注册四个 hook 的
    `.claude/settings.json` 是 07-30 13:48Z 才提交的——晚了约 17 小时。
    Claude Code 在**会话启动时**读取 settings 的 hooks 与 env，
    所以这个进程里根本没有 Stop hook，也没有
    `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80`。

    失效的方式是**无声的**：不报错、不警告，一路涨到 87% 才被人发现
    "怎么什么都没发生"。这个子命令把"有没有武装"变成可以当场查的事实——
    判据是**这个 session_id 有没有留下过 guard 状态文件**，
    那是 guard 真的跑过的唯一证据，比读配置文件可靠：
    配置文件写得再对，也不代表当前进程加载了它。
    """
    root = project_dir(payload)
    if root is None:
        print("不是 CampusPath 项目，引擎不介入。")
        return 0

    entries = load_entries(payload.get("transcript_path", ""))
    tokens, pct, limit = context_pct(entries)
    session_id = payload.get("session_id") or "unknown"
    hd = handoff_dir(root)
    guard_file = hd / f".guard-{session_id}.json"
    ever_fired = guard_file.exists()

    settings = root / ".claude" / "settings.json"
    configured = settings.exists() and "handoff.py" in settings.read_text(
        encoding="utf-8", errors="replace"
    )

    print(json.dumps({
        "session_id": session_id,
        "tokens": tokens,
        "pct": pct,
        "limit": limit,
        "model": last_model(entries),
        "guard_pct": GUARD_PCT,
        "autocompact_pct": os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "<未设>"),
        "hooks_configured_on_disk": configured,
        "guard_ran_in_this_session": ever_fired,
        # 配置在盘上、水位也过了阈值、但 guard 从没跑过 —— 只有一种解释：
        # 这个会话早于配置，hook 没被加载。**重启窗口才会生效。**
        "armed": ever_fired or pct < GUARD_PCT,
        "verdict": (
            "已武装"
            if ever_fired or pct < GUARD_PCT
            else "⚠️ 未武装：配置在盘上但本会话从未触发过 guard，"
                 "几乎可以确定是会话早于配置。**重启这个窗口**后才会生效。"
        ),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_pct(payload: dict) -> int:
    entries = load_entries(payload.get("transcript_path", ""))
    tokens, pct, limit = context_pct(entries)
    print(json.dumps({"tokens": tokens, "pct": pct, "limit": limit,
                      "model": last_model(entries)}))
    return 0


COMMANDS = {
    "status": cmd_status,
    "guard": cmd_guard,
    "precompact": cmd_precompact,
    "postcompact": cmd_postcompact,
    "sessionstart": cmd_sessionstart,
    "build": cmd_build,
    "pct": cmd_pct,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: handoff.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 1
    return COMMANDS[sys.argv[1]](read_payload())


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # hook 永远不许把主流程搞挂
        print(f"[handoff] 内部错误：{exc}", file=sys.stderr)
        notify("Hook 执行失败 ✗", f"{sys.argv[1:2]}：{exc}")
        sys.exit(0)
