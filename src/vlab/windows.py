# -*- coding: utf-8 -*-
"""回测窗口定义 / Backtest windows.

**为什么需要两个窗口？**
------------------------
本项目的资产池跨越两个市场，且部分标的上市较晚：

======================  ==============  ====================
标的                    首个交易日      在 Steve 配置中占比
======================  ==============  ====================
sh512890 红利低波        2019-01-18      **25%**
sh512800 银行ETF         2017-08-03      0%（仅基准用）
sh510300 / sh511010 等   2014-01-02      35%
usSPY.OQ / usXLF.OQ     2001-01-02      5%
======================  ==============  ====================

若回测起点早于某标的的上市日，该标的的权重会被"提前入场"，
这叫**穿越时空**，会让回撤被严重低估 —— 本项目早期版本正是因此
错误地报出"2015–2026 年最大回撤仅 -13%"。

因此定义两个窗口：

``A`` 投资现实口径（2019-01-18 ~ 至今）
    起点 = **所有可投标的均已上市**的最早交易日。这是现实中能真实
    执行的口径，也是对外结论的主口径。

``B`` 指数代理长口径（2008-07-01 ~ 至今）
    起点 = 中证红利指数上市日（2008-07-31 附近）。用**指数**代理
    早期尚不存在的 ETF，以覆盖 2008 金融危机。用于回答
    "这套配置在极端行情里到底扛不扛得住"。

两个窗口的结论**必须分开陈述**，混用即为误导。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

#: 窗口 key -> (起始日, 结束日, 显示名, 说明)
WINDOWS: Dict[str, Tuple[str, str, str, str]] = {
    "A": (
        "2019-01-18",
        "2026-11-26",
        "投资现实口径 2019–2026",
        "起点为所有可投标的均已上市的最早交易日（红利低波 ETF 上市日）。"
        "这是现实中可执行的主口径。",
    ),
    "B": (
        "2008-07-01",
        "2026-11-26",
        "指数代理长口径 2008–2026",
        "用中证红利等指数代理早期尚不存在的 ETF，覆盖 2008 金融危机。"
        "用于检验极端行情下的抗跌能力，不代表可直接执行。",
    ),
}

#: 面板默认展示的窗口
DEFAULT_WINDOW = "A"

#: 各资产的首个交易日（由数据自动探测，此处仅作文档参考）
LISTING_HINTS = {
    "sh512890": "2019-01-18",
    "sh512800": "2017-08-03",
    "sh510300": "2014-01-02",
    "sh510880": "2014-01-02",
    "sh511010": "2014-01-02",
    "sh511990": "2014-01-02",
    "sh513100": "2014-01-02",
    "sh518880": "2014-01-02",
    "ixsh000300": "2005-04-08",
    "ixsh000922": "2008-07-31",
    "usSPY.OQ": "2001-01-02",
    "usXLF.OQ": "2001-01-02",
    "usQQQ.OQ": "2001-01-02",
    "usAGG.OQ": "2005-01-03",
    "usGLD.OQ": "2004-11-18",
    "usIWM.OQ": "2005-01-03",
    "usUUP.OQ": "2007-03-01",
}


def window_label(key: str) -> str:
    return WINDOWS[key][2]


def window_note(key: str) -> str:
    return WINDOWS[key][3]


def window_bounds(key: str) -> Tuple[str, str]:
    a, b, _n, _d = WINDOWS[key]
    return a, b


def slice_window(dates: List[str], mat: Dict, key: str):
    """把统一交易日轴切到指定窗口。

    返回 ``(dates, mat)``，``mat`` 的每一列都同步切片。
    """
    d0, d1 = window_bounds(key)
    idx = [i for i, d in enumerate(dates) if d0 <= d <= d1]
    D = [dates[i] for i in idx]
    M = {c: [col[i] for i in idx] for c, col in mat.items()}
    return D, M


def earliest_listing(dates: List[str], mat: Dict, codes: List[str]) -> str:
    """求一组标的全部可用的最早交易日。

    用于自动确定"投资现实口径"的起点，避免手写日期与实际数据脱节。
    """
    best = None
    for c in codes:
        col = mat.get(c)
        if not col:
            continue
        for i, v in enumerate(col):
            if v is not None:
                if best is None or dates[i] < best:
                    best = dates[i]
                break
    return best or (dates[0] if dates else "")
