# -*- coding: utf-8 -*-
"""策略定义 / Strategy definitions.

每个策略都是一个 ``weights_fn(date, mat, dates, index) -> {code: weight}``。

命名约定
--------
* ``bench_*`` —— 买入持有基准，用于对照
* ``core_*``  —— 组合型策略
"""
from __future__ import annotations

from typing import Dict

from .engine import GOLD_BANDS, STRATEGY_CURRENT, const_weights


class Strategy:
    """一个策略：显示名 + 权重函数 + 涉及的资产代码 + 分组。

    显式记录 ``codes`` 是为了避免"用源码正则猜资产"这种脆弱做法
    （const_weights 把权重藏在闭包里，正则看不到）。
    """

    __slots__ = ("label", "fn", "codes", "group", "note")

    def __init__(self, label, fn, codes, group="core", note=""):
        self.label = label
        self.fn = fn
        self.codes = list(codes)
        self.group = group
        self.note = note

    def __call__(self, *a, **kw):
        return self.fn(*a, **kw)

# --------------------------------------------------------------------------
# 基准：纯单资产
# --------------------------------------------------------------------------
BENCH_12 = {
    "sh510300": 1 / 12, "sh510880": 1 / 12, "sh512890": 1 / 12,
    "sh512800": 1 / 12, "sh518880": 1 / 12, "sh511010": 1 / 12,
    "sh511990": 1 / 12, "sh513100": 1 / 12, "usSPY.OQ": 1 / 12,
    "usXLF.OQ": 1 / 12, "usQQQ.OQ": 1 / 12, "usAGG.OQ": 1 / 12,
}

BENCH_7_INDEX = {
    "ixsh000300": 1 / 7, "ixsh000922": 1 / 7, "ixsh000015": 1 / 7,
    "ixsh000905": 1 / 7, "usSPY.OQ": 1 / 7, "usAGG.OQ": 1 / 7, "usGLD.OQ": 1 / 7,
}

# --------------------------------------------------------------------------
# Steve 核心配置
# --------------------------------------------------------------------------
def steve_static(d, mat, dates, i) -> Dict[str, float]:
    """静态配置：权重永不改变（仅在月度调仓日按当前权重再平衡）。"""
    return dict(STRATEGY_CURRENT)


def _gold_weight(gold_price: float) -> float:
    """金价分档 → 黄金目标权重。"""
    for ceiling, w in GOLD_BANDS:
        if gold_price <= ceiling:
            return w
    return 0.0


def steve_gold_timing(d, mat, dates, i) -> Dict[str, float]:
    """配置 + 黄金分档择时。

    金价越低，黄金仓位越高；超过 4000 美元清零黄金。
    其余资产权重按比例缩放以保持总权重为 1（且总权重永不超过 1）。
    """
    w = dict(STRATEGY_CURRENT)
    col = mat.get("sh518880")
    gp = None
    if col is not None and i < len(col) and col[i] is not None:
        gp = col[i]
    if gp is None:
        return w

    target_gold = _gold_weight(gp)
    base_gold = w.get("sh518880", 0.0)
    if abs(target_gold - base_gold) < 1e-9:
        return w

    others = {c: v for c, v in w.items() if c != "sh518880"}
    others_total = sum(others.values())
    scale = (1.0 - target_gold) / others_total if others_total > 0 else 0.0
    out = {c: v * scale for c, v in others.items()}
    out["sh518880"] = target_gold
    return out


# --------------------------------------------------------------------------
# 策略注册表
# --------------------------------------------------------------------------
# key -> (显示名, 策略函数, 分组)
#   分组 "core" = 核心策略，"bench" = 基准对照
STRATEGIES = {
    "steve":       ("Steve 配置（静态）",      steve_static,      "core"),
    "steve_gold":  ("Steve 配置 + 黄金择时",   steve_gold_timing, "core"),
    "eq12":        ("12 资产等权",             const_weights(BENCH_12),        "bench"),
    "eq7":         ("7 资产等权（指数代理）",  const_weights(BENCH_7_INDEX),  "bench"),
    "dividend":    ("纯红利低波",              const_weights({"sh512890": 1.0}),        "bench"),
    "csi300":      ("纯沪深300 ETF",           const_weights({"sh510300": 1.0}),        "bench"),
    "csi300_ix":   ("纯沪深300 指数",          const_weights({"ixsh000300": 1.0}),      "bench"),
    "dividend_ix": ("纯中证红利指数",          const_weights({"ixsh000922": 1.0}),      "bench"),
    "spy":         ("纯标普500",               const_weights({"usSPY.OQ": 1.0}),        "bench"),
    "gold":        ("纯黄金 ETF",              const_weights({"sh518880": 1.0}),        "bench"),
    "agg":         ("纯美债",                  const_weights({"usAGG.OQ": 1.0}),        "bench"),
    "money":       ("纯货币 ETF",              const_weights({"sh511990": 1.0}),        "bench"),
    "6040":        ("60/40 组合",
                    const_weights({"sh511010": .4, "sh510300": .3,
                                   "sh512890": .2, "sh518880": .1}),                "bench"),
}

#: 策略注册表：key -> Strategy
STRATEGIES = {
    "steve": Strategy(
        "Steve 配置（静态）", steve_static,
        list(STRATEGY_CURRENT.keys()), "core",
        "当前建议配置，权重恒定，每月再平衡",
    ),
    "steve_gold": Strategy(
        "Steve 配置 + 黄金择时", steve_gold_timing,
        list(STRATEGY_CURRENT.keys()), "core",
        "在静态配置基础上，按金价分档调整黄金权重",
    ),
    "eq12": Strategy(
        "12 资产等权", const_weights(BENCH_12), list(BENCH_12.keys()), "bench",
    ),
    "eq7": Strategy(
        "7 资产等权（指数代理）", const_weights(BENCH_7_INDEX),
        list(BENCH_7_INDEX.keys()), "bench",
        "用指数代理早期尚未上市的 ETF，用于长周期检验",
    ),
    "dividend": Strategy(
        "纯红利低波", const_weights({"sh512890": 1.0}), ["sh512890"], "bench"),
    "csi300": Strategy(
        "纯沪深300 ETF", const_weights({"sh510300": 1.0}), ["sh510300"], "bench"),
    "csi300_ix": Strategy(
        "纯沪深300 指数", const_weights({"ixsh000300": 1.0}), ["ixsh000300"], "bench"),
    "dividend_ix": Strategy(
        "纯中证红利指数", const_weights({"ixsh000922": 1.0}), ["ixsh000922"], "bench"),
    "spy": Strategy(
        "纯标普500", const_weights({"usSPY.OQ": 1.0}), ["usSPY.OQ"], "bench"),
    "gold": Strategy(
        "纯黄金 ETF", const_weights({"sh518880": 1.0}), ["sh518880"], "bench"),
    "agg": Strategy(
        "纯美债", const_weights({"usAGG.OQ": 1.0}), ["usAGG.OQ"], "bench"),
    "money": Strategy(
        "纯货币 ETF", const_weights({"sh511990": 1.0}), ["sh511990"], "bench"),
    "6040": Strategy(
        "60/40 组合",
        const_weights({"sh511010": .4, "sh510300": .3,
                       "sh512890": .2, "sh518880": .1}),
        ["sh511010", "sh510300", "sh512890", "sh518880"], "bench"),
}

#: 面板里默认高亮/置顶的策略
PRIMARY = ("steve", "steve_gold")
