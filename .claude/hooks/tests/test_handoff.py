#!/usr/bin/env python3
"""handoff.py 自检。

Harness 规矩：每个检查都配一个"已知会失败的样例"，证明它真的会红——
所以这里既测"该拦的拦住了"，也测"不该拦的没拦"，还测"把过滤器拿掉就会误报"。

跑法： python3 .claude/hooks/tests/test_handoff.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "handoff.py"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}{'  — ' + detail if detail and not ok else ''}")


def run(cmd: str, payload: dict, env: dict | None = None) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOK), cmd],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return proc.returncode, proc.stdout, proc.stderr


def transcript(path: Path, tokens: int, sidechain: bool = False,
               model: str = "claude-haiku-4-5-20251001") -> str:
    """造一份 transcript：最后一条主线程 assistant 消息的 usage 决定上下文规模。"""
    rows = [
        {
            "type": "user",
            "message": {"role": "user", "content": "把 WP7 的双语切换做完"},
        },
        {
            "type": "assistant",
            "isSidechain": sidechain,
            "message": {
                "role": "assistant",
                "model": model,
                "content": [
                    {"type": "text", "text": "先看现有 i18n 资源"},
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "Edit",
                        "input": {"file_path": "/tmp/app/i18n.ts"},
                    },
                ],
                "usage": {
                    "input_tokens": 2,
                    "cache_read_input_tokens": tokens - 2,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 0,
                },
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    return str(path)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="handoff-test-"))
    (root / "CLAUDE.md").write_text("# fake project\n", encoding="utf-8")
    # 引擎靠这个标记文件认定"这是 CampusPath"，测试里要伪造一份
    (root / "CampusPath_Implementation_Plan_V2.md").write_text("# fake plan\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    env = {
        "CLAUDE_PROJECT_DIR": str(root),
        "CP_CTX_LIMIT": "1000",
        "CP_GUARD_PCT": "70",
        "CP_NOTIFY": "off",  # 自检时别弹 20 多个通知
    }
    hd = root / ".claude" / "handoff"

    # --- 占比计算 -------------------------------------------------------
    tp = transcript(root / "t_low.jsonl", 300)
    _, out, _ = run("pct", {"transcript_path": tp}, env)
    check("pct: 300/1000 算成 30%", json.loads(out)["pct"] == 30.0, out)

    tp_hi = transcript(root / "t_hi.jsonl", 850)
    _, out, _ = run("pct", {"transcript_path": tp_hi}, env)
    check("pct: 850/1000 算成 85%", json.loads(out)["pct"] == 85.0, out)

    # 已知会失败的样例：子 agent 的 usage 不许算进主线程
    tp_side = transcript(root / "t_side.jsonl", 950, sidechain=True)
    _, out, _ = run("pct", {"transcript_path": tp_side}, env)
    check("pct: sidechain 的 usage 被排除（拿掉过滤器这条会红）",
          json.loads(out)["tokens"] == 0, out)

    # --- 分母判定（踩过的坑：把 1M 窗口当成 200k，18% 被算成 95%）---------
    noenv = {k: v for k, v in env.items() if k != "CP_CTX_LIMIT"}
    tp_opus = transcript(root / "t_opus.jsonl", 178797, model="claude-opus-5")
    _, out, _ = run("pct", {"transcript_path": tp_opus}, noenv)
    got = json.loads(out)
    check("分母: opus-5 按 1M 窗口算（980k）", got["limit"] == 980000, out)
    check("分母: 178,797 tokens 因此是 18.2% 而不是 95%", got["pct"] == 18.2, out)

    tp_haiku = transcript(root / "t_haiku.jsonl", 90000)
    _, out, _ = run("pct", {"transcript_path": tp_haiku}, noenv)
    check("分母: haiku-4.5 按 200k 窗口算（180k）",
          json.loads(out)["limit"] == 180000, out)

    # 兜底：模型不认识，但实测跑到过 187k 以上 → 窗口必然大于 200k
    tp_unknown = transcript(root / "t_unknown.jsonl", 300000, model="mystery-model")
    _, out, _ = run("pct", {"transcript_path": tp_unknown}, noenv)
    check("分母: 未知模型但实测超 187k → 反推为 1M 窗口",
          json.loads(out)["limit"] == 980000, out)

    _, out, _ = run("pct", {"transcript_path": tp_opus}, {**noenv, "CP_CTX_LIMIT": "180000"})
    check("分母: CP_CTX_LIMIT 显式指定时压过自动判定",
          json.loads(out)["limit"] == 180000, out)

    # --- guard 触发条件 -------------------------------------------------
    code, out, _ = run("guard", {"transcript_path": tp, "session_id": "s1"}, env)
    check("guard: 30% 不打断", code == 0 and out.strip() == "", out)

    code, out, _ = run("guard", {"transcript_path": tp_hi, "session_id": "s2"}, env)
    blocked = out.strip() and json.loads(out).get("decision") == "block"
    check("guard: 85% 打断并要求写交接", bool(blocked), out)
    reason = json.loads(out)["reason"] if blocked else ""
    check("guard: 打断文案带 HANDOFF.md 骨架",
          all(k in reason for k in ("HANDOFF.md", "半成品", "PROGRESS.md", "下一步")),
          reason[:200])

    code, out, _ = run(
        "guard", {"transcript_path": tp_hi, "session_id": "s3", "stop_hook_active": True}, env
    )
    check("guard: stop_hook_active=true 时绝不打断（防死循环）",
          code == 0 and out.strip() == "", out)

    # 同一会话紧接着再来一次 → 闩锁生效，不连环打断
    code, out, _ = run("guard", {"transcript_path": tp_hi, "session_id": "s2"}, env)
    check("guard: 刚提醒过且交接未写 → 不重复打断", out.strip() == "", out)

    # Claude 照做写了 HANDOFF.md → 同一水位不再打断
    hd.mkdir(parents=True, exist_ok=True)
    (hd / "HANDOFF.md").write_text(
        "# 断点交接 — 2026-07-30 04:00\n\n## 半成品\n- agents/x.py:42 停在写测试\n",
        encoding="utf-8",
    )
    time.sleep(0.05)
    code, out, _ = run("guard", {"transcript_path": tp_hi, "session_id": "s2"}, env)
    check("guard: 交接已写入后同水位不再打断", out.strip() == "", out)

    # 水位再涨 5% 以上 → 重新提醒
    tp_hi2 = transcript(root / "t_hi2.jsonl", 950)
    code, out, _ = run("guard", {"transcript_path": tp_hi2, "session_id": "s2"}, env)
    check("guard: 水位再涨 5%+ 会要求刷新交接",
          bool(out.strip() and json.loads(out).get("decision") == "block"), out)

    # --- 压缩前后 -------------------------------------------------------
    code, out, _ = run(
        "precompact", {"transcript_path": tp_hi, "session_id": "s2", "trigger": "auto"}, env
    )
    check("precompact: 快照 facts.md", (hd / "facts.md").exists())
    check("precompact: 置 pending 标记", (hd / ".pending").exists())
    facts = (hd / "facts.md").read_text(encoding="utf-8")
    check("precompact: facts 含 git status 与本会话改过的文件",
          "git status" in facts and "i18n.ts" in facts)

    code, out, _ = run("postcompact", {"session_id": "s2", "trigger": "auto"}, env)
    need = [
        "CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md",
        "CampusPath_Implementation_Plan_V2.md",
        "PROGRESS.md",
        "Vertex AI",
        "validation_id",
        "F01–F27",
        "停在写测试",       # Claude 手写交接的正文
        "机器采集的事实",   # facts
        "恢复协议",
    ]
    missing = [n for n in need if n not in out]
    check("postcompact: 注入内容含必读文档 / 硬约束 / 手写断点 / 事实 / 恢复协议",
          not missing, f"缺: {missing}")
    check("postcompact: 消费后清掉 pending", not (hd / ".pending").exists())
    check("postcompact: 归档一份", any((hd / "archive").glob("handoff_*.md")))

    # 已知会失败的样例：没有人工交接时必须显式警告，而不是假装有进度
    (hd / "HANDOFF.md").unlink()
    code, out, _ = run("postcompact", {"session_id": "s9", "trigger": "auto"}, env)
    check("postcompact: 缺人工交接时明确告警", "没有留下人工交接" in out, out[:200])

    # --- 新窗口注入 -----------------------------------------------------
    code, out, _ = run("sessionstart", {"session_id": "s2", "source": "compact"}, env)
    check("sessionstart: source=compact 不重复注入", out.strip() == "", out[:120])

    # 这条原来断言"无 pending 时保持安静"。**那句断言本身就是那个 bug。**
    # 2026-07-30：一个会话早于 settings.json 约 17 小时启动，四个 hook 一个都
    # 没加载，而 SessionStart 正好什么都不说——于是"引擎没生效"从第一回合
    # 起就不可见，一路涨到 87% 才被人发现。安静是代价最高的默认值。
    # 现在要求它出一句话：**只报状态，不注入交接**（注入仍以 .pending 为准）。
    code, out, _ = run("sessionstart", {"session_id": "s2", "source": "startup"}, env)
    check("sessionstart: 无 pending 时报告自己活着，但不注入交接",
          "引擎已武装" in out and "断点交接" not in out, out[:160])

    (hd / ".pending").write_text("1", encoding="utf-8")
    code, out, _ = run("sessionstart", {"session_id": "s2", "source": "startup"}, env)
    check("sessionstart: 有 pending 的新窗口自动注入",
          "CampusPath 上下文交接" in out, out[:120])
    check("sessionstart: 注入后清 pending", not (hd / ".pending").exists())

    # --- 只在本项目生效（拿掉标记检查，下面四条都会红）--------------------
    other = Path(tempfile.mkdtemp(prefix="other-project-"))
    (other / "CLAUDE.md").write_text("# 别的项目\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=other, capture_output=True)
    oenv = {**env, "CLAUDE_PROJECT_DIR": str(other)}
    for cmd, payload in (
        ("guard", {"transcript_path": tp_hi2, "session_id": "x"}),
        ("precompact", {"transcript_path": tp_hi2, "session_id": "x", "trigger": "auto"}),
        ("postcompact", {"session_id": "x", "trigger": "auto"}),
        ("sessionstart", {"session_id": "x", "source": "startup"}),
    ):
        code, out, _ = run(cmd, payload, oenv)
        check(f"项目隔离: 别的项目里 {cmd} 完全静默", code == 0 and out.strip() == "", out[:120])
    check("项目隔离: 不在别的项目里建交接目录", not (other / ".claude" / "handoff").exists())
    shutil.rmtree(other, ignore_errors=True)

    # --- 健壮性 ---------------------------------------------------------
    code, out, err = run("guard", {"transcript_path": "/nope/nope.jsonl", "session_id": "s4"}, env)
    check("健壮性: transcript 不存在时不打断也不崩", code == 0 and out.strip() == "")
    proc = subprocess.run(
        [sys.executable, str(HOOK), "guard"], input="not json", capture_output=True, text=True,
        env={**os.environ, **env},
    )
    check("健壮性: 收到坏 JSON 也退出 0", proc.returncode == 0)

    # ── 「引擎到底有没有生效」必须查得出来（2026-07-30 的教训）──────
    #
    # 那次失效的方式是**无声的**：会话早于 settings.json 约 17 小时，
    # 四个 hook 一个都没加载，一路涨到 87% 才被人发现什么都没发生。
    # 所以 status 必须把"配置在盘上"与"本会话真的武装过"分开报——
    # 只查配置文件的检查器，在那次事故里会一路报绿。
    tp_status = transcript(root / "status.jsonl", 900)   # 90% > 阈值 70%
    _, out, _ = run("status", {"cwd": str(root), "session_id": "never-guarded",
                               "transcript_path": tp_status}, env)
    unarmed = json.loads(out)
    check("status: 过了阈值却从没跑过 guard → 报未武装",
          unarmed["armed"] is False and unarmed["guard_ran_in_this_session"] is False,
          out[:200])

    (hd / ".guard-armed.json").write_text('{"fired_at": 1, "fired_pct": 80}',
                                          encoding="utf-8")
    _, out, _ = run("status", {"cwd": str(root), "session_id": "armed",
                               "transcript_path": tp_status}, env)
    armed = json.loads(out)
    check("status: 跑过 guard → 报已武装", armed["armed"] is True, out[:200])

    # H5：两个会话看到的配置完全一样，武装状态却必须不同——
    # 这证明判据不是"配置在不在盘上"，否则上面两条会同时为真。
    check("status 的判据是「跑过没有」而非「配得对不对」",
          armed["hooks_configured_on_disk"] == unarmed["hooks_configured_on_disk"]
          and armed["armed"] != unarmed["armed"],
          f"configured 相同={armed['hooks_configured_on_disk']}")

    # SessionStart 无待交接时也要出声，否则失效永远是无声的
    for stale in hd.glob(".pending"):
        stale.unlink()
    _, out, _ = run("sessionstart", {"cwd": str(root), "source": "startup",
                                     "session_id": "s"}, env)
    check("sessionstart: 无待交接时也报告自己活着", "引擎已武装" in out, out[:160])

    shutil.rmtree(root, ignore_errors=True)
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("失败项：" + ", ".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
