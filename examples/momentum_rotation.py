# -*- coding: utf-8 -*-
"""示例：动量轮动策略 / Example: momentum rotation.

用法 / Usage::

    PYTHONPATH=src python3 -m vlab validate examples/momentum_rotation.py

策略契约
--------
必须定义 ``weights_fn(date, mat, dates, index) -> {code: weight}``。

诚实性约束
----------
* ``mat`` 只能读到 ``[0, index]``。读未来数据会抛
  ``vlab.guard.LookAheadError`` —— 这是故意的。
* ``index`` 之前的日期在本函数里**不可见**。需要回看窗口的策略
  （如 60 日动量）请让引擎从更早的起点跑，``vlab validate`` 会自动
  在完整历史上运行再切分指标。
"""
RISK = ["sh510300", "sh512890", "sh512800", "sh513100",
        "usSPY.OQ", "usXLF.OQ", "usQQQ.OQ", "sh518880"]
BOND = "sh511010"
LOOKBACK = 60
N_TOP = 3
BOND_W = 0.10


def weights_fn(date, mat, dates, index):
    if index < LOOKBACK:
        return {}
    scored = []
    for c in RISK:
        col = mat.get(c)
        if col is None:
            continue
        a, b = col[index], col[index - LOOKBACK]
        if a is None or b is None or b <= 0:
            continue
        scored.append((a / b - 1.0, c))
    if not scored:
        return {}
    scored.sort(reverse=True)
    out = {c: (1.0 - BOND_W) / N_TOP for _, c in scored[:N_TOP]}
    out[BOND] = BOND_W
    return out
