# -*- coding: utf-8 -*-
"""vlab 命令行入口 / CLI.

::

    python3 -m vlab fetch          # 抓取并缓存行情数据
    python3 -m vlab report         # 生成回测报告 JSON
    python3 -m vlab serve          # 启动本地面板
    python3 -m vlab test           # 跑回归测试
    python3 -m vlab compare        # 命令行输出策略对比表
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA_DIR = os.path.join(ROOT, "data")
RESULTS_DIR = os.path.join(ROOT, "results")
WEB_DIR = os.path.join(HERE, "web")


def _ensure(path):
    os.makedirs(path, exist_ok=True)
    return path


# --------------------------------------------------------------------------
def cmd_fetch(args):
    """抓取全部标的的日线数据并缓存。"""
    from .datasource import fetch
    from .engine import UNIVERSE

    _ensure(DATA_DIR)
    codes = list(args.codes) if args.codes else [c for c, *_ in UNIVERSE]
    codes += ["ixsh000300", "ixsh000922", "ixsh000015", "ixsh000905"]
    ok, fail = 0, 0
    for c in dict.fromkeys(codes):
        rows = fetch(c, DATA_DIR, force=args.force)
        if rows:
            print(f"  ✓ {c:14} n={len(rows):6}  {rows[0]['d']} -> {rows[-1]['d']}")
            ok += 1
        else:
            print(f"  ✗ {c:14} 抓取失败")
            fail += 1
    print(f"\n完成：成功 {ok}，失败 {fail}。数据目录：{DATA_DIR}")
    return 0 if fail == 0 else 1


# --------------------------------------------------------------------------
def cmd_report(args):
    """生成回测报告 JSON。"""
    from .engine import load_series
    from .report import build_report, save

    _ensure(RESULTS_DIR)
    series = load_series(data_dir=DATA_DIR)
    if not series:
        print("没有可用数据，请先运行：python3 -m vlab fetch", file=sys.stderr)
        return 1
    rep = build_report(series, cash0=args.cash)
    out = save(rep, os.path.join(RESULTS_DIR, "report.json"))
    print(f"报告已生成：{out}")
    for wk, w in rep["windows"].items():
        print(f"\n=== 窗口 {wk}: {w['label']}  {w['start']} ~ {w['end']} ({w['days']}日) ===")
        for k, s in sorted(w["strategies"].items(),
                           key=lambda x: -x[1]["metrics"]["cagr"]):
            m = s["metrics"]
            print(f"  {s['label']:24} 年化{m['cagr']*100:6.2f}%  "
                  f"回撤{m['maxdd']*100:7.2f}%  夏普{m['sharpe']:5.2f}  "
                  f"期末{s['final_eq']:>12,.0f}")
    return 0


# --------------------------------------------------------------------------
def cmd_serve(args):
    """启动本地面板服务。"""
    sys.path.insert(0, os.path.dirname(HERE))
    from vlab.web.server import serve
    serve(port=args.port, data_dir=DATA_DIR, web_dir=WEB_DIR,
          host=args.host, cache_path=os.path.join(RESULTS_DIR, "report.json"))
    return 0


# --------------------------------------------------------------------------
def cmd_test(args):
    """跑回归测试。"""
    import unittest
    tests_dir = os.path.join(ROOT, "tests")
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir)
    runner = unittest.TextTestRunner(verbosity=2)
    return 0 if runner.run(suite).wasSuccessful() else 1


# --------------------------------------------------------------------------
def cmd_compare(args):
    """命令行输出策略对比表（读取已有报告）。"""
    import json
    path = os.path.join(RESULTS_DIR, "report.json")
    if not os.path.exists(path):
        print("找不到报告，请先运行：python3 -m vlab report", file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as f:
        rep = json.load(f)
    for wk in args.windows:
        w = rep["windows"].get(wk)
        if not w:
            continue
        print(f"\n=== {w['label']}  {w['start']} ~ {w['end']} ===")
        print(f"{'策略':<24}{'年化':>8}{'回撤':>9}{'夏普':>7}{'Calmar':>8}{'期末':>14}")
        for k, s in sorted(w["strategies"].items(),
                           key=lambda x: -x[1]["metrics"]["cagr"]):
            m = s["metrics"]
            print(f"{s['label']:<24}{m['cagr']*100:>7.2f}%{m['maxdd']*100:>8.2f}%"
                  f"{m['sharpe']:>7.2f}{m['calmar']:>8.2f}{s['final_eq']:>14,.0f}")
    print("\n" + rep.get("disclaimer_zh", ""))
    return 0


# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(
        prog="vlab",
        description="vlab — 零依赖的资产配置回测实验室",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fetch", help="抓取并缓存行情数据")
    pf.add_argument("--codes", nargs="*", help="只抓指定标的")
    pf.add_argument("--force", action="store_true", help="忽略缓存强制重抓")
    pf.set_defaults(func=cmd_fetch)

    pr = sub.add_parser("report", help="生成回测报告")
    pr.add_argument("--cash", type=float, default=1_000_000.0, help="初始本金")
    pr.set_defaults(func=cmd_report)

    ps = sub.add_parser("serve", help="启动本地面板")
    ps.add_argument("--port", type=int, default=8765)
    ps.add_argument("--host", default="0.0.0.0")
    ps.set_defaults(func=cmd_serve)

    pt = sub.add_parser("test", help="跑回归测试")
    pt.set_defaults(func=cmd_test)

    pc = sub.add_parser("compare", help="命令行输出策略对比表")
    pc.add_argument("--windows", nargs="*", default=["A", "B"])
    pc.set_defaults(func=cmd_compare)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
