# -*- coding: utf-8 -*-
"""自定义策略沙盒 / Custom strategy sandbox.

让用户在面板上直接配置自己的资产配置权重，跑一次回测，并同时看到
**样本内 / 样本外**两段结果。

设计原则（与本项目其余部分一致）：

1. **不承诺任何东西。** 输出的是历史回测，不是预测。
2. **口径分离。** 用户选的窗口（投资现实口径 A / 指数代理长口径 B）
   决定数据切片方式，两个窗口的结论永不混用。
3. **权重不足 1 的部分留在现金。** 绝不静默归一化到 1 ——
   那是本项目 BUG-3 的教训。
4. **不可投资的标的权重不转嫁。** 若某标的在窗口起点尚未上市，
   它的权重留在现金并明确告知用户，而不是挤到其他资产上。
5. **零第三方依赖。** 只用标准库与本项目已有的引擎。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from . import engine, metrics, validate, windows as W

#: 调仓频率 -> 显示名
REBAL_MODES = {
    "monthly":  ("每月", "Monthly"),
    "quarterly": ("每季", "Quarterly"),
    "yearly":   ("每年", "Yearly"),
    "hold":     ("买入持有（仅一次）", "Buy & hold (once)"),
}

CURVE_POINTS = 520


def _downsample(xs: List, n: int = CURVE_POINTS) -> List[int]:
    """等距降采样索引，保留首尾。"""
    if len(xs) <= n:
        return list(range(len(xs)))
    step = (len(xs) - 1) / (n - 1)
    idx = sorted({int(round(i * step)) for i in range(n)})
    idx[0] = 0
    idx[-1] = len(xs) - 1
    return idx


def _rebal_dates(mode: str, dates: Sequence[str]) -> set:
    """按频率挑出调仓日。

    ``hold`` 只在第一天调仓一次 —— 之后权重随价格漂移，
    这才是真正的买入持有。
    """
    me = engine.month_ends(dates)
    if mode == "monthly":
        return me
    if mode == "quarterly":
        return {d for d in me if d[5:7] in ("03", "06", "09", "12")}
    if mode == "yearly":
        return {d for d in me if d[5:7] == "12"}
    # hold: 第一天之后的月份都不再调仓
    first = dates[0] if dates else None
    return {d for d in me if d == first or d[:7] == first[:7]}


def _pack_curve(curve: List[Dict]) -> Dict:
    """把回测曲线打包成面板可用的结构（含降采样与回撤序列）。"""
    eq = [c["eq"] for c in curve]
    dates = [c["d"] for c in curve]
    idx = _downsample(eq)
    dd = metrics.drawdown_series(eq)
    return {
        "dates": [dates[i] for i in idx],
        "eq": [eq[i] for i in idx],
        "dd": {
            "dates": [dates[i] for i in idx],
            "v": [dd[i] for i in idx],
        },
        "final_eq": eq[-1] if eq else 0.0,
    }


def _metrics_of(curve: List[Dict]) -> Dict:
    eq = [c["eq"] for c in curve]
    dates = [c["d"] for c in curve]
    m = metrics.summarize(eq, dates)
    return {
        "total": m["total"], "cagr": m["cagr"], "vol": m["vol"],
        "sharpe": m["sharpe"], "sortino": m["sortino"],
        "maxdd": m["maxdd"], "maxdd_date": m["maxdd_date"],
        "calmar": m["calmar"], "win_rate": m["win_rate"],
        "days": m["days"], "start": m["start"], "end": m["end"],
    }


def analyze_weights(
    weights: Dict[str, float],
    data_dir: str,
    window: str = "A",
    rebal: str = "monthly",
    cash0: float = 1_000_000.0,
    fee_bps: float = engine.DEFAULT_FEE_BPS,
    slip_bps: float = engine.DEFAULT_SLIP_BPS,
    split_ratio: float = 0.7,
    cash_apy: float = 0.0,
) -> Dict:
    """跑一次自定义配置，回测 + 样本内/样本外切分。

    返回可直接 JSON 序列化的字典。
    """
    if window not in W.WINDOWS:
        window = W.DEFAULT_WINDOW

    series = engine.load_series(data_dir=data_dir)
    if not series:
        return {"error": "no data; run `python3 -m vlab fetch` first"}
    dates = engine.trading_dates(series)
    mat = engine.align(series, dates)
    D, M_ = W.slice_window(dates, mat, window)
    if len(D) < 30:
        return {"error": f"window {window} has too few trading days ({len(D)})"}

    # ---- 清洗用户输入的权重 ----
    clean: Dict[str, float] = {}
    for c, v in (weights or {}).items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > 0 and c in M_:
            clean[c] = fv
    if not clean:
        return {"error": "no valid positive weights"}

    requested_total = sum(clean.values())
    # 超过 1 的部分会被引擎按比例缩放到 1 —— 与引擎语义保持一致，
    # 但必须明确告知用户，而不是静默处理。
    scaled = requested_total > 1.0

    # ---- 不可投资标的：权重留在现金，不转嫁 ----
    not_listed = [c for c in clean
                  if M_[c][0] is None or M_[c][0] <= 0]
    investable_total = sum(v for c, v in clean.items() if c not in not_listed)
    cash_weight = max(0.0, 1.0 - (investable_total if not scaled
                                   else min(investable_total, 1.0)))

    fn = engine.const_weights(clean)
    rd = _rebal_dates(rebal, D)
    bt = {"start_cash": cash0, "fee_bps": fee_bps, "slip_bps": slip_bps,
          "rebal_dates": rd, "cash_apy": cash_apy}

    res = engine.backtest(fn, M_, D, **bt)
    curve = res["curve"]

    out: Dict = {
        "ok": True,
        "window": window,
        "window_label": W.window_label(window),
        "rebal": rebal,
        "weights": clean,
        "requested_total": requested_total,
        "scaled_to_one": scaled,
        "not_listed": not_listed,
        "cash_weight": cash_weight,
        "investable_total": investable_total,
        "metrics": _metrics_of(curve),
        "curve": _pack_curve(curve),
        "trade_count": len(res["trades"]),
        "fee_bps": fee_bps,
        "slip_bps": slip_bps,
        # 现金计息必须如实披露：引擎默认 0（保守），
        # 界面不得替用户假设一个利率。
        "cash_apy": cash_apy,
        "interest_earned": res.get("interest_earned", 0.0),
    }

    # ---- 样本内 / 样本外 ----
    try:
        ho = validate.holdout(fn, M_, D, split_ratio=split_ratio, **bt)
        if ho:
            out["holdout"] = {
                "split_date": ho.get("split_date"),
                "n_is": ho.get("n_is"),
                "n_oos": ho.get("n_oos"),
                "is": ho.get("is", {}),
                "oos": ho.get("oos", {}),
                "degradation": ho.get("degradation", {}),
            }
    except Exception as exc:            # 样本外切分失败不得影响主结果
        out["holdout_error"] = str(exc)

    return out


def universe_availability(data_dir: str, window: str = "A") -> List[Dict]:
    """每个标的在给定窗口内的可投资状态（用于面板提示）。"""
    series = engine.load_series(data_dir=data_dir)
    if not series:
        return []
    dates = engine.trading_dates(series)
    mat = engine.align(series, dates)
    D, M_ = W.slice_window(dates, mat, window)
    out: List[Dict] = []
    for code, name, cls, _y in engine.UNIVERSE:
        col = M_.get(code)
        listed = bool(col) and col[0] is not None and col[0] > 0
        first = None
        if col:
            for i, v in enumerate(col):
                if v is not None and v > 0:
                    first = D[i]
                    break
        out.append({"code": code, "name": name, "class": cls,
                    "listed_at_start": listed, "first_date": first,
                    "has_data": bool(col) and any(
                        v is not None and v > 0 for v in col)})
    return out
