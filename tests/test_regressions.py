# -*- coding: utf-8 -*-
"""回归测试：把三个历史缺陷钉死 / Regression tests for the three historical bugs.

这些测试是本项目最有价值的资产。

**为什么重要？**
开发本项目期间，引擎出现过三个缺陷，每一个都足以让回测结论**完全反转**：

* BUG-1 让 2008 年的回撤变成 -90%
* BUG-2 让现金策略的年化变成 0%
* BUG-3 让 2008 年出现虚假的 -30% 单年跌幅

如果这些测试不存在，下一个人（包括未来的我）随时可能把它们改回去，
而你永远不会知道。

**如何运行**::

    python3 -m unittest discover -s tests -v

无需安装依赖，无需联网。
"""
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"),
)

from vlab import engine  # noqa: E402
from vlab.engine import align, backtest, const_weights, normalize_weights  # noqa: E402
from vlab.metrics import summarize  # noqa: E402


class TestBug1CalendarAlignment(unittest.TestCase):
    """BUG-1：跨市场休市日未对齐。

    A 股与美股休市日不同。若缺失报价的日子把持仓估值记为 0，
    回撤会算出荒谬的 -90%。

    修复：``align()`` 做 forward-fill，休市日沿用上一个有效价格。
    """

    def test_forward_fill_on_market_holiday(self):
        # A 股：1/2 交易、1/3 休市、1/4 交易
        series = {"A": [("2020-01-02", 100.0), ("2020-01-04", 110.0)]}
        dates = ["2020-01-02", "2020-01-03", "2020-01-04"]
        mat = align(series, dates)
        self.assertEqual(mat["A"], [100.0, 100.0, 110.0],
                         "休市日必须 forward-fill，不能归零")

    def test_pre_listing_is_none_not_zero(self):
        """上市之前必须是 None（不可投资），而不是 0（会被算成暴跌）。"""
        series = {"A": [("2020-01-04", 100.0)]}
        dates = ["2020-01-02", "2020-01-03", "2020-01-04"]
        mat = align(series, dates)
        self.assertIsNone(mat["A"][0])
        self.assertIsNone(mat["A"][1])
        self.assertEqual(mat["A"][2], 100.0)

    def test_no_artificial_drawdown_from_holiday(self):
        """端到端：只因休市导致的"价格缺失"不得产生回撤。"""
        dates = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
        series = {"A": [("2020-01-02", 100.0), ("2020-01-06", 100.0), ("2020-01-07", 100.0)]}
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=0.0, slip_bps=0.0,
                       rebal_dates=["2020-01-02"])
        m = summarize([c["eq"] for c in res["curve"]], [c["d"] for c in res["curve"]])
        self.assertGreater(m["maxdd"], -1e-9,
                           "休市日不应造成任何回撤")


