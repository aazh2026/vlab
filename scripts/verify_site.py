#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验已提交的 GitHub Pages 产物是否完整一致 / Verify committed site artifacts.

CI 里不联网重新构建（行情数据是本地缓存，体积大且可复现），
而是校验已提交的 ``docs/`` 产物是否自洽：

* ``index.html`` 存在，且引用的是相对路径 ``report.json``
* ``report.json`` 能解析，且包含两个回测窗口与免责声明
* 面板需要的 DOM 挂载点都在
* ``DISCLAIMER.txt`` 非空

用法::

    python3 scripts/verify_site.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "docs")

REQUIRED_IDS = ["app"]


def fail(msg: str) -> None:
    print("✗ " + msg)
    sys.exit(1)


def main() -> int:
    idx = os.path.join(SITE, "index.html")
    rep = os.path.join(SITE, "report.json")
    dis = os.path.join(SITE, "DISCLAIMER.txt")

    for p in (idx, rep, dis):
        if not os.path.exists(p):
            fail("缺少文件: " + os.path.relpath(p, ROOT))

    html = open(idx, encoding="utf-8").read()
    if 'fetch("report.json"' not in html:
        fail("index.html 未使用相对路径读取 report.json（Pages 上会 404）")
    for i in REQUIRED_IDS:
        if f'id="{i}"' not in html:
            fail(f"index.html 缺少挂载点 id={i}")
    if "cdn." in html or "https://unpkg" in html or "cdnjs" in html:
        fail("index.html 引用了外部 CDN —— 必须保证离线可打开")

    data = json.load(open(rep, encoding="utf-8"))
    for w in ("A", "B"):
        if w not in data.get("windows", {}):
            fail(f"report.json 缺少窗口 {w}")
    for s in ("disclaimer_zh", "disclaimer_en"):
        if not data.get(s):
            fail(f"report.json 缺少 {s}")
    for w in data["windows"].values():
        if not w.get("strategies"):
            fail("窗口 " + w.get("label", "?") + " 没有策略结果")

    d = open(dis, encoding="utf-8").read().strip()
    if len(d) < 50:
        fail("DISCLAIMER.txt 内容过短")

    n = sum(len(w["strategies"]) for w in data["windows"].values())
    print(f"✓ 站点产物校验通过：{n} 条策略曲线，双窗口，免责声明完整，零 CDN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
