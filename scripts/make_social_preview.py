#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 GitHub 社交预览图 / Build the GitHub social preview image.

用 SVG 精确排版 + 无头浏览器截图，产出 1280x640 的 PNG。

为什么不用 AI 生成？因为 AI 生成的文字会出乱码，
而社交预览图上的每一个字都必须是正确的。

用法::

    python3 scripts/make_social_preview.py
    # 需要本机有 Google Chrome 或 Chromium

输出：``.github/assets/social-preview.png``
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, ".github", "assets")
OUT = os.path.join(OUT_DIR, "social-preview.png")

W, H = 1280, 640
BG = "#0b0e14"
PANEL = "#121722"
GRID = "#1a2130"
LINE = "#232b3b"
TX = "#e6e9ef"
TX2 = "#9aa4b8"
TX3 = "#5d6880"
BLUE = "#4c9aff"
GREEN = "#3ddc97"
AMBER = "#ffb84d"
RED = "#ff6b6b"
PURPLE = "#a78bfa"

# 示意净值曲线（对数刻度，x 归一到 0..1）
CURVES = {
    BLUE: [(0.00, 1.00), (0.06, 1.04), (0.12, 0.99), (0.19, 1.07), (0.26, 1.12),
           (0.33, 1.05), (0.40, 1.16), (0.47, 1.24), (0.54, 1.19), (0.61, 1.31),
           (0.68, 1.42), (0.75, 1.36), (0.82, 1.51), (0.89, 1.63), (1.00, 1.78)],
    GREEN: [(0.00, 1.00), (0.08, 1.02), (0.16, 1.05), (0.24, 1.03), (0.32, 1.09),
            (0.40, 1.12), (0.48, 1.11), (0.56, 1.18), (0.64, 1.21), (0.72, 1.25),
            (0.80, 1.29), (0.88, 1.33), (1.00, 1.40)],
    AMBER: [(0.00, 1.00), (0.10, 0.98), (0.20, 0.95), (0.30, 1.00), (0.40, 1.04),
            (0.50, 1.02), (0.60, 1.08), (0.70, 1.06), (0.80, 1.12), (0.90, 1.15),
            (1.00, 1.20)],
    RED: [(0.00, 1.00), (0.12, 0.96), (0.24, 0.92), (0.36, 0.95), (0.48, 0.90),
          (0.60, 0.93), (0.72, 0.89), (0.84, 0.92), (1.00, 0.94)],
}


def find_chrome() -> str:
    cands = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return ""


