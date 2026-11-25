# -*- coding: utf-8 -*-
"""绩效指标计算 / Performance metrics.

所有函数均为纯函数，无状态，便于单元测试与复用。

约定
----
* 所有 ``rate`` 类指标返回**小数**（0.0838 表示 8.38%）。
* 交易日数按 A 股惯例取 244 天/年。
* 无风险利率默认 1.8%（中国货币 ETF 附近），可通过参数覆盖。
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

TRADING_DAYS = 244
DEFAULT_RF = 0.018


def _clean(equity: Sequence[float]) -> List[float]:
    """去掉非正与缺失值，避免除零产生 inf。"""
    return [float(x) for x in equity if x is not None and x > 0]


def daily_returns(equity: Sequence[float]) -> List[float]:
    """简单日收益率序列。"""
    e = [float(x) for x in equity]
    out = []
    for i in range(1, len(e)):
        if e[i - 1] > 0:
            out.append(e[i] / e[i - 1] - 1.0)
    return out


def cagr(equity: Sequence[float], periods_per_year: int = TRADING_DAYS) -> float:
    """复合年化收益率。

    ``equity`` 为净值序列，第一个元素是起点，最后一个是终点。
    """
    e = _clean(equity)
    if len(e) < 2:
        return 0.0
    years = (len(e) - 1) / float(periods_per_year)
    if years <= 0 or e[0] <= 0:
        return 0.0
    return (e[-1] / e[0]) ** (1.0 / years) - 1.0


def volatility(returns: Iterable[float], periods_per_year: int = TRADING_DAYS) -> float:
    """年化波动率（样本标准差）。"""
    r = list(returns)
    if len(r) < 2:
        return 0.0
    mu = sum(r) / len(r)
    var = sum((x - mu) ** 2 for x in r) / (len(r) - 1)
    return math.sqrt(var) * math.sqrt(periods_per_year)


def sharpe(cagr_value: float, vol: float, rf: float = DEFAULT_RF) -> float:
    """夏普比率。波动率为 0 时返回 0。"""
    if vol <= 0:
        return 0.0
    return (cagr_value - rf) / vol


def downside_deviation(returns: Iterable[float], periods_per_year: int = TRADING_DAYS) -> float:
    """下行标准差（只统计负收益）。"""
    dn = [x for x in returns if x < 0]
    if len(dn) < 2:
        return 0.0
    var = sum(x * x for x in dn) / (len(dn) - 1)
    return math.sqrt(var) * math.sqrt(periods_per_year)


def sortino(cagr_value: float, dvol: float, rf: float = DEFAULT_RF) -> float:
    """索提诺比率。"""
    if dvol <= 0:
        return 0.0
    return (cagr_value - rf) / dvol


def max_drawdown(equity: Sequence[float]) -> Tuple[float, Optional[int]]:
    """最大回撤及其发生位置（索引）。

    返回 ``(maxdd, peak_index)``，``maxdd`` 为负小数。
    """
    e = [float(x) for x in equity]
    if not e:
        return 0.0, None
    peak = e[0]
    mdd = 0.0
    mdd_peak_idx = None
    cur_peak_idx = 0
    for i, v in enumerate(e):
        if v > peak:
            peak = v
            cur_peak_idx = i
        dd = v / peak - 1.0 if peak > 0 else 0.0
        if dd < mdd:
            mdd = dd
            mdd_peak_idx = cur_peak_idx
    return mdd, mdd_peak_idx


def drawdown_series(equity: Sequence[float]) -> List[float]:
    """逐点回撤序列（相对历史最高净值）。"""
    e = [float(x) for x in equity]
    out: List[float] = []
    peak = None
    for v in e:
        peak = v if peak is None else max(peak, v)
        out.append(v / peak - 1.0 if peak > 0 else 0.0)
    return out


def drawdown_periods(
    equity: Sequence[float],
    dates: Optional[Sequence[str]] = None,
    top: int = 5,
) -> List[Dict]:
    """定位最大的若干段回撤区间。

    每段包含 ``peak_date`` / ``trough_date`` / ``depth`` / ``recovery_date``
    / ``length_days``。未收复的底部回撤 ``recovery_date`` 为 ``None``。
    """
    e = [float(x) for x in equity]
    n = len(e)
    if n < 2:
        return []

    # 找出所有"尚未收复前高"的极值区间
    periods: List[Dict] = []
    peak = e[0]
    peak_i = 0
    trough = e[0]
    trough_i = 0
    in_dd = False

    for i in range(1, n):
        if e[i] >= peak:
            if in_dd:
                periods.append(_mk_period(peak_i, trough_i, i, dates, e))
                in_dd = False
            peak = e[i]
            peak_i = i
            trough = e[i]
            trough_i = i
        else:
            in_dd = True
            if e[i] < trough:
                trough = e[i]
                trough_i = i
    if in_dd:
        periods.append(_mk_period(peak_i, trough_i, None, dates, e))

    # depth 必须在排序前算好，否则会按 0.0 排序并截断出"最浅的若干段"
    for p in periods:
        pv = e[p["_peak_i"]]
        tv = e[p["_trough_i"]]
        p["depth"] = (tv / pv - 1.0) if pv > 0 else 0.0
        p.pop("_peak_i", None)
        p.pop("_trough_i", None)
    periods.sort(key=lambda p: p["depth"])
    return periods[:top]


def _mk_period(peak_i: int, trough_i: int, rec_i: Optional[int],
               dates: Optional[Sequence[str]], equity: Sequence[float]) -> Dict:
    def dt(i: Optional[int]) -> Optional[str]:
        if i is None or dates is None:
            return None
        return dates[i] if 0 <= i < len(dates) else None

    return {
        "peak_date": dt(peak_i),
        "trough_date": dt(trough_i),
        "recovery_date": dt(rec_i),
        "depth": 0.0,          # 稍后由调用方按 equity 计算
        "length_days": (rec_i - peak_i) if rec_i is not None else (trough_i - peak_i),
        "_peak_i": peak_i,
        "_trough_i": trough_i,
    }


def calmar(cagr_value: float, maxdd: float) -> float:
    """卡玛比率 = 年化收益 / |最大回撤|。"""
    if maxdd >= 0:
        return 0.0
    return cagr_value / abs(maxdd)


def yearly_returns(equity: Sequence[float], dates: Sequence[str]) -> Dict[str, float]:
    """按自然年切分的收益率。

    语义
    ----
    * 序列第一年：用该年**第一个观测值**作为基准。因此第一年的收益
      不包含首日之前的那一段（没有信息就无法计算）。
    * 后续年份：用**上一年的最后一个观测值**作为基准，
      所以 ``year[Y] == equity[end of Y] / equity[end of Y-1] - 1``。
    """
    buckets: Dict[str, List[float]] = {}
    for i, d in enumerate(dates):
        buckets.setdefault(d[:4], []).append(float(equity[i]))
    out: Dict[str, float] = {}
    prev_close = None
    for y in sorted(buckets):
        vals = buckets[y]
        base = vals[0] if prev_close is None else prev_close
        out[y] = (vals[-1] / base - 1.0) if base > 0 else 0.0
        prev_close = vals[-1]
    return out


def summarize(
    equity: Sequence[float],
    dates: Sequence[str],
    rf: float = DEFAULT_RF,
) -> Dict:
    """一次性算出全部常用指标。

    这是本项目对外的主要指标出口，面板与 CLI 都以它为准。
    """
    e = [float(x) for x in equity]
    r = daily_returns(e)
    c = cagr(e)
    v = volatility(r)
    mdd, mdd_peak_idx = max_drawdown(e)
    mdd_date = dates[mdd_peak_idx] if (mdd_peak_idx is not None and dates) else None
    dn = downside_deviation(r)
    y = yearly_returns(e, dates)
    neg_years = [k for k, v_ in y.items() if v_ < 0]
    return {
        "total": (e[-1] / e[0] - 1.0) if e and e[0] > 0 else 0.0,
        "cagr": c,
        "vol": v,
        "sharpe": sharpe(c, v, rf),
        "sortino": sortino(c, dn, rf),
        "maxdd": mdd,
        "maxdd_date": mdd_date,
        "calmar": calmar(c, mdd),
        "win_rate": (sum(1 for x in r if x > 0) / len(r)) if r else 0.0,
        "days": max(len(e) - 1, 0),
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
        "yearly": y,
        "loss_years": neg_years,
    }
