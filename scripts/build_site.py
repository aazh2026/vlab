#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 GitHub Pages 静态站 / Build the static site for GitHub Pages.

产出 ``site/`` 目录，内容包括：

* ``index.html``  —— 交互式面板（零 CDN，单文件，可离线打开）
* ``report.json`` —— 回测报告数据
* ``data.js``     —— 报告数据的 JS 包装（供无服务器环境直接读取）

用法::

    python3 scripts/build_site.py

不需要网络 —— 使用本地已缓存的行情数据。若没有缓存数据，
脚本会尝试在线抓取（``python3 -m vlab fetch``）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
DATA_DIR = os.path.join(ROOT, "data")
RESULTS_DIR = os.path.join(ROOT, "results")
SITE_DIR = os.path.join(ROOT, "site")
WEB_DIR = os.path.join(SRC, "vlab", "web")

sys.path.insert(0, SRC)


def build() -> int:
    from vlab.engine import load_series
    from vlab.report import build_report, save

    if not os.path.isdir(DATA_DIR) or not os.listdir(DATA_DIR):
        print("! 没有本地行情数据，正在尝试在线抓取…")
        try:
            from vlab.cli import cmd_fetch
            import argparse
            cmd_fetch(argparse.Namespace(codes=[], force=False))
        except Exception as e:
            print("! 抓取失败：", e)
            print("! 请先运行：PYTHONPATH=src python3 -m vlab fetch")
            return 1

    series = load_series(data_dir=DATA_DIR)
    if not series:
        print("! 无可用数据，无法构建站点")
        return 1

    rep = build_report(series)
    save(rep, os.path.join(RESULTS_DIR, "report.json"))

    if os.path.isdir(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    os.makedirs(SITE_DIR)

    # 1) 面板 HTML：改成读取同目录的 report.json（相对路径，Pages 可直接用）
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as f:
        html = f.read()
    html = html.replace('fetch("api/report"', 'fetch("report.json"')
    html = html.replace('fetch("api/rebuild"', 'fetch("api/rebuild"')
    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    # 2) 报告 JSON
    shutil.copy(os.path.join(RESULTS_DIR, "report.json"),
                os.path.join(SITE_DIR, "report.json"))

    # 3) JS 包装（便于在控制台或 notebook 里直接引用）
    with open(os.path.join(SITE_DIR, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.VLAB_REPORT = ")
        json.dump(rep, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    # 4) 免责声明单独的纯文本文件，方便被引用
    with open(os.path.join(SITE_DIR, "DISCLAIMER.txt"), "w", encoding="utf-8") as f:
        f.write(rep["disclaimer_zh"] + "\n\n" + rep["disclaimer_en"] + "\n")

    size = sum(
        os.path.getsize(os.path.join(SITE_DIR, n)) for n in os.listdir(SITE_DIR)
    )
    print(f"✓ 站点已构建：{SITE_DIR}  ({size/1024:.0f} KB)")
    for n in sorted(os.listdir(SITE_DIR)):
        p = os.path.join(SITE_DIR, n)
        print(f"    {n:20} {os.path.getsize(p)/1024:8.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(build())
