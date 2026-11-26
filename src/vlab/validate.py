# -*- coding: utf-8 -*-
"""自定义策略的有效性检验 / Validity checks for custom strategies.

为什么需要这个模块
------------------
引擎能跑任意策略，但"跑出数字"不等于"数字有效"。一个自定义策略在
**样本内**跑出 25% 年化，可能只是因为参数挑得刚好适合那段历史。
真正要回答的问题是：

    这个策略的有效性，扛不扛得住一段它没见过的历史？

本模块提供三种检验，按诚实度从低到高排列：

1. :func:`holdout` —— 单次样本内/样本外切分。看衰减。
2. :func:`parameter_sweep` —— 参数网格搜索 + 样本外验证。
   关键输出是 **overfit gap**：样本内最优参数到了样本外还剩多少。
   同时给出"先知"（直接用样本外最优参数）的成绩作为对照 ——
   两者差距越大，说明样本内挑选越可能只是运气。
3. :func:`walk_forward` —— 滚动前推（walk-forward）。把历史切成若干段，
   每段用之前的数据选参数、在这段上检验，把所有样本外段拼成一条净值。
   这是最接近"真实使用"的检验方式。

统一约定
--------
* **预热（warmup）**：策略函数只能看到"当前日及之前"的数据（见
  ``vlab.guard``）。因此需要回看窗口的策略（如 60 日动量）必须在
  **更早的起点**上跑，然后对净值曲线取子集。本模块的所有函数都在
  **完整历史上运行**，再按日期切分指标 —— 这样预热天然可用。
* **样本外段不重置资金**：连续运行后取子集，保留真实路径依赖。
  这与"每次重新给 100 万"不同，但后者会人为抹掉策略的历史包袱。
  两种口径都列在结果里，由使用者选择。
* **起点不可用即跳过**：若某段起始日早于标的上市日，该段会被引擎
  按"未上市资产留在现金"处理，而不是穿越时空。

本模块不产生任何收益承诺，所有输出都必须连同免责声明一起呈现。
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import engine
from .metrics import summarize

#: 权重函数签名
WeightsFn = Callable[[str, Dict, Sequence, int], Dict[str, float]]

DEFAULT_BT = {
    "start_cash": 1_000_000.0,
    "fee_bps": engine.DEFAULT_FEE_BPS,
    "slip_bps": engine.DEFAULT_SLIP_BPS,
}


# --------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------
def _slice_curve(curve: List[Dict], start: Optional[str],
                  end: Optional[str]) -> List[Dict]:
    out = []
    for c in curve:
        d = c["d"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        out.append(c)
    return out


def _metrics(curve: List[Dict]) -> Dict:
    if len(curve) < 2:
        return {}
    return summarize([c["eq"] for c in curve], [c["d"] for c in curve])


def _first_index_at_or_after(curve: List[Dict], d0: str) -> int:
    for i, c in enumerate(curve):
        if c["d"] >= d0:
            return i
    return len(curve)


def _run(weights_fn: WeightsFn, mat: Dict, dates: Sequence[str],
         bt: Dict) -> List[Dict]:
    res = engine.backtest(weights_fn, mat, dates, **bt)
    return res["curve"]


def _metric_of(curve: List[Dict], key: str) -> float:
    m = _metrics(curve)
    return float(m.get(key, 0.0) or 0.0)


# --------------------------------------------------------------------------
# 1) 单次样本内 / 样本外切分
# --------------------------------------------------------------------------
def holdout(
    weights_fn: WeightsFn,
    mat: Dict,
    dates: Sequence[str],
    split_ratio: float = 0.7,
    split_date: Optional[str] = None,
    **bt,
) -> Dict:
    """切一段历史做样本外检验。

    参数
    ----
    split_ratio
        样本内占比（0~1）。``split_date`` 存在时优先使用它。
    split_date
        样本外的第一天，格式 ``YYYY-MM-DD``。

    返回
    ----
    ``{"split_date":..., "is": {...}, "oos": {...}, "degradation": {...},
    "oos_curve": [...]}``
    """
    bt = {**DEFAULT_BT, **bt}
    curve = _run(weights_fn, mat, dates, bt)
    if not curve:
        return {}

    if split_date:
        idx = _first_index_at_or_after(curve, split_date)
        cut = curve[idx]["d"] if idx < len(curve) else curve[-1]["d"]
    else:
        idx = max(1, int(len(curve) * split_ratio))
        idx = min(idx, len(curve) - 1)
        cut = curve[idx]["d"]

    is_curve = curve[:idx]
    oos_curve = curve[idx:]
    m_is = _metrics(is_curve)
    m_oos = _metrics(oos_curve)

    deg = {}
    for k in ("cagr", "sharpe", "maxdd", "calmar"):
        if k in m_is and k in m_oos:
            deg[k] = m_oos[k] - m_is[k]

    return {
        "split_date": cut,
        "is": m_is,
        "oos": m_oos,
        "degradation": deg,
        "is_curve": is_curve,
        "oos_curve": oos_curve,
        "n_is": len(is_curve),
        "n_oos": len(oos_curve),
    }


# --------------------------------------------------------------------------
# 2) 参数网格搜索 + 样本外验证
# --------------------------------------------------------------------------
def parameter_sweep(
    make_fn: Callable[[dict], WeightsFn],
    grid: Sequence[Dict],
    mat: Dict,
    dates: Sequence[str],
    split_ratio: float = 0.7,
    split_date: Optional[str] = None,
    metric: str = "sharpe",
    **bt,
) -> Dict:
    """参数网格搜索，样本内选优后在样本外检验。

    参数
    ----
    make_fn
        由**参数字典**构造权重函数的工厂：``make_fn({"lookback": 60})``。
        如果你的工厂是按关键字定义的，用 lambda 包一层：
        ``lambda p: make_mom(**p)``。
    grid
        参数字典列表。每个字典是一组参数。
    metric
        样本内选优所用的指标，默认 ``sharpe``。

    返回
    ----
    关键字段：

    ``selected``
        样本内最优的那组参数。
    ``selected_oos``
        这组参数在样本外的成绩。
    ``oracle_oos``
        **先知基线** —— 直接用样本外最优参数时的成绩。它是搜索偏差
        的上界：如果 ``oracle_oos`` 明显高于 ``selected_oos``，
        说明"样本内挑出来的最好"其实只是运气好。
    ``overfit_gap``
        ``selected_oos[metric] - oracle_oos[metric]``，越大越可疑。
    ``oos_winners``
        网格里有多少组在样本外指标为正 —— 网格整体是否稳健。
    """
    bt = {**DEFAULT_BT, **bt}
    curve_cache: Dict[str, List[Dict]] = {}

    rows = []
    for params in grid:
        key = repr(sorted(params.items()))
        fn = make_fn(params)
        curve = _run(fn, mat, dates, bt)
        curve_cache[key] = curve

        if split_date:
            idx = _first_index_at_or_after(curve, split_date)
        else:
            idx = max(1, min(int(len(curve) * split_ratio), len(curve) - 1))
        is_curve = curve[:idx]
        oos_curve = curve[idx:]
        m_is = _metrics(is_curve)
        m_oos = _metrics(oos_curve)
        rows.append({
            "params": dict(params),
            "is": m_is,
            "oos": m_oos,
            "is_metric": m_is.get(metric, 0.0),
            "oos_metric": m_oos.get(metric, 0.0),
            "key": key,
        })

    if not rows:
        return {}

    # 样本内最优
    best = max(rows, key=lambda r: r["is_metric"])
    # 先知：直接用样本外最优参数
    oracle = max(rows, key=lambda r: r["oos_metric"])

    winners = sum(1 for r in rows if r["oos_metric"] > 0)

    return {
        "metric": metric,
        "n_combos": len(rows),
        "rows": rows,
        "selected": best["params"],
        "selected_is": best["is"],
        "selected_oos": best["oos"],
        "selected_is_metric": best["is_metric"],
        "selected_oos_metric": best["oos_metric"],
        "oracle_params": oracle["params"],
        "oracle_oos": oracle["oos"],
        "oracle_oos_metric": oracle["oos_metric"],
        "overfit_gap": best["oos_metric"] - oracle["oos_metric"],
        "oos_winners": winners,
        "oos_positive_ratio": winners / len(rows),
        "split_date": best["is"].get("end") if best["is"] else None,
        "curve_of": lambda params: curve_cache[repr(sorted(params.items()))],
    }


# --------------------------------------------------------------------------
# 3) 滚动前推（walk-forward）
# --------------------------------------------------------------------------
def walk_forward(
    make_fn: Callable[[dict], WeightsFn],
    grid: Sequence[Dict],
    mat: Dict,
    dates: Sequence[str],
    n_folds: int = 4,
    metric: str = "sharpe",
    **bt,
) -> Dict:
    """滚动前推检验：每段用历史选参数，在**没见过的**下一段上检验。

    做法
    ----
    把完整历史切成 ``n_folds`` 段。第 ``k`` 段的样本内 = 第 0..k-1 段，
    样本外 = 第 k 段。每段用样本内挑参数、在该段上跑，然后把所有
    样本外段**拼成一条净值**。

    这条拼接出来的净值就是"一个从头到尾只用过当时可得信息"的策略
    的真实业绩 —— 最接近实盘的可得口径。

    诚实说明：拼接时每段起点资金不同，这里按"每段起点归一为 1.0"
    等权拼接，即假设每段独立建仓。它衡量的是**策略本身**，而不是
    一个连续账户的资金曲线。
    """
    bt = {**DEFAULT_BT, **bt}
    n = len(dates)
    if n < n_folds * 2 or not grid:
        return {}

    # 把历史切成 n_folds + 1 段：第 0 段只作样本内种子，
    # 后面 n_folds 段各自是一个"样本外段"。这样正好得到 n_folds 次前推检验。
    n_seg = n_folds + 1
    fold_size = n // n_seg
    if fold_size < 2:
        return {}
    folds: List[Dict] = []
    composite: List[Dict] = []
    composite_dates: List[str] = []

    for k in range(1, n_folds + 1):
        is_end = fold_size * k
        oos_start = is_end
        oos_end = min(fold_size * (k + 1), n)
        if oos_start >= n or oos_end - oos_start < 2:
            continue

        is_dates = dates[:is_end]
        oos_dates = dates[oos_start:oos_end]

        best = None
        for params in grid:
            fn = make_fn(params)
            curve = _run(fn, mat, is_dates, bt)
            m = _metrics(curve)
            v = m.get(metric, 0.0)
            if best is None or v > best[0]:
                best = (v, params)

        if best is None:
            continue
        chosen = best[1]
        fn = make_fn(chosen)
        oos_curve = _run(fn, mat, oos_dates, bt)
        m_oos = _metrics(oos_curve)

        folds.append({
            "fold": k,
            "is_start": dates[0],
            "is_end": dates[is_end - 1],
            "oos_start": dates[oos_start],
            "oos_end": dates[oos_end - 1],
            "chosen_params": dict(chosen),
            "is_metric": best[0],
            "oos": m_oos,
            "oos_metric": m_oos.get(metric, 0.0),
        })

        # 等权拼接：每段起点归一为 1.0
        if oos_curve:
            base = oos_curve[0]["eq"]
            if base and base > 0:
                for c in oos_curve:
                    composite.append({"d": c["d"], "eq": c["eq"] / base})
                    composite_dates.append(c["d"])

    if not folds:
        return {}

    wf_metrics = _metrics(composite)
    return {
        "metric": metric,
        "n_folds": len(folds),
        "folds": folds,
        "walkforward_curve": composite,
        "walkforward_metrics": wf_metrics,
        "oos_winners": sum(1 for f in folds if f["oos_metric"] > 0),
        "params_chosen": [f["chosen_params"] for f in folds],
    }


# --------------------------------------------------------------------------
# 4) 一站式：拿到完整有效性报告
# --------------------------------------------------------------------------
def evaluate(
    weights_fn: WeightsFn,
    mat: Dict,
    dates: Sequence[str],
    split_ratio: float = 0.7,
    windows: Optional[Dict[str, Tuple[str, str]]] = None,
    **bt,
) -> Dict:
    """一次性产出自定义策略的有效性报告。

    ``windows`` 是 ``{key: (start, end)}``，用于在完整历史上按窗口
    （例如本项目的 A / B 两个口径）切片统计指标。
    """
    bt = {**DEFAULT_BT, **bt}
    curve = _run(weights_fn, mat, dates, bt)
    out: Dict = {
        "full": _metrics(curve),
        "curve": curve,
        "holdout": holdout(weights_fn, mat, dates,
                           split_ratio=split_ratio, **bt),
    }
    if windows:
        out["windows"] = {}
        for k, (s, e) in windows.items():
            out["windows"][k] = _metrics(_slice_curve(curve, s, e))
    return out
