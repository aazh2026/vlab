# -*- coding: utf-8 -*-
"""房产模块 / Property module —— "持币 vs 持房" 对比。

这个模块回答一个具体问题：**现在这个价位买房，和把钱拿在手里买理财，
哪一个更划算？**

诚实性约束（重要）
==================
本模块**不接入任何房���挂牌数据**。挂牌价是卖方报价，不是成交价，
拿它算收益是最常见的自欺。真实决策需要的是：

* 近 6 个月**网签成交**价（同小区、同面积段）
* **银行预审**给出的实际可贷额度与利率
* **税费**核定（契税、增值税及附加、个税、中介费）
* **贷款**预审批结果（房龄是否影响年限与成数）

这些**必须由使用者自己填进来**（见 ``ASSUMPTIONS``）。本模块提供的是
**计算框架**和**敏感性分析**：结论必须在合理参数区间内都成立，
才算成立。

所以本模块的输出**不是**"买房能赚 X%"，而是三件事：

1. 在给定假设下，两条净值曲线的**差额**随时间怎么走；
2. **盈亏平衡点**——房价要跌多少、租金要涨到多少，"持房"才不亏；
3. **敏感性网格**——关键假设变动时，结论会不会翻转。

所有数字都是**假设下的推演**，不是对市场的预测。

口径约定
========
* 所有金额单位为**元**，比率一律用**小数**（0.018 = 1.8%），
  与 ``vlab.metrics`` 保持一致；前端用 ``pctRaw()`` 展示已是百分数的值。
* 持仓按**月**计息与摊还：中国房贷按月还款，租金也按月收。
* "持币"侧的资金收益率由调用方给定（默认货币基金 1.8% 年化，
  即 ``vlab.engine.MONEY_MARKET_APY``）。
"""
from __future__ import annotations

import calendar
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# 默认假设（**全部是占位值，必须用核验后的数字替换**）
# --------------------------------------------------------------------------
ASSUMPTIONS: Dict = {
    "name_zh": "上海田林十一村",
    "name_en": "Tianlin Shiyi Village, Shanghai",

    # --- 标的 ---
    "area_sqm": 60.0,            # 建筑面积 m²
    "price_per_sqm": 90000.0,    # **待核验**成交单价 元/m²

    # --- 买入成本 ---
    "down_ratio": 0.35,          # 首付比例
    "mortgage_rate": 0.030,      # 年利率（商贷）**待银行预审**
    "mortgage_years": 30,        # 贷款年限
    "deed_tax": 0.01,            # 契税（首套 ≤140㎡）
    "agency_fee": 0.02,          # 中介费
    "other_buy_tax": 0.005,      # 评估/登记等杂费

    # --- 持有成本 ---
    "mgmt_fee_per_sqm_month": 2.0,   # 物业费 元/m²/月
    "rent_tax_rate": 0.04,           # 个人出租综合税费（房产税等）
    "vacancy_rate": 0.05,            # 空置 + 维修损耗
    "sell_cost_rate": 0.05,          # 卖出端税费（增值税及附加+中介+个税）

    # --- 租金 ---
    "monthly_rent": 6000.0,      # **待核验**近 6 个月实际签约租金 元/月

    # --- 现金侧 ---
    "cash_apy": 0.018,           # 持币侧年化（货币基金）
}

#: 结论在多少年内判定为"未定论"（房产买卖有交易成本，期太短没有意义）
DEFAULT_HORIZON_YEARS = 3


