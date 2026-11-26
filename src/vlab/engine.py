# -*- coding: utf-8 -*-
"""回测引擎 / Backtest engine.

本模块只依赖 Python 标准库，可以在完全离线的情况下用合成数据测试。

三个历史缺陷（已修复，且各有回归测试钉死）
============================================

**BUG-1 跨市场休市日未对齐**
    A 股与美股休市日不同。若直接按各自日期取值再求交/求并，
    缺失报价的交易日会把持仓估值记为 0，产生 -90% 的荒谬回撤。
    *修复*：``align()`` 以统一交易日轴做 forward-fill，上市前填 ``None``。

**BUG-2 货币 ETF 收益蒸发**
    交易型货币基金（如 sh511990）净值恒为 100，收益以份额形式派发，
    价格序列里根本看不到。若不做处理，"全现金"策略年化会是 0%，
    而真实水平约 1.67%。
    *修复*：``synthesize_money_market()`` 按 1.8% 年化合成累积曲线。

**BUG-3 权重过度归一化（最严重）**
    早期若把"目标权重"归一到 1，未上市资产拿不到价格，其权重会
    被挤到少数可交易资产上，导致 2008 年出现虚假的 -30% 单年跌幅。
    *修复*：``normalize_weights()`` 只在总权重 <= 1 时按比例缩放，
    剩余部分**留在现金**；绝不把超额权重强行分配给可交易资产。

诚实性约束
==========
``backtest()`` 只在资产**当日有价格**时才允许建仓，未上市资产不参与
成交。回测区间起点必须晚于所有标的首个交易日，否则结果不可信
（见 ``vlab.windows.WINDOWS``）。
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Sequence

from . import guard
from .metrics import summarize

# --------------------------------------------------------------------------
# 资产池
# --------------------------------------------------------------------------
# (code, 中文名, 资产类别, 年化分红率)
# 年化分红率用于把美股"原始价格"近似为"全收益"序列。
UNIVERSE: List[tuple] = [
    ("sh510300", "沪深300ETF", "cn_equity", 0.0),
    ("sh510880", "红利ETF", "dividend", 0.0),
    ("sh512890", "红利低波", "dividend", 0.0),
    ("sh512800", "银行ETF", "dividend", 0.0),
    ("sh518880", "黄金ETF", "gold", 0.0),
    ("sh511010", "国债ETF", "bond", 0.0),
    ("sh511990", "货币ETF", "cash", 0.0),
    ("sh513100", "纳指ETF", "us_equity", 0.0),
    ("usSPY.OQ", "标普500", "us_equity", 0.013),
    ("usXLF.OQ", "美股金融", "dividend", 0.022),
    ("usQQQ.OQ", "纳指100", "us_equity", 0.006),
    ("usAGG.OQ", "美债", "bond", 0.020),
    ("usGLD.OQ", "美股黄金", "gold", 0.0),
    ("usSLV.OQ", "白银", "metal", 0.0),
    ("usIWM.OQ", "罗素2000", "us_equity", 0.014),
    ("usUUP.OQ", "美元指数", "fx", 0.0),
    # 指数（用于长周期代理：这些指数的上市日早于对应 ETF）
    ("ixsh000300", "沪深300指数", "index", 0.0),
    ("ixsh000922", "中证红利", "index", 0.0),
    ("ixsh000015", "上证红利", "index", 0.0),
    ("ixsh000905", "中证500", "index", 0.0),
]

NAME: Dict[str, str] = {c: n for c, n, _k, _y in UNIVERSE}
CLS: Dict[str, str] = {c: k for c, _n, k, _y in UNIVERSE}
DIVY: Dict[str, float] = {c: y for c, _n, _k, y in UNIVERSE}

#: 货币 ETF 的合成年化收益率（BUG-2 的修复参数）
MONEY_MARKET_APY = 0.018

#: Steve 当前建议配置（2026-11）
STRATEGY_CURRENT: Dict[str, float] = {
    "sh511990": 0.15,   # 货币 流动层
    "sh511010": 0.20,   # 国债 锁息层
    "sh512890": 0.25,   # 红利低波 红利层
    "usXLF.OQ": 0.05,   # 美股金融 红利补充
    "sh510300": 0.15,   # 沪深300 宽基
    "sh513100": 0.05,   # 纳指ETF
    "sh518880": 0.10,   # 黄金
    "usUUP.OQ": 0.05,   # 美元 对冲
}

#: 黄金分档择时：(金价上限美元, 黄金目标权重)
GOLD_BANDS: List[tuple] = [(3000, 0.15), (3300, 0.10), (3600, 0.05), (4000, 0.0)]

#: 默认交易成本
DEFAULT_FEE_BPS = 5.0
DEFAULT_SLIP_BPS = 3.0

WeightsFn = Callable[..., Dict[str, float]]


# --------------------------------------------------------------------------
# 数据准备
# --------------------------------------------------------------------------
def _years_between(d0: str, d1: str) -> float:
    """两个 YYYY-MM-DD 之间的大致年数（按月精确计算）。"""
    y = int(d1[:4]) - int(d0[:4])
    m = (int(d1[5:7]) - int(d0[5:7])) / 12.0
    return y + m


def synthesize_money_market(rows: List[dict], apy: float = MONEY_MARKET_APY) -> List[tuple]:
    """把货币 ETF 的恒定净值合成为累积收益曲线。

    输入 ``rows`` 为 ``[{"d": "2019-01-02", "c": 100.0}, ...]``，
    输出 ``[("2019-01-02", 100.0), ...]``，按年化 ``apy`` 复利增长。
    """
    if not rows:
        return []
    base = rows[0]["d"]
    return [
        (r["d"], 100.0 * (1.0 + apy) ** _years_between(base, r["d"]))
        for r in rows
    ]


def apply_dividend_approx(rows: List[dict], annual_yield: float) -> List[tuple]:
    """把价格序列近似为全收益序列（按固定年化分红率复利调整）。

    仅用于美股标的。这是一个**近似**，不是精确的股息再投资，
    因此所有基于它的长期结论都带有已知偏差 —— 详见 README 的局限性章节。
    """
    if not rows or annual_yield <= 0:
        return [(r["d"], float(r["c"])) for r in rows]
    base = rows[0]["d"]
    return [
        (r["d"], float(r["c"]) * (1.0 + annual_yield) ** _years_between(base, r["d"]))
        for r in rows
    ]


def load_series(codes: Optional[Iterable[str]] = None, data_dir: Optional[str] = None) -> Dict[str, List[tuple]]:
    """读取本地缓存行情并加工成 ``{code: [(date, close), ...]}``。

    缺货/未上市资产会被自动跳过；调用方需自行确认资产实际可用区间。
    """
    import json
    import os

    if data_dir is None:
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
        )
    codes = list(codes or [c for c, *_ in UNIVERSE])
    out: Dict[str, List[tuple]] = {}
    for c in codes:
        key = c.replace(":", "_").replace(".", "_")
        path = os.path.join(data_dir, key + ".json")
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                rows = json.load(f)
        except Exception:
            continue
        if not rows:
            continue
        if c == "sh511990":
            out[c] = synthesize_money_market(rows)
        elif DIVY.get(c, 0) > 0:
            out[c] = apply_dividend_approx(rows, DIVY[c])
        else:
            out[c] = [(r["d"], float(r["c"])) for r in rows]
    return out


def align(series: Dict[str, List[tuple]], dates: Sequence[str]) -> Dict[str, List[Optional[float]]]:
    """对齐到统一交易日轴（BUG-1 修复）。

    - 当日有报价 → 用当日价格
    - 当日休市 → forward-fill 上一个有效价格
    - 上市之前   → ``None``（表示不可投资，**不参与估值也不参与成交**）
    """
    mat: Dict[str, List[Optional[float]]] = {}
    for c, rows in series.items():
        s = dict(rows)
        last: Optional[float] = None
        col: List[Optional[float]] = []
        for d in dates:
            if d in s:
                last = s[d]
            col.append(last)
        mat[c] = col
    return mat


def trading_dates(series: Dict[str, List[tuple]]) -> List[str]:
    """从资产序列推出统一交易日轴（所有资产的日期并集）。"""
    s: set = set()
    for rows in series.values():
        for d, _ in rows:
            s.add(d)
    return sorted(s)


def month_ends(dates: Sequence[str]) -> set:
    """每个自然月的最后一个交易日。"""
    out, prev_m, prev_d = [], None, None
    for d in dates:
        m = d[:7]
        if prev_m is not None and m != prev_m:
            out.append(prev_d)
        prev_m, prev_d = m, d
    if prev_d:
        out.append(prev_d)
    return set(out)


# --------------------------------------------------------------------------
# 权重处理
# --------------------------------------------------------------------------
def normalize_weights(
    weights: Dict[str, float],
    mat: Dict[str, List[Optional[float]]],
    i: int,
) -> Dict[str, float]:
    """剔除非正权重与当日无价资产，并把总权重收敛到 <= 1（BUG-3 修复）。

    **关键语义**：如果剔除后总权重仍 > 1（例如因剔除导致分母变小），
    按比例缩放到 1；**剩余部分留在现金**，而不是强行分配给可交易资产。
    """
    w = {c: float(v) for c, v in (weights or {}).items() if c in mat and v > 0}
    w = {c: v for c, v in w.items() if mat[c][i] is not None}
    tot = sum(w.values())
    if tot <= 0:
        return {}
    if tot > 1.0:
        w = {c: v / tot for c, v in w.items()}
    return w


def const_weights(weights: Dict[str, float]) -> WeightsFn:
    """返回一个恒定权重的策略函数。"""

    def fn(d, mat, dates, i):
        return dict(weights)

    return fn


# --------------------------------------------------------------------------
# 回测主循环
# --------------------------------------------------------------------------
def backtest(
    weights_fn: WeightsFn,
    mat: Dict[str, List[Optional[float]]],
    dates: Sequence[str],
    start_cash: float = 1_000_000.0,
    fee_bps: float = DEFAULT_FEE_BPS,
    slip_bps: float = DEFAULT_SLIP_BPS,
    rebal_dates: Optional[Iterable[str]] = None,
    tolerance: float = 0.02,
) -> Dict:
    """执行一次带回测。

    约定
    ----
    * 调仓在**调仓日当日收盘价**成交（不含日内择时）。
    * 佣金 ``fee_bps`` + 滑点 ``slip_bps``，买入上浮、卖出下压。
    * 现金不足以完成全部买入时，按比例缩放买入金额。
    * 权重偏离目标 2% 以内不交易（减少无意义的换手与成本）。

    返回 ``{"curve": [{"d":..., "eq":...}], "trades": [...]}``。
    """
    fee = fee_bps / 1e4
    slip = slip_bps / 1e4
    if rebal_dates is None:
        rebal_dates = month_ends(dates)
    else:
        rebal_dates = set(rebal_dates)

    cash = float(start_cash)
    pos: Dict[str, float] = {}      # code -> 份额
    curve: List[Dict] = []
    trades: List[Dict] = []

    for i, d in enumerate(dates):
        val = cash + sum(sh * (mat[c][i] or 0.0) for c, sh in pos.items())

        if d in rebal_dates:
            # 策略只拿到"截至今天"的视图：mat[c][j] 中 j > i 会抛
            # LookAheadError，把静默的未来函数变成响亮的错误。
            mview, dview = guard.guard_view(mat, dates, i)
            w = normalize_weights(weights_fn(d, mview, dview, i) or {}, mat, i)
            if w:
                cash = _rebalance(cash, pos, mat, dates, i, w, val, fee, slip,
                                  tolerance, trades)

        # 净值在调仓之后记录：成交价即当日收盘价，净值不受调仓影响，
        # 只体现交易成本。这一点很重要 —— 否则日收益序列会多出一笔
        # "凭空"的负收益。
        val = cash + sum(sh * (mat[c][i] or 0.0) for c, sh in pos.items())
        curve.append({"d": d, "eq": val})

    return {"curve": curve, "trades": trades}


def _rebalance(cash, pos, mat, dates, i, w, target_val, fee, slip,
               tolerance, trades):
    """在 ``i`` 日以收盘价调仓。

    ``pos`` 是可变 dict，传入后原地修改。
    ``cash`` 是 float，Python 按值传递 —— 因此**必须返回**新的现金余额，
    调用方要接住返回值。（这是本引擎历史上最隐蔽的一个 bug：
    忘记接收返回值会导致现金永远不扣减，权益虚增。）
    """
    # 1) 卖出超配
    for c in list(pos.keys()):
        pxv = mat[c][i]
        if pxv is None:
            continue
        cur = pos[c] * pxv
        tgt = target_val * w.get(c, 0.0)
        if cur <= tgt * (1.0 + tolerance):
            continue
        sell_v = cur - tgt
        sell_sh = sell_v / pxv
        cash += sell_sh * pxv * (1.0 - fee - slip)
        trades.append({
            "d": dates[i], "code": c, "name": NAME.get(c, c),
            "side": "sell", "px": pxv, "value": sell_v,
        })
        pos[c] -= sell_sh
        if pos[c] * pxv < target_val * 0.001:
            del pos[c]

    # 2) 买入低配（现金不足按比例缩放）
    buys = []
    for c, wt in w.items():
        pxv = mat[c][i]
        if pxv is None:
            continue
        cur = pos.get(c, 0.0) * pxv
        tgt = target_val * wt
        if tgt > cur * (1.0 + tolerance):
            buys.append((c, pxv, tgt - cur))
    need = sum(b[2] for b in buys)
    scale = 1.0 if need <= cash * 0.995 else (cash * 0.995 / need if need > 0 else 1.0)
    for c, pxv, amt in buys:
        amt *= scale
        if amt <= 0:
            continue
        shares = amt / (pxx_guard(pxv) * (1.0 + fee + slip))
        cost = shares * pxv * (1.0 + fee + slip)
        if cost > cash:
            continue
        cash -= cost
        pos[c] = pos.get(c, 0.0) + shares
        trades.append({
            "d": dates[i], "code": c, "name": NAME.get(c, c),
            "side": "buy", "px": pxv, "value": amt,
        })
    return cash


def pxx_guard(px: float) -> float:
    """防御性：价格为 0 或负时不允许成交（会除零）。"""
    return px if px and px > 0 else 1e-12


def bench_from_mat(
    mat: Dict[str, List[Optional[float]]],
    code: str,
    dates: Sequence[str],
    cash0: float = 1_000_000.0,
) -> Dict:
    """单资产买入持有基准（含交易成本近似）。"""
    col = mat.get(code)
    if not col:
        return {}
    eq: List[Dict] = []
    base = None
    for i, d in enumerate(dates):
        if col[i] is None:
            continue
        if base is None:
            base = col[i]
        eq.append({"d": d, "eq": cash0 * col[i] / base})
    if not eq:
        return {}
    return summarize([c["eq"] for c in eq], [c["d"] for c in eq])


def run(
    weights_fn: WeightsFn,
    mat: Dict[str, List[Optional[float]]],
    dates: Sequence[str],
    **kw,
) -> Dict:
    """跑一次回测并直接返回指标字典。"""
    res = backtest(weights_fn, mat, dates, **kw)
    return summarize([c["eq"] for c in res["curve"]], [c["d"] for c in res["curve"]])


def yearly(curve: Sequence[Dict]) -> Dict[str, float]:
    """由 ``curve`` 计算年度收益率（兼容旧调用方式）。"""
    from .metrics import yearly_returns
    return yearly_returns([c["eq"] for c in curve], [c["d"] for c in curve])


def metrics_of(curve: Sequence[Dict], rf: float = 0.018) -> Dict:
    """由 ``curve`` 直接得到指标字典（兼容旧调用方式）。"""
    return summarize([c["eq"] for c in curve], [c["d"] for c in curve], rf=rf)


def fmt(m: Dict, label: str = "") -> str:
    """一行式指标摘要，便于 CLI 输出。"""
    if not m:
        return f"{label}: no data"
    return (
        f"{label:22} 总收益{m['total']*100:8.2f}%  年化{m['cagr']*100:6.2f}%  "
        f"波动{m['vol']*100:5.1f}%  夏普{m['sharpe']:5.2f}  Sortino{m['sortino']:5.2f}  "
        f"回撤{m['maxdd']*100:7.2f}%  Calmar{m['calmar']:5.2f}  胜率{m['win_rate']*100:4.1f}%"
    )
