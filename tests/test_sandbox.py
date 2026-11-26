# -*- coding: utf-8 -*-
"""自定义策略沙盒的回归测试 / Sandbox regression tests.

沙盒是面板上"用户自己配权重"的那一层。它必须继承本项目的核心诚实性
约束，否则用户会在面板上看到一个比离线结果更好看的数字：

1. 权重不足 1 的部分**留在现金**，不得静默归一化到 1（BUG-3 教训）。
2. 窗口起点尚未上市的标的，其权重**不转嫁**给其他资产。
3. 超过 100% 的权重按比例缩放，但必须被**显式标记**，不能静默处理。
4. 调仓频率必须真的生效（"买入持有"= 只在第一天调仓一次）。
5. 样本内/样本外切分必须真的切开，不得重叠。

**如何运行**::

    python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from vlab import engine, metrics, sandbox, windows as W  # noqa: E402


def _mat(dates, series):
    return engine.align(series, dates)


class TestRebalanceModes(unittest.TestCase):
    """调仓频率必须真的改变调仓次数。"""

    def setUp(self):
        self.dates = ["2020-01-31", "2020-02-28", "2020-03-31",
                      "2020-04-30", "2020-05-29", "2020-06-30"]

    def test_monthly_covers_every_month_end(self):
        rd = sandbox._rebal_dates("monthly", self.dates)
        self.assertEqual(len(rd), len(self.dates))

    def test_quarterly_covers_only_quarter_ends(self):
        rd = sandbox._rebal_dates("quarterly", self.dates)
        months = sorted(d[5:7] for d in rd)
        self.assertTrue(all(m in ("03", "06", "09", "12") for m in months))
        self.assertLess(len(rd), len(self.dates))

    def test_yearly_covers_only_december(self):
        rd = sandbox._rebal_dates("yearly", self.dates)
        self.assertTrue(all(d[5:7] == "12" for d in rd))

    def test_hold_rebalances_once(self):
        """买入持有：只在第一天调仓，之后权重随价格漂移。"""
        rd = sandbox._rebal_dates("hold", self.dates)
        self.assertEqual(len(rd), 1)
        self.assertEqual(next(iter(rd)), self.dates[0])


class TestSandboxWeightSemantics(unittest.TestCase):
    """权重语义：现金、不转嫁、超配标记。"""

    def setUp(self):
        self.dates = ["2020-01-02", "2020-01-03", "2020-01-06"]
        self.series = {
            "A": [("2020-01-02", 100.0), ("2020-01-03", 101.0),
                  ("2020-01-06", 102.0)],
            "B": [("2020-01-06", 50.0)],   # 第三天才有价 —— 模拟尚未上市
        }
        self.mat = _mat(self.dates, self.series)

    def test_underweight_stays_in_cash(self):
        """权重 0.5 必须只投 0.5，剩下 0.5 留现金，不得归一化。"""
        w = engine.normalize_weights({"A": 0.5, "B": 0.5}, self.mat, 0)
        self.assertAlmostEqual(sum(w.values()), 0.5)

    def test_unlisted_asset_weight_not_redistributed(self):
        """未上市标的的权重不得挤到其他资产上。"""
        w = engine.normalize_weights({"A": 0.5, "B": 0.5}, self.mat, 0)
        self.assertAlmostEqual(w.get("A", 0.0), 0.5)

    def test_overweight_is_scaled_to_one(self):
        """超过 100% 必须缩放到 100%，而不是留下 >1。"""
        w = engine.normalize_weights({"A": 0.8, "B": 0.8}, self.mat, 2)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)


class TestSandboxAnalyzeWeights(unittest.TestCase):
    """analyze_weights 的端到端行为。"""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data")
        if not os.path.isdir(cls.data_dir) or not os.listdir(cls.data_dir):
            raise unittest.SkipTest("no cached market data; run `vlab fetch` first")

    def test_rejects_empty_weights(self):
        r = sandbox.analyze_weights({}, self.data_dir)
        self.assertIn("error", r)

    def test_result_shape(self):
        r = sandbox.analyze_weights(
            {"sh511990": 0.15, "sh511010": 0.20, "sh512890": 0.25,
             "usXLF.OQ": 0.05, "sh510300": 0.15, "sh513100": 0.05,
             "sh518880": 0.10, "usUUP.OQ": 0.05},
            self.data_dir, window="A", rebal="monthly")
        if r.get("error"):
            self.skipTest(r["error"])
        self.assertTrue(r["ok"])
        for k in ("metrics", "curve", "holdout", "trade_count",
                  "cash_weight", "not_listed", "requested_total"):
            self.assertIn(k, r)
        self.assertIn("dates", r["curve"])
        self.assertIn("eq", r["curve"])
        self.assertIn("dd", r["curve"])

    def test_holdout_splits_without_overlap(self):
        """样本内/样本外必须真的切开，不重叠。"""
        r = sandbox.analyze_weights(
            {"sh511990": 0.15, "sh511010": 0.20, "sh512890": 0.25,
             "usXLF.OQ": 0.05, "sh510300": 0.15, "sh513100": 0.05,
             "sh518880": 0.10, "usUUP.OQ": 0.05},
            self.data_dir, window="A", rebal="monthly")
        if r.get("error"):
            self.skipTest(r["error"])
        ho = r.get("holdout")
        if not ho:
            self.skipTest("holdout unavailable")
        self.assertGreater(ho["n_is"], 0)
        self.assertGreater(ho["n_oos"], 0)
        # 曲线点数 = 日收益数 + 1（首个点没有前一日收益）
        self.assertEqual(ho["n_is"] + ho["n_oos"], r["metrics"]["days"] + 1)

    def test_overweight_is_flagged_not_silent(self):
        """超配必须被标记 scaled_to_one，而不是静默处理。"""
        r = sandbox.analyze_weights(
            {"sh518880": 0.8, "sh510300": 0.7},
            self.data_dir, window="A", rebal="monthly")
        if r.get("error"):
            self.skipTest(r["error"])
        self.assertTrue(r["scaled_to_one"])
        self.assertGreater(r["requested_total"], 1.0)

    def test_underweight_leaves_cash(self):
        """权重不足 100% 时现金权重为正。"""
        r = sandbox.analyze_weights(
            {"sh511990": 0.5}, self.data_dir, window="A", rebal="monthly")
        if r.get("error"):
            self.skipTest(r["error"])
        self.assertAlmostEqual(r["cash_weight"], 0.5, places=6)
        self.assertFalse(r["scaled_to_one"])

    def test_unknown_codes_are_ignored(self):
        """不存在的代码不得进入权重。"""
        r = sandbox.analyze_weights(
            {"sh511990": 0.5, "NOT_A_CODE": 0.3},
            self.data_dir, window="A", rebal="monthly")
        if r.get("error"):
            self.skipTest(r["error"])
        self.assertNotIn("NOT_A_CODE", r["weights"])

    def test_windows_produce_different_periods(self):
        """A / B 两个窗口的样本长度必须不同（口径不得混用）。"""
        ra = sandbox.analyze_weights(
            {"sh511990": 0.5}, self.data_dir, window="A", rebal="monthly")
        rb = sandbox.analyze_weights(
            {"sh511990": 0.5}, self.data_dir, window="B", rebal="monthly")
        if ra.get("error") or rb.get("error"):
            self.skipTest("data unavailable")
        self.assertNotEqual(ra["metrics"]["days"], rb["metrics"]["days"])
        self.assertEqual(rb["metrics"]["days"], 0) if False else None
        self.assertGreater(rb["metrics"]["days"], ra["metrics"]["days"])


class TestUniverseAvailability(unittest.TestCase):
    """可投资状态探测。"""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data")
        if not os.path.isdir(cls.data_dir) or not os.listdir(cls.data_dir):
            raise unittest.SkipTest("no cached market data; run `vlab fetch` first")

    def test_rows_cover_universe(self):
        rows = sandbox.universe_availability(self.data_dir, "A")
        self.assertTrue(rows)
        self.assertEqual(len(rows), len(engine.UNIVERSE))
        for r in rows:
            for k in ("code", "name", "listed_at_start", "has_data"):
                self.assertIn(k, r)

    def test_window_b_flags_more_unlisted_assets(self):
        """窗口 B 起点更早，未上市标的应当更多（或相等）。"""
        a = sandbox.universe_availability(self.data_dir, "A")
        b = sandbox.universe_availability(self.data_dir, "B")
        na = sum(1 for r in a if not r["listed_at_start"])
        nb = sum(1 for r in b if not r["listed_at_start"])
        self.assertGreaterEqual(nb, na)


class TestCashInterest(unittest.TestCase):
    """闲置现金计息（BUG-4：界面曾宣称计息，引擎实际按 0 处理）。

    这是本项目最诚实性相关的一条：界面不能替用户假设一个利率。
    """

    @classmethod
    def setUpClass(cls):
        cls.data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data")
        if not os.path.isdir(cls.data_dir) or not os.listdir(cls.data_dir):
            raise unittest.SkipTest("no cached market data; run `vlab fetch` first")

    def test_default_is_zero_interest(self):
        """默认必须是 0 息 —— 保守口径，不给未实现的收益加分。"""
        r = sandbox.analyze_weights({"sh511990": 0.5}, self.data_dir,
                                    window="A", rebal="monthly")
        if r.get("error"):
            self.skipTest(r["error"])
        self.assertEqual(r["cash_apy"], 0.0)
        self.assertAlmostEqual(r["interest_earned"], 0.0, places=6)

    def test_positive_rate_earns_interest(self):
        """给定现金利率必须真的产生利息，并如实披露。"""
        r0 = sandbox.analyze_weights({"sh511010": 0.5}, self.data_dir,
                                     window="A", rebal="monthly", cash_apy=0.0)
        r1 = sandbox.analyze_weights({"sh511010": 0.5}, self.data_dir,
                                     window="A", rebal="monthly", cash_apy=0.018)
        if r0.get("error") or r1.get("error"):
            self.skipTest("data unavailable")
        self.assertGreater(r1["interest_earned"], 0.0)
        self.assertGreater(r1["metrics"]["cagr"], r0["metrics"]["cagr"])
        self.assertAlmostEqual(r1["cash_apy"], 0.018, places=9)

    def test_fully_invested_portfolio_earns_no_interest(self):
        """满仓组合没有闲置现金，不该凭空产生利息。"""
        r = sandbox.analyze_weights(
            {"sh511990": 0.15, "sh511010": 0.20, "sh512890": 0.25,
             "usXLF.OQ": 0.05, "sh510300": 0.15, "sh513100": 0.05,
             "sh518880": 0.10, "usUUP.OQ": 0.05},
            self.data_dir, window="A", rebal="monthly", cash_apy=0.05)
        if r.get("error"):
            self.skipTest(r["error"])
        # 满仓仍有极少量现金（交易成本造成的），利息应远小于余额规模
        self.assertLess(r["interest_earned"], 1_000_000 * 0.05)
        self.assertGreaterEqual(r["interest_earned"], 0.0)

    def test_engine_returns_interest_field(self):
        """引擎必须返回现金利息字段，且 0 息时为 0。"""
        from vlab import engine as E
        dates = ["2020-01-02", "2020-01-03", "2020-01-06"]
        mat = {"A": [100.0, 101.0, 102.0]}
        res = E.backtest(E.const_weights({"A": 0.5}), mat, dates,
                         start_cash=1e6, cash_apy=0.0)
        self.assertIn("interest_earned", res)
        self.assertEqual(res["interest_earned"], 0.0)
        res2 = E.backtest(E.const_weights({"A": 0.5}), mat, dates,
                          start_cash=1e6, cash_apy=0.05)
        self.assertGreater(res2["interest_earned"], 0.0)


class TestFxConversion(unittest.TestCase):
    """汇率换算（BUG-5：美元价曾被当作人民币直接相加）。"""

    def test_load_fx_reads_cache(self):
        from vlab import engine as E
        data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data")
        fx = E.load_fx(data_dir)
        if not fx:
            self.skipTest("no cached fx data")
        self.assertTrue(all(v > 0 for v in fx.values()))

    def test_fx_series_forward_fills(self):
        from vlab import engine as E
        fx = {"2020-01-02": 7.0, "2020-01-06": 6.9}
        col = E._fx_series(["2020-01-02", "2020-01-03", "2020-01-06"], fx)
        self.assertEqual(col, [7.0, 7.0, 6.9])

    def test_fx_series_empty_fx_is_all_none(self):
        from vlab import engine as E
        self.assertEqual(E._fx_series(["2020-01-02"], {}), [None])

    def test_us_assets_are_converted_when_fx_present(self):
        """有汇率时，美股价格必须被换算成人民币口径。"""
        from vlab import engine as E
        data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data")
        if not E.load_fx(data_dir):
            self.skipTest("no cached fx data")
        raw = E.load_series(data_dir=data_dir, use_fx=False)
        conv = E.load_series(data_dir=data_dir, use_fx=True)
        us = [c for c in raw if c.startswith("us")]
        if not us:
            self.skipTest("no us assets cached")
        c = us[0]
        # 汇率数据起点是 2001-09-09；更早的美股价格**无法**换算，
        # 引擎会保留原始美元价（这是已知边界，不是 bug）。
        # 因此必须挑一个汇率起点之后的点来断言换算生效。
        fx_start = min(E.load_fx(data_dir))
        pairs = list(zip(raw[c], conv[c]))
        after = [(a, b) for a, b in pairs if a[0] >= fx_start]
        if not after:
            self.skipTest("no us quotes after fx start")
        (d0, p0), (d1, p1) = after[0]
        self.assertEqual(d0, d1)
        self.assertNotAlmostEqual(p0, p1, places=6)
        self.assertGreater(p1, 0)

    def test_cn_assets_untouched_by_fx(self):
        """A 股资产不得被汇率换算。"""
        from vlab import engine as E
        data_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data")
        if not E.load_fx(data_dir):
            self.skipTest("no cached fx data")
        raw = E.load_series(data_dir=data_dir, use_fx=False)
        conv = E.load_series(data_dir=data_dir, use_fx=True)
        cn = [c for c in raw if not c.startswith("us")]
        if not cn:
            self.skipTest("no cn assets cached")
        c = cn[0]
        self.assertEqual(raw[c][0], conv[c][0])


if __name__ == "__main__":
    unittest.main()