# --------------------------------------------------------------------------
# 基础数学
# --------------------------------------------------------------------------
def month_grid(start: str, end: str) -> List[str]:
    """生成 ``["YYYY-MM", ...]`` 的连续月序列（含首尾）。

    ``start`` / ``end`` 为 ``YYYY-MM-DD``。
    """
    sy, sm = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out: List[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def months_between(start: str, end: str) -> int:
    """两个 ``YYYY-MM-DD`` 之间的月数（含首尾月，至少为 1）。"""
    months = month_grid(start, end)
    return max(len(months), 1)


def mortgage_payment(principal: float, annual_rate: float, years: int) -> float:
    """等额本息月供。

    ``M = P · r(1+r)^n / ((1+r)^n − 1)``，``r`` 为月利率。
    利率为 0 时退化为等额本金（此时月供 = P/n + 利息）。
    """
    n = max(int(years * 12), 1)
    r = annual_rate / 12.0
    if r <= 0:
        return principal / n
    f = (1.0 + r) ** n
    return principal * r * f / (f - 1.0)


def amortization(principal: float, annual_rate: float, years: int) -> List[Dict]:
    """逐月摊还表。

    返回每期 ``{month, payment, interest, principal, balance}``，
    ``month`` 从 1 开始。末期余额精确归零（不做浮点尾差）。
    """
    n = max(int(years * 12), 1)
    r = annual_rate / 12.0
    pay = mortgage_payment(principal, annual_rate, years)
    bal = principal
    rows: List[Dict] = []
    for i in range(1, n + 1):
        interest = bal * r
        prin = pay - interest
        if i == n or prin > bal:          # 末期：把余额一次性还清
            prin = bal
            pay = prin + interest
        bal = max(bal - prin, 0.0)
        rows.append({
            "month": i, "payment": pay, "interest": interest,
            "principal": prin, "balance": bal,
        })
    return rows


def property_value_path(p0: float, annual_growth: float,
                        months: Sequence[str], start: str) -> List[float]:
    """按年化增长率 ``annual_growth`` 生成逐月房价路径。

    采用**按月复利**（等价于年化率下的月度复利），而非简单年化线性外推。
    """
    r = (1.0 + annual_growth) ** (1.0 / 12.0) - 1.0
    # 从 start 到该月已经过去的整月数（start 当月记为 0）
    y0, m0 = int(start[:4]), int(start[5:7])
    out: List[float] = []
    for mkey in months:
        my, mm = int(mkey[:4]), int(mkey[5:7])
        k = (my - y0) * 12 + (mm - m0)
        out.append(p0 * (1.0 + r) ** k)
    return out


# --------------------------------------------------------------------------
# 核心：持币 vs 持房
# --------------------------------------------------------------------------
def compare(
    months: Sequence[str],
    start: str,
    p0: float,
    monthly_rent: float,
    a: Optional[Dict] = None,
    cash_monthly_returns: Optional[Sequence[float]] = None,
    price_growth: float = 0.02,
    _solve: bool = True,
) -> Dict:
    """在给定月份轴上对比"持币"与"持房"两条净值曲线。

    Parameters
    ----------
    months:
        月份轴 ``["YYYY-MM", ...]``。
    start:
        起始日期 ``YYYY-MM-DD``，用于计算房价路径的复利起点。
    p0:
        房屋总价（元）。
    monthly_rent:
        月租金（元）。
    a:
        假设字典，默认 :data:`ASSUMPTIONS`。
    cash_monthly_returns:
        持币侧的逐月收益率序列（**小数**，如 0.014 表示 1.4%）。
        ``None`` 时使用固定年化 ``a["cash_apy"]``。
    price_growth:
        房价年化涨幅假设（默认 2%）。

    Returns
    -------
    dict，含两条曲线、关键指标与盈亏平衡点。
    """
    a = dict(ASSUMPTIONS if a is None else a)
    n = len(months)
    if n < 2:
        raise ValueError("months 至少需要 2 个月")

    area = float(a["area_sqm"])
    loan = p0 * (1.0 - float(a["down_ratio"]))
    down = p0 - loan
    buy_cost = p0 * (float(a["deed_tax"]) + float(a["agency_fee"]) +
                     float(a["other_buy_tax"]))

    amort = amortization(loan, float(a["mortgage_rate"]),
                         int(a["mortgage_years"]))
    pay = amort[0]["payment"] if amort else 0.0

    # 持币侧初始资金 = 首付 + 买入税费（与持房初始现金支出完全一致）
    cash0 = down + buy_cost

    mgmt = float(a["mgmt_fee_per_sqm_month"]) * area
    rent_tax_rate = float(a["rent_tax_rate"])
    vacancy = float(a["vacancy_rate"])

    # 房价路径
    vals = property_value_path(p0, price_growth, months, start)

    cash_series: List[float] = []
    house_equity: List[float] = []
    cash_flow_accum: List[float] = []   # 房租 - 月供 - 持有成本 的累计（已复利滚存）
    cashflow = 0.0
    cash = cash0
    rate_m = float(a["cash_apy"]) / 12.0

    for i in range(n):
        # 第 0 期是"起点"：此刻刚付完首付与税费，尚未经过任何一个月。
        # 因此 cash_series[0] 必须等于现金投入额本身，
        # house_equity[0] 必须等于 房屋市值 - 贷款。
        if i > 0:
            # 现金侧收益：给定逐月收益率序列时用它，否则按固定年化。
            if cash_monthly_returns is not None:
                mret = cash_monthly_returns[i - 1] if (i - 1) < len(cash_monthly_returns) else 0.0
                cash *= (1.0 + mret)
            else:
                cash *= (1.0 + rate_m)
            cashflow *= (1.0 + rate_m)

            if i - 1 < len(amort):
                payment = amort[i - 1]["payment"]
                loan_balance = amort[i - 1]["balance"]
            else:
                payment = 0.0
                loan_balance = 0.0
            # 净现金流：租金 - 出租税费 - 空置损耗 - 物业费 - 月供
            net = (monthly_rent * (1.0 - rent_tax_rate) * (1.0 - vacancy)
                   - mgmt - payment)
            cashflow += net
        else:
            loan_balance = loan

        cash_series.append(cash)
        cash_flow_accum.append(cashflow)
        # 持房总财富 = 房屋市值 - 剩余贷款 + 累计净现金流
        house_equity.append(vals[i] - loan_balance + cashflow)

    diff = [h - c for h, c in zip(house_equity, cash_series)]

    # ---- 盈亏平衡分析 ----
    total_pay = sum(r["payment"] for r in amort)
    total_interest = sum(r["interest"] for r in amort)

    # 求解器内部会再次调用 compare()，必须关闭嵌套求解，否则无限递归。
    breakeven_rent = None
    breakeven_growth = None
    price_drop_to_breakeven = None

    # 静态租售比与"负 carry"判定
    gross_rent_yield = monthly_rent * 12.0 / p0 if p0 else 0.0
    net_rent_yield = gross_rent_yield * (1.0 - rent_tax_rate) * (1.0 - vacancy)
    carry = net_rent_yield - float(a["mortgage_rate"])

    if _solve:
        # 1) 保本租金：使"持房"终值 = "持币"终值所需的月租金（数值求解）
        breakeven_rent = _solve_breakeven_rent(
            months, start, p0, a, cash_monthly_returns, price_growth)

        # 2) 保本房价涨幅：房价年化涨幅降到多少时终值持平
        breakeven_growth = _solve_breakeven_growth(
            months, start, p0, monthly_rent, a, cash_monthly_returns)

        # 3) 房价一次性下跌多少才持平
        if diff[-1] < 0:
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = (lo + hi) / 2.0
                r = compare(months, start, p0 * (1.0 - mid), monthly_rent, a,
                            cash_monthly_returns, price_growth, _solve=False)
                if r["final_diff"] < 0:
                    lo = mid
                else:
                    hi = mid
            price_drop_to_breakeven = (lo + hi) / 2.0

    return {
        "assumptions": a,
        "scenario": "money_market",
        "months": list(months),
        "months_count": n,
        "start": start,
        "end": f"{months[-1]}-01",
        "price0": p0,
        "price_path": vals,
        "down_payment": down,
        "buy_cost": buy_cost,
        "loan": loan,
        "monthly_payment": pay,
        "monthly_rent": monthly_rent,
        "mgmt_fee": mgmt,
        "cash_series": cash_series,
        "house_equity": house_equity,
        "diff": diff,
        "final_cash": cash_series[-1],
        "final_house": house_equity[-1],
        "final_diff": diff[-1],
        "total_interest_paid": total_interest,
        "total_paid": total_pay,
        "gross_rent_yield": gross_rent_yield,
        "net_rent_yield": net_rent_yield,
        "carry": carry,
        "breakeven_rent": breakeven_rent,
        "breakeven_price_growth": breakeven_growth,
        "price_drop_to_breakeven": price_drop_to_breakeven,
        "price_growth": price_growth,
        "note_zh": "本结果基于未核验的占位假设，仅用于框架演示；"
                   "不构成投资建议，不可直接作为决策依据。",
        "note_en": "Based on unverified placeholder assumptions; framework demo only. "
                   "Not investment advice and not decision-grade.",
    }


def _solve_breakeven_rent(months, start, p0, a, cash_monthly_returns,
                           price_growth) -> Optional[float]:
    """求使终值持平的月租金（二分法）。不存在解时返回 None。"""
    def f(rent: float) -> float:
        r = compare(months, start, p0, rent, a, cash_monthly_returns,
                    price_growth, _solve=False)
        return r["final_diff"]

    lo, hi = 0.0, p0 * 0.02        # 上界：租金 = 总价的 2%/月，绰绰有余
    if f(hi) < 0:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2.0
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _solve_breakeven_growth(months, start, p0, monthly_rent, a,
                             cash_monthly_returns) -> Optional[float]:
    """求使终值持平的房价年化涨幅（二分法）。"""
    def f(g: float) -> float:
        r = compare(months, start, p0, monthly_rent, a, cash_monthly_returns, g,
                    _solve=False)
        return r["final_diff"]

    lo, hi = -0.30, 0.30
    if f(lo) > 0:
        return None
    if f(hi) < 0:
        return None
    for _ in range(50):
        mid = (lo + hi) / 2.0
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# --------------------------------------------------------------------------
# 敏感性分析
# --------------------------------------------------------------------------
def sensitivity(
    months: Sequence[str],
    start: str,
    a: Optional[Dict] = None,
    cash_monthly_returns: Optional[Sequence[float]] = None,
    price_growth: float = 0.02,
    rents: Optional[Sequence[float]] = None,
    prices: Optional[Sequence[float]] = None,
    rates: Optional[Sequence[float]] = None,
) -> Dict:
    """三因子敏感性网格：房价 × 租金 × 利率。

    输出每个组合下的 ``final_diff``（持房终值 − 持币终值）。
    结论只有在**整个网格符号一致**时才算稳健。
    """
    a = dict(ASSUMPTIONS if a is None else a)
    p0 = float(a["price_per_sqm"]) * float(a["area_sqm"])
    rents = list(rents) if rents else [0.8, 0.9, 1.0, 1.1, 1.2]
    prices = list(prices) if prices else [0.8, 0.9, 1.0, 1.1, 1.2]
    rates = list(rates) if rates else [0.025, 0.030, 0.035]

    base_rent = float(a["monthly_rent"])
    cells: List[Dict] = []
    for pr in prices:
        for rt in rents:
            row: Dict = {"price_mult": pr, "rent_mult": rt, "cells": []}
            for rate in rates:
                aa = dict(a)
                aa["mortgage_rate"] = rate
                res = compare(months, start, p0 * pr, base_rent * rt, aa,
                              cash_monthly_returns, price_growth, _solve=False)
                row["cells"].append({
                    "rate": rate,
                    "final_diff": res["final_diff"],
                    "final_cash": res["final_cash"],
                    "final_house": res["final_house"],
                    "breakeven_rent": res["breakeven_rent"],
                    "net_rent_yield": res["net_rent_yield"],
                    "carry": res["carry"],
                })
            cells.append(row)

    vals = [c["final_diff"] for row in cells for c in row["cells"]]
    same_sign = all(v > 0 for v in vals) or all(v < 0 for v in vals)
    return {
        "grid": cells,
        "prices": prices,
        "rents": rents,
        "rates": rates,
        "price0": p0,
        "base_rent": base_rent,
        "all_same_sign": same_sign,
        "sign_positive_count": sum(1 for v in vals if v > 0),
        "total": len(vals),
        "min_diff": min(vals) if vals else 0.0,
        "max_diff": max(vals) if vals else 0.0,
    }


def monthly_returns_from_equity(equity: Sequence[float],
                                 dates: Sequence[str]) -> List[float]:
    """把日频净值序列转成逐月收益率（取每月最后一个有数据的交易日）。

    用于把 vlab 的策略曲线接入"持币"侧。
    """
    if not equity or not dates:
        return []
    last_of_month: Dict[str, int] = {}
    for i, d in enumerate(dates):
        last_of_month[d[:7]] = i
    keys = sorted(last_of_month)
    out: List[float] = []
    prev: Optional[float] = None
    for k in keys:
        cur = equity[last_of_month[k]]
        if prev is None:
            # 首月没有"上一个月"可比较，定义为 0（基期）。
            out.append(0.0)
        else:
            out.append((cur / prev - 1.0) if prev > 0 else 0.0)
        prev = cur
    return out


def average_monthly_return(equity: Sequence[float],
                           dates: Sequence[str]) -> float:
    """日频净值序列的平均月收益率（算术平均，逐月）。

    **这是外推用的常数**，不是预测。把它用于未来投影属于
    "用历史均值代表未来"，在本项目的诚实性约束下必须显式标注。
    """
    mr = monthly_returns_from_equity(equity, dates)
    if len(mr) < 2:
        return 0.0
    return sum(mr[1:]) / len(mr[1:])


def build_property_section(
    start: str,
    horizon_years: int = DEFAULT_HORIZON_YEARS,
    a: Optional[Dict] = None,
    price_growth: float = 0.02,
    cash_monthly_returns: Optional[Sequence[float]] = None,
    cash_scenario_label: str = "货币基金 1.8% 年化",
    cash_scenario_note: str = "",
) -> Dict:
    """构建面板用的房产对比区块。

    Parameters
    ----------
    start:
        投影起始日 ``YYYY-MM-DD``。
    horizon_years:
        投影年数。
    cash_monthly_returns:
        持币侧逐月收益率；``None`` 则用 ``a["cash_apy"]`` 固定年化。
    """
    a = dict(ASSUMPTIONS if a is None else a)
    p0 = float(a["price_per_sqm"]) * float(a["area_sqm"])
    end_year = int(start[:4]) + horizon_years
    end = f"{end_year:04d}-{start[5:7]}-{start[8:10]}"
    months = month_grid(start, end)

    res = compare(months, start, p0, float(a["monthly_rent"]), a,
                  cash_monthly_returns, price_growth)
    res["scenario_label"] = cash_scenario_label
    res["scenario_note"] = cash_scenario_note
    res["horizon_years"] = horizon_years

    # 曲线降采样（与策略曲线保持同样的点数上限）
    n = len(res["months"])
    step = max(1, n // 240)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    res["downsample_idx"] = idx
    res["months_downsampled"] = [res["months"][i] for i in idx]
    res["cash_downsampled"] = [res["cash_series"][i] for i in idx]
    res["house_downsampled"] = [res["house_equity"][i] for i in idx]
    res["diff_downsampled"] = [res["diff"][i] for i in idx]
    res["price_downsampled"] = [res["price_path"][i] for i in idx]

    sens = sensitivity(months, start, a, cash_monthly_returns, price_growth)
    res["sensitivity"] = sens
    return res