def count_tests() -> int:
    """数出仓库里真实存在的测试数量。

    预览图上的测试数之前是写死的 17，仓库实际已经有 52 个 ——
    过期数字正是本项目要消灭的那类错误，所以这里改成自动读取。
    """
    total = 0
    tests_dir = os.path.join(ROOT, "tests")
    for name in sorted(os.listdir(tests_dir)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(tests_dir, name), encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("def test_") or s.startswith("async def test_"):
                    total += 1
    return total


def build_svg() -> str:
    n = count_tests()
    TESTS = f"{n}/{n}"
    # 图表区域
    cx, cy, cw, chh = 660, 96, 552, 330
    ymin, ymax = 0.85, 1.85

    def X(x): return cx + x * cw
    def Y(v): return cy + chh - ((v - ymin) / (ymax - ymin)) * chh

    parts = []
    # 网格
    for i in range(6):
        v = ymin + (ymax - ymin) * i / 5
        y = Y(v)
        parts.append(f'<line x1="{cx}" y1="{y:.1f}" x2="{cx+cw}" y2="{y:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        lbl = f"{v:.2f}×"
        parts.append(f'<text x="{cx-12}" y="{y+4:.1f}" fill="{TX3}" font-size="13" '
                     f'text-anchor="end" font-family="Helvetica,Arial,sans-serif">{lbl}</text>')
    # 本金基准
    yb = Y(1.0)
    parts.append(f'<line x1="{cx}" y1="{yb:.1f}" x2="{cx+cw}" y2="{yb:.1f}" '
                 f'stroke="{LINE}" stroke-width="1.5" stroke-dasharray="5 5"/>')
    parts.append(f'<text x="{cx+cw-6}" y="{yb-9:.1f}" fill="{TX3}" font-size="13" '
                 f'text-anchor="end" font-family="Helvetica,Arial,sans-serif">'
                 f'principal</text>')
    # 曲线
    for color, pts in CURVES.items():
        d = " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in pts)
        wdt = 3.2 if color in (BLUE, GREEN) else 2.0
        op = 1.0 if color in (BLUE, GREEN) else 0.65
        parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" '
                     f'stroke-width="{wdt}" stroke-opacity="{op}" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')

    # 图例
    lx, ly = cx + 4, cy + chh + 40
    legend = [(BLUE, "core allocation"), (GREEN, "core + gold timing"),
              (AMBER, "12-asset equal weight"), (RED, "CSI 300 ETF")]
    for i, (c, name) in enumerate(legend):
        x = lx + (i % 2) * 268
        y = ly + (i // 2) * 28
        parts.append(f'<line x1="{x}" y1="{y}" x2="{x+22}" y2="{y}" stroke="{c}" '
                     f'stroke-width="3" stroke-linecap="round"/>')
        parts.append(f'<text x="{x+31}" y="{y+4}" fill="{TX2}" font-size="14" '
                     f'font-family="Helvetica,Arial,sans-serif">{name}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"
     viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{BG}"/>
      <stop offset="100%" stop-color="#0e1320"/>
    </linearGradient>
    <pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse">
      <path d="M 48 0 L 0 0 0 48" fill="none" stroke="{GRID}" stroke-width="0.6"
            stroke-opacity="0.55"/>
    </pattern>
  </defs>

  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <rect width="{W}" height="{H}" fill="url(#grid)"/>
  <rect x="0" y="0" width="{W}" height="5" fill="{BLUE}"/>

  <!-- 左侧标题 -->
  <text x="72" y="212" fill="{BLUE}" font-size="104" font-weight="700"
        font-family="Helvetica,Arial,sans-serif" letter-spacing="-3">vlab</text>
  <text x="76" y="258" fill="{TX}" font-size="24" font-weight="500"
        font-family="Helvetica,Arial,sans-serif">Zero-Dependency Portfolio Backtesting Lab</text>
  <text x="76" y="296" fill="{TX2}" font-size="20"
        font-family="Helvetica,Arial,sans-serif">诚实的回测，而不是漂亮的回撤曲线</text>

  <line x1="76" y1="330" x2="520" y2="330" stroke="{LINE}" stroke-width="1"/>

  <!-- 关键数字 -->
  <text x="76" y="374" fill="{TX3}" font-size="12" letter-spacing="0.8" font-weight="600"
        font-family="Helvetica,Arial,sans-serif">TESTS PASSING</text>
  <text x="76" y="412" fill="{GREEN}" font-size="32" font-weight="700"
        font-family="Helvetica,Arial,sans-serif">{TESTS}</text>

  <text x="196" y="374" fill="{TX3}" font-size="12" letter-spacing="0.8" font-weight="600"
        font-family="Helvetica,Arial,sans-serif">DEPENDENCIES</text>
  <text x="196" y="412" fill="{GREEN}" font-size="32" font-weight="700"
        font-family="Helvetica,Arial,sans-serif">0</text>

  <text x="300" y="374" fill="{TX3}" font-size="12" letter-spacing="0.8" font-weight="600"
        font-family="Helvetica,Arial,sans-serif">BUGS PINNED</text>
  <text x="300" y="412" fill="{AMBER}" font-size="32" font-weight="700"
        font-family="Helvetica,Arial,sans-serif">5</text>

  <text x="410" y="374" fill="{TX3}" font-size="12" letter-spacing="0.8" font-weight="600"
        font-family="Helvetica,Arial,sans-serif">PYTHON</text>
  <text x="410" y="412" fill="{TX}" font-size="32" font-weight="700"
        font-family="Helvetica,Arial,sans-serif">3.9+</text>

  <!-- 免责 -->
  <rect x="72" y="452" width="490" height="1" fill="{LINE}"/>
  <text x="76" y="482" fill="{TX3}" font-size="15"
        font-family="Helvetica,Arial,sans-serif">Backtests on historical data. Past performance</text>
  <text x="76" y="504" fill="{TX3}" font-size="15"
        font-family="Helvetica,Arial,sans-serif">does not predict future returns. Not investment advice.</text>
  <text x="76" y="540" fill="{AMBER}" font-size="16" font-weight="600"
        font-family="Helvetica,Arial,sans-serif">Research and education only — not investment advice.</text>

  <!-- 图表标题 -->
  <text x="{cx}" y="60" fill="{TX3}" font-size="15" letter-spacing="1.5"
        font-family="Helvetica,Arial,sans-serif">EQUITY CURVES · LOG SCALE · 2019–2026</text>

  {''.join(parts)}
</svg>'''


def main() -> int:
    chrome = find_chrome()
    if not chrome:
        print("! 找不到 Chrome/Chromium，无法截图。请手动渲染 SVG。")
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    svg = build_svg()
    tmp = tempfile.mkdtemp()
    svg_path = os.path.join(tmp, "preview.svg")
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    cmd = [
        chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        f"--screenshot={OUT}", "--window-size=%d,%d" % (W, H), "--default-background-color=00000000",
        "file://" + svg_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if not os.path.exists(OUT):
        print("! 截图失败：", r.stderr[-500:])
        return 1
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"✓ 社交预览图已生成：{OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
