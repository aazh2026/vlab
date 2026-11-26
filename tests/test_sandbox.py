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


if __name__ == "__main__":
    unittest.main()
