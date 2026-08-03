#!/usr/bin/env python3
"""Seed 命令行。

    python3 -m campuspath_seed.cli build --profile full
    python3 -m campuspath_seed.cli check --profile full
    python3 -m campuspath_seed.cli selftest      # 验证检查器真的会失败
    python3 -m campuspath_seed.cli reproduce     # 两次构建字节比对

``make seed-reset`` 走的是 ``build``：删掉旧产物重新生成，
同一 Seed 版本必然得到同一份数据（Spec §11.5）。
"""

from __future__ import annotations

import argparse
import shutil
import sys

from .build import OUT_DIR, _canonical_json, build_seed, write_seed
from .consistency import run_checks, run_selftest

GREEN, RED, YELLOW, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def _cmd_build(args: argparse.Namespace) -> int:
    target = OUT_DIR / args.profile
    if args.reset and target.exists():
        shutil.rmtree(target)
    path = write_seed(args.profile)
    print(f"{GREEN}✓{RESET} 已生成 {args.profile} 数据集 → {path}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    bundle = build_seed(args.profile)
    failures = 0
    for result in run_checks(bundle):
        if result.ok:
            print(f"  {GREEN}✓{RESET} {result.name}")
        else:
            failures += 1
            print(f"  {RED}✗{RESET} {result.name} —— {result.detail}")
    print()
    if failures:
        print(f"{RED}{failures} 项一致性检查失败{RESET}")
        return 1
    print(f"{GREEN}全部一致性检查通过{RESET}")
    return 0


def _cmd_selftest(args: argparse.Namespace) -> int:
    # 变异样例是针对 full 数据集设计的（例如"把某门课的先修挪到本课之后"
    # 需要数据里真的存在一条 AND-only 的先修链）。在 tiny 上跑会因为找不到
    # 可变异的记录而误报，所以这里固定用 full——**不是**静默跳过某些变异。
    if args.profile != "full":
        print(f"{YELLOW}!{RESET} selftest 固定在 full 数据集上运行（变异样例针对 full 设计）")
    bundle = build_seed("full")
    results = run_selftest(bundle)
    misses = 0
    for label, caught, detail in results:
        if caught:
            print(f"  {GREEN}✓{RESET} {label}")
        else:
            misses += 1
            print(f"  {RED}✗{RESET} {label} —— 检查器没抓住 {detail}")
    print()
    if misses:
        print(f"{RED}{misses} 个已知矛盾未被检查器抓住{RESET}")
        return 1
    print(f"{GREEN}检查器对全部 {len(results)} 个已知矛盾均报错{RESET}")
    return 0


def _cmd_reproduce(args: argparse.Namespace) -> int:
    first = _canonical_json(build_seed(args.profile))
    second = _canonical_json(build_seed(args.profile))
    if first != second:
        print(f"{RED}✗ 两次构建结果不一致——Seed 不可复现{RESET}")
        return 1
    print(f"{GREEN}✓{RESET} 两次构建字节一致（{len(first):,} 字符）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="campuspath_seed")
    parser.add_argument("--profile", default="full", choices=("full", "tiny"))
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="生成数据集")
    build.add_argument("--reset", action="store_true", help="先删除旧产物")
    build.set_defaults(func=_cmd_build)

    sub.add_parser("check", help="跨表一致性校验").set_defaults(func=_cmd_check)
    sub.add_parser("selftest", help="用已知矛盾验证检查器").set_defaults(func=_cmd_selftest)
    sub.add_parser("reproduce", help="两次构建字节比对").set_defaults(func=_cmd_reproduce)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
