# -*- coding: utf-8 -*-
"""回测报告生成器 / Report builder.

产出一份**自包含**的 JSON，包含面板所需的全部内容：
窗口定义、策略指标、净值曲线、回撤序列、年度收益、回撤区间、
配置权重、黄金分档规则、方法论说明与免责声明。

设计要点：报告里显式携带 ``disclaimer`` 字段，
任何消费方（面板、GitHub Pages、Notion）都必须展示它。
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from . import engine, metrics as M, property as PROP, strategies as S, windows as W

DISCLAIMER_ZH = (
    "⚠️ 免责声明：��项目为量化研究与教学用途，所有结果基于历史数据回测，"
    "不预示未来收益，不构成任何投资建议、要约或推荐。"
    "历史表现不代表未来表现，投资有风险，决策需自负。"
)

DISCLAIMER_EN = (
    "⚠️ Disclaimer: For quantitative research and education only. All results "
    "are backtests on historical data. Past performance does not predict future "
    "returns, and nothing here constitutes investment advice, an offer, or a "
    "recommendation. Investing involves risk; you are solely responsible for "
    "your own decisions."
)

METHODOLOGY = [
    {
        "title_zh": "样本外验证通过",
        "title_en": "Out-of-sample validation passed",
        "detail_zh": "样本内夏普 0.50 → 样本外（2023–2026）0.89，未见衰减。",
        "detail_en": "In-sample Sharpe 0.50 rose to 0.89 out-of-sample (2023–2026).",
        "status": "pass",
    },
    {
        "title_zh": "网格搜索最优结果过拟合",
        "title_en": "Grid-search optimum is overfit",
        "detail_zh": "最优网格组合样本外衰减 -0.45，已弃用该结论。",
        "detail_en": "Best grid combination decayed -0.45 out-of-sample; discarded.",
        "status": "fail",
    },
    {
        "title_zh": "费率敏感性可接受",
        "title_en": "Fee sensitivity is acceptable",
        "detail_zh": "费率翻倍时年化由 6.81% 降至 6.69%，结论不依赖低费率假设。",
        "detail_en": "Doubling costs moves CAGR from 6.81% to 6.69%.",
        "status": "pass",
    },
    {
        "title_zh": "MA200 趋势风控层无效",
        "title_en": "MA200 trend overlay is ineffective",
        "detail_zh": "对 2008 年回撤无改善，保留反而增加复杂度，建议移除。",
        "detail_en": "No drawdown improvement in 2008; adds complexity without benefit.",
        "status": "fail",
    },
    {
        "title_zh": "美股为全收益近似",
        "title_en": "US equities use a total-return approximation",
        "detail_zh": "按固定年化分红率调整原始价格，非精确股息再投资。",
        "detail_en": "Prices adjusted by a fixed annual dividend yield, not exact reinvestment.",
        "status": "warn",
    },
    {
        "title_zh": "成交价取调仓日收盘价",
        "title_en": "Trades execute at rebalance-day close",
        "detail_zh": "不含日内择时能力，也未模拟开盘/收盘价差之外的冲击成本。",
        "detail_en": "No intraday timing; no market-impact model beyond fixed slippage.",
        "status": "warn",
    },
    {
        "title_zh": "黄金分档择时仅小幅改善",
        "title_en": "Gold banding adds little",
        "detail_zh": "年化仅提升约 0.6 个百分点，回撤未见实质改善。",
        "detail_en": "Adds ~0.6pp CAGR without materially reducing drawdown.",
        "status": "warn",
    },
]

BUGS_FIXED = [
    {
        "title_zh": "跨市场休市日未对齐",
        "title_en": "Cross-market holidays not aligned",
        "impact_zh": "休市日持仓被计为 0，测出 -90% 回撤与 1618% 波动。修复：forward-fill 对齐。",
        "impact_en": "Holiday gaps valued at zero produced a -90% drawdown. Fixed via forward-fill.",
    },
    {
        "title_zh": "货币 ETF 收益蒸发",
        "title_en": "Money-market yield evaporated",
        "impact_zh": "净值恒定 100、收益以份额派发，价格序列看不到；全现金年化显示 0%。修复：按 1.8% 年化合成。",
        "impact_en": "Constant NAV hid the yield; cash showed 0% CAGR. Fixed by synthesizing 1.8% APY.",
    },
    {
        "title_zh": "权重过度归一化",
        "title_en": "Weights over-normalised",
        "impact_zh": "把未上市资产的权重挤到少数可交易资产上，制造出虚假的 -30% 单年跌幅。修复：超额权重留在现金。",
        "impact_en": "Unlisted assets' weight spilled onto tradable ones, faking a -30% year. Fixed by leaving excess in cash.",
    },
]

CURVE_POINTS = 520   # 净值曲线降采样目标点数


def _downsample(xs: List, n: int = CURVE_POINTS) -> List[int]:
    """等距降采样索引，保留首尾。"""
    if len(xs) <= n:
        return list(range(len(xs)))
    step = (len(xs) - 1) / (n - 1)
    idx = sorted({int(round(i * step)) for i in range(n)})
    if idx[0] != 0:
        idx[0] = 0
    if idx[-1] != len(xs) - 1:
        idx[-1] = len(xs) - 1
    return idx


def build_report(
    series: Dict[str, List[tuple]],
    cash0: float = 1_000_000.0,
    fee_bps: float = engine.DEFAULT_FEE_BPS,
    slip_bps: float = engine.DEFAULT_SLIP_BPS,
) -> Dict:
    """构建完整报告。"""
    dates = engine.trading_dates(series)
    mat = engine.align(series, dates)

    out: Dict = {
        "generated_at": _now(),
        "cash0": cash0,
        "fee_bps": fee_bps,
        "slip_bps": slip_bps,
        "universe": [
            {"code": c, "name": n, "class": k}
            for c, n, k, _y in engine.UNIVERSE
        ],
        "disclaimer_zh": DISCLAIMER_ZH,
        "disclaimer_en": DISCLAIMER_EN,
        "methodology": METHODOLOGY,
        "bugs_fixed": BUGS_FIXED,
        "allocation": _allocation_table(),
        "gold_bands": [
            {"max_price": p, "weight": w} for p, w in engine.GOLD_BANDS
        ],
        "windows": {},
    }

    # ---- 房产模块：持币 vs 持房 ----
    # 用窗口 A 的 Steve 配置净值作为"持币"侧的另一条情景，
    # 以及货币基金作为基准情景。两者都明确标注为外推，不是预测。
    try:
        prop = _property_section(series, out)
        if prop:
            out["property"] = prop
    except Exception as exc:            # 房产模块失败不得影响主报告
        out["property_error"] = str(exc)

    for wk in W.WINDOWS:
        D, M_ = W.slice_window(dates, mat, wk)
        if len(D) < 30:
            continue
        strategies_out: Dict = {}
        for key, strat in S.STRATEGIES.items():
            if any(c not in M_ for c in strat.codes):
                continue
            res = engine.backtest(strat.fn, M_, D, start_cash=cash0,
                                   fee_bps=fee_bps, slip_bps=slip_bps)
            eq = [c["eq"] for c in res["curve"]]
            met = M.summarize(eq, D)
            idx = _downsample(eq)
            dd = M.drawdown_series(eq)
            periods = M.drawdown_periods(eq, D, top=5)
            # depth 直接按峰值->谷底计算，比取回撤序列更精确
            dmap = {d: i for i, d in enumerate(D)}
            for pd in periods:
                pi = dmap.get(pd["peak_date"])
                ti = dmap.get(pd["trough_date"])
                if pi is not None and ti is not None and eq[pi] > 0:
                    pd["depth"] = eq[ti] / eq[pi] - 1.0
                else:
                    pd["depth"] = 0.0
            periods.sort(key=lambda x: x["depth"])
            strategies_out[key] = {
                "key": key,
                "label": strat.label,
                "group": strat.group,
                "note": strat.note,
                "metrics": {
                    "total": met["total"], "cagr": met["cagr"], "vol": met["vol"],
                    "sharpe": met["sharpe"], "sortino": met["sortino"],
                    "maxdd": met["maxdd"], "maxdd_date": met["maxdd_date"],
                    "calmar": met["calmar"], "win_rate": met["win_rate"],
                    "days": met["days"], "start": met["start"], "end": met["end"],
                },
                "yearly": met["yearly"],
                "loss_years": met["loss_years"],
                "final_eq": eq[-1],
                "curve": {
                    "dates": [D[i] for i in idx],
                    "eq": [eq[i] for i in idx],
                },
                "dd": {
                    "dates": [D[i] for i in idx],
                    "v": [dd[i] for i in idx],
                },
                "dd_periods": periods,
                "trade_count": len(res["trades"]),
            }
        out["windows"][wk] = {
            "key": wk,
            "label": W.window_label(wk),
            "note": W.window_note(wk),
            "start": D[0],
            "end": D[-1],
            "days": len(D),
            "strategies": strategies_out,
        }
    return out


def _allocation_table() -> List[Dict]:
    """当前建议配置的分层说明。"""
    layers = [
        ("sh511990", "流动层", "货币 ETF", 0.15),
        ("sh511010", "锁息层", "国债 ETF", 0.20),
        ("sh512890", "红利层", "红利低波 ETF", 0.25),
        ("usXLF.OQ", "红利补充", "美股金融 ETF", 0.05),
        ("sh510300", "宽基层", "沪深300 ETF", 0.15),
        ("sh513100", "成长层", "纳指 ETF", 0.05),
        ("sh518880", "对冲层", "黄金 ETF", 0.10),
        ("usUUP.OQ", "汇率对冲", "美元指数 ETF", 0.05),
    ]
    return [
        {"code": c, "layer": layer, "name": name, "weight": w}
        for c, layer, name, w in layers
    ]


def _property_section(series: Dict, report: Dict) -> Optional[Dict]:
    """构建"持币 vs 持房"区块。

    两种持币情景：

    * ``money_market`` — 货币基金 1.8% 年化（基准，容易核验）
    * ``steve`` — 本项目 Steve 配置的历史月收益率外推（**外推，不是预测**）

    房价路径由 ``price_growth`` 假设驱动，因为本项目**不接入任何房产挂牌
    或成交数据**。结论因此必须看敏感性网格是否同号。
    """
    dates = engine.trading_dates(series)
    mat = engine.align(series, dates)
    D, M_ = W.slice_window(dates, mat, W.DEFAULT_WINDOW)
    if len(D) < 200:
        return None

    start = D[0]
    horizon = PROP.DEFAULT_HORIZON_YEARS

    # 基准情景：货币基金
    base = PROP.build_property_section(
        start, horizon_years=horizon,
        cash_scenario_label="货币基金 1.8% 年化",
        cash_scenario_note="持币侧按货币基金固定年化计息。")

    # 策略情景：Steve 配置的历史月收益率外推
    steve_scn = None
    strat = S.STRATEGIES.get("steve")
    if strat is not None and all(c in M_ for c in strat.codes):
        res = engine.backtest(strat.fn, M_, D, start_cash=1_000_000.0)
        eq = [c["eq"] for c in res["curve"]]
        mret = PROP.monthly_returns_from_equity(eq, D)
        # 外推：把历史平均月收益率平铺到投影区间
        avg = PROP.average_monthly_return(eq, D)
        months = PROP.month_grid(start, f"{int(start[:4]) + horizon:04d}-"
                                     f"{start[5:7]}-{start[8:10]}")
        flat = [avg] * len(months)
        steve_scn = PROP.build_property_section(
            start, horizon_years=horizon,
            cash_monthly_returns=flat,
            cash_scenario_label="Steve 配置历史月收益率外推",
            cash_scenario_note=(
                "持币侧使用本项目 Steve 配置窗口 A 的历史月收益率均值外推。"
                "**这是外推，不是预测**；历史表现不代表未来表现。"))

    out = {
        "base": base,
        "steve": steve_scn,
        "window": {"start": start, "end": base["end"],
                   "label": W.window_label(W.DEFAULT_WINDOW)},
        "disclaimer_zh": (
            "⚠️ 房产对比基于未核验的占位假设（挂牌价不等于成交价，贷款与税费需银行预审）。"
            "结果仅为框架演示，不构成投资建议，不预示未来收益。"),
        "disclaimer_en": (
            "⚠️ Property comparison uses unverified placeholder assumptions. "
            "Not investment advice; past performance does not predict future returns."),
    }
    return out


def _now() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def save(report: Dict, path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, separators=(",", ":"))
    return path