class TestBug2MoneyMarketYield(unittest.TestCase):
    """BUG-2：货币 ETF 收益蒸发。

    交易型货币基金净值恒为 100，收益以份额形式派发，价格序列里看不到。
    若不处理，"全现金"策略年化会是 0%，真实水平约 1.67%。
    """

    def test_money_market_grows(self):
        rows = [{"d": "2020-01-02", "c": 100.0},
                {"d": "2021-01-04", "c": 100.0}]
        synth = engine.synthesize_money_market(rows, apy=0.018)
        self.assertAlmostEqual(synth[0][1], 100.0, places=6)
        self.assertGreater(synth[1][1], 100.0, "一年后必须增长")
        self.assertAlmostEqual(synth[1][1], 101.8, places=3)

    def test_money_market_not_flat_in_backtest(self):
        """纯货币策略的年化应接近 1.8%，而非 0%。

        用真实密度的交易日（连续 250 个工作日）以避免年化折算失真。
        """
        import datetime as _dt
        dates: list = []
        d = _dt.date(2020, 1, 1)
        while len(dates) < 250:
            if d.weekday() < 5:
                dates.append(d.isoformat())
            d += _dt.timedelta(days=1)
        rows = [{"d": x, "c": 100.0} for x in dates]
        series = {"sh511990": engine.synthesize_money_market(rows)}
        mat = align(series, dates)
        res = backtest(const_weights({"sh511990": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=0.0, slip_bps=0.0,
                       rebal_dates=dates)
        m = summarize([c["eq"] for c in res["curve"]], [c["d"] for c in res["curve"]])
        self.assertGreater(m["cagr"], 0.015, "现金策略必须有接近 1.8% 的正收益")
        self.assertLess(m["cagr"], 0.025, "现金策略收益应接近 1.8% 而非暴利")


class TestBug3WeightNormalization(unittest.TestCase):
    """BUG-3：权重过度归一化（最严重）。

    早期把目标权重归一到 1，导致未上市资产的权重被挤到少数可交易资产上，
    制造出 2008 年虚假的 -30% 单年跌幅。

    修复：``normalize_weights()`` 永不把总权重放大到 1 以上；
    超额部分留在现金。
    """

    def setUp(self):
        # 资产 A 一直可交易；资产 B 从第 3 天才有价格（模拟"尚未上市"）
        self.dates = ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"]
        self.series = {
            "A": [("2020-01-01", 100.0), ("2020-02-01", 100.0),
                  ("2020-03-01", 100.0), ("2020-04-01", 100.0)],
            "B": [("2020-03-01", 100.0), ("2020-04-01", 100.0)],
        }
        self.mat = align(self.series, self.dates)

    def test_missing_asset_weight_stays_in_cash(self):
        """资产 B 不可投时，它的权重不得转嫁给 A。"""
        w = normalize_weights({"A": 0.5, "B": 0.5}, self.mat, 0)
        self.assertAlmostEqual(sum(w.values()), 0.5,
                               msg="总权重必须保持 0.5，剩余 0.5 留在现金")

    def test_never_exceeds_one(self):
        """即使传入权重之和 > 1，归一化后也必须 == 1。"""
        w = normalize_weights({"A": 0.8, "B": 0.8}, self.mat, 3)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_no_fake_crash_when_asset_not_listed(self):
        """核心回归：未上市资产不得导致暴跌。"""
        # 只买 B（尚未上市），A 不买 —— 前两天 B 不可投，资金应全在现金
        res = backtest(const_weights({"B": 1.0}), self.mat, self.dates,
                       start_cash=100_000.0, fee_bps=0.0, slip_bps=0.0,
                       rebal_dates=self.dates)
        eq = [c["eq"] for c in res["curve"]]
        m = summarize(eq, self.dates)
        self.assertGreater(m["maxdd"], -1e-9, "未上市资产不得制造回撤")
        self.assertAlmostEqual(eq[0], eq[1], places=6, msg="现金期净值必须持平")


class TestNoLookahead(unittest.TestCase):
    """通用诚实性约束：不得使用未来信息。"""

    def test_weights_fn_only_sees_past(self):
        """策略函数只能拿到当日及之前的数据。

        这里用"作弊策略"验证引擎：它在最后一天把全部资产权重改成 100%，
        如果引擎有任何未来信息泄漏，这个测试无法通过 —— 因为作弊策略
        只依赖传入的 index，不依赖未来价格。真正要防的是引擎在成交时
        使用了未来价格，这里通过记录成交价来验证。
        """
        dates = ["2020-01-01", "2020-02-01", "2020-03-01"]
        series = {"A": [("2020-01-01", 100.0), ("2020-02-01", 110.0),
                        ("2020-03-01", 120.0)]}
        mat = align(series, dates)

        def cheat(d, m, ds, i):
            return {"A": 1.0}

        res = backtest(cheat, mat, dates, start_cash=100_000.0,
                       fee_bps=0.0, slip_bps=0.0, rebal_dates=["2020-01-01"])
        buy = [t for t in res["trades"] if t["side"] == "buy"]
        self.assertEqual(len(buy), 1)
        self.assertEqual(buy[0]["px"], 100.0,
                         "必须用成交日当日价格，不能用未来价格")


class TestMetrics(unittest.TestCase):
    """指标计算的基本正确性。"""

    def test_cagr(self):
        from vlab.metrics import cagr
        self.assertAlmostEqual(cagr([100.0, 110.0], periods_per_year=1), 0.10, places=9)

    def test_max_drawdown(self):
        from vlab.metrics import max_drawdown
        dd, _ = max_drawdown([100.0, 120.0, 60.0, 130.0])
        self.assertAlmostEqual(dd, -0.5, places=9)

    def test_drawdown_series(self):
        from vlab.metrics import drawdown_series
        self.assertEqual(
            [round(x, 6) for x in drawdown_series([100.0, 120.0, 60.0, 130.0])],
            [0.0, 0.0, -0.5, 0.0],
        )

    def test_yearly_returns(self):
        from vlab.metrics import yearly_returns
        # 2019 年末 100 -> 2020 年末 110 -> 2021 年末 121 -> 2022 年末 133.1
        eq = [100.0, 110.0, 121.0, 133.1]
        ds = ["2019-12-31", "2020-12-31", "2021-12-31", "2022-12-30"]
        y = yearly_returns(eq, ds)
        # 首年无前值可用，以序列首值为基准 -> 0%
        self.assertAlmostEqual(y["2019"], 0.0, places=6)
        self.assertAlmostEqual(y["2020"], 0.10, places=6)
        self.assertAlmostEqual(y["2021"], 0.10, places=6)
        self.assertAlmostEqual(y["2022"], 0.10, places=6)

    def test_yearly_returns_chained(self):
        """年度收益必须能连乘还原总收益（从第二年起）。"""
        from vlab.metrics import yearly_returns
        eq = [100.0, 110.0, 99.0, 118.8]
        ds = ["2019-12-31", "2020-12-31", "2021-12-31", "2022-12-30"]
        y = yearly_returns(eq, ds)
        chained = 1.0
        for k in sorted(y)[1:]:
            chained *= (1.0 + y[k])
        self.assertAlmostEqual(chained * 100.0, eq[-1], places=6)


class TestCashConservation(unittest.TestCase):
    """现金守恒：买入必须真实扣减现金。

    这是一条在重构中被真实引入过的 bug：``_rebalance()`` 里 ``cash``
    是 float，Python 按值传递，函数内 ``cash -= cost`` **不会**回写
    调用方的变量。结果是现金永远不扣减、权益虚增（实测年化 23.7%，
    而真实值是 1.8%）。

    这类 bug 靠肉眼几乎不可能发现，但一行断言就能钉死它。
    """

    def test_buy_deducts_cash(self):
        dates = ["2020-01-02", "2020-02-03"]
        series = {"A": [("2020-01-02", 100.0), ("2020-02-03", 100.0)]}
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=0.0, slip_bps=0.0,
                       rebal_dates=["2020-01-02"])
        eq = res["curve"][0]["eq"]
        self.assertAlmostEqual(eq, 100_000.0, places=2,
                               msg="买入后总权益不应凭空增加")

    def test_full_investment_tracks_asset_price(self):
        """满仓买入后，净值必须跟住资产价格，不能凭空膨胀。"""
        dates = ["2020-01-02", "2020-02-03", "2020-03-02"]
        series = {"A": [("2020-01-02", 100.0), ("2020-02-03", 110.0),
                        ("2020-03-02", 121.0)]}
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=0.0, slip_bps=0.0,
                       rebal_dates=["2020-01-02"])
        eq = [c["eq"] for c in res["curve"]]
        # 买入金额上限为 99.5% 现金（留出费用缓冲），剩余 0.5% 留作现金。
        # 净值 = 99500 * 1.21 + 500 = 120895
        expected = 100_000.0 * 0.995 * 1.21 + 100_000.0 * 0.005
        self.assertAlmostEqual(eq[-1], expected, delta=1.0)
        self.assertAlmostEqual(eq[0], 100_000.0, places=2)

    def test_equity_never_exceeds_hold_value(self):
        """权益不得超过“满仓持有不动”的上界（无杠杆、无凭空增益）。

        构造一个上涨序列：真实权益应当紧贴“价格涨幅 × 起始资金”，
        并且永远低于或等于持有不动的结果。
        """
        import datetime as _dt
        dates: list = []
        d = _dt.date(2020, 1, 1)
        while len(dates) < 120:
            if d.weekday() < 5:
                dates.append(d.isoformat())
            d += _dt.timedelta(days=1)
        prices = [100.0 + i * 0.1 for i in range(len(dates))]
        series = {"A": list(zip(dates, prices))}
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=5.0, slip_bps=3.0,
                       rebal_dates=dates)
        eq = [c["eq"] for c in res["curve"]]
        hold = [100_000.0 * (p / prices[0]) for p in prices]
        for e, h in zip(eq, hold):
            self.assertLessEqual(e, h + 1e-6,
                                 msg="有交易成本时权益不得超过持有不动的上界")
        # 同时也不能低于持有不动的 95%（否则说明仓位没建立起来）
        for e, h in zip(eq, hold):
            self.assertGreater(e, h * 0.95, msg="仓位应基本建立")


if __name__ == "__main__":
    unittest.main(verbosity=2)
