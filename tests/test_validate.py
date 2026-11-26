# -*- coding: utf-8 -*-
"""自定义策略有效性检验的回归测试 / Tests for guard + validate.

为什么这些测试存在
------------------
``vlab.guard`` 和 ``vlab.validate`` 是本项目"诚实性"承诺的新载体：

* ``guard`` 把"偷看未来"从**静默的作弊**变成**响亮的错误**。
* ``validate`` 把"样本内好看"和"样本外有效"这两件事区分开。

如果这些测试不存在，下一个人随时可能把它们改回去 —— 而你永远不会知道。
这正是本项目反复强调的：缺陷即资产，测试即资产。

运行::

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

from vlab import engine, guard, validate  # noqa: E402
from vlab.engine import align, backtest, const_weights  # noqa: E402


def _toy(n=8, start=100.0, step=1.0):
    """构造一个玩具数据集：n 个交易日，价格线性上涨。

    日期按月递增（跨年也正确），保证生成的日期都合法可排序。
    """
    dates = []
    for i in range(n):
        y = 2020 + i // 12
        m = i % 12 + 1
        dates.append("%04d-%02d-01" % (y, m))
    series = {"A": [(d, start + i * step) for i, d in enumerate(dates)]}
    return dates, series


# ==========================================================================
# guard —— 防未来函数
# ==========================================================================
class TestLookAheadGuard(unittest.TestCase):
    """策略函数不得读取未来数据。"""

    def test_reading_next_day_raises(self):
        dates, series = _toy()
        mat = align(series, dates)

        def cheat(d, m, ds, i):
            return {"A": 1.0} if m["A"][i + 1] is not None else {}

        with self.assertRaises(guard.LookAheadError):
            backtest(cheat, mat, dates, start_cash=100_000.0)

    def test_negative_index_also_raises(self):
        """负索引按真实长度解析，因此 ``[-1]`` 是未来，必须拦下。"""
        dates, series = _toy()
        mat = align(series, dates)

        def cheat(d, m, ds, i):
            return {"A": 1.0} if m["A"][-1] is not None else {}

        with self.assertRaises(guard.LookAheadError):
            backtest(cheat, mat, dates, start_cash=100_000.0)

    def test_reading_current_day_is_allowed(self):
        dates, series = _toy()
        mat = align(series, dates)

        def ok(d, m, ds, i):
            return {"A": 1.0} if m["A"][i] is not None else {}

        res = backtest(ok, mat, dates, start_cash=100_000.0)
        self.assertEqual(len(res["curve"]), len(dates))

    def test_reading_past_is_allowed(self):
        """回看历史（动量类策略的基础）必须能工作。"""
        dates, series = _toy()
        mat = align(series, dates)

        def mom(d, m, ds, i):
            if i < 2:
                return {}
            a, b = m["A"][i], m["A"][i - 2]
            return {"A": 1.0} if (a is not None and b is not None and a > b) else {}

        res = backtest(mom, mat, dates, start_cash=100_000.0)
        self.assertEqual(len(res["curve"]), len(dates))

    def test_future_date_raises(self):
        dates, series = _toy()
        mat = align(series, dates)

        def cheat(d, m, ds, i):
            _ = ds[i + 1]
            return {}

        with self.assertRaises(guard.LookAheadError):
            backtest(cheat, mat, dates, start_cash=100_000.0)

    def test_error_is_index_error_subclass(self):
        """继承 IndexError 便于兼容，但语义上是诚实性违规。"""
        self.assertTrue(issubclass(guard.LookAheadError, IndexError))

    def test_view_reports_its_own_length(self):
        dates, series = _toy()
        mat = align(series, dates)
        view, dview = guard.guard_view(mat, dates, 2)
        self.assertEqual(len(view["A"]), 3)
        self.assertEqual(len(dview), 3)

    def test_view_keeps_key_set(self):
        """策略仍需知道有哪些资产可用，只是不能看未来价格。"""
        dates, series = _toy()
        mat = align(series, dates)
        view, _ = guard.guard_view(mat, dates, 1)
        self.assertIn("A", view)
        self.assertEqual(list(view.keys()), ["A"])


# ==========================================================================
# validate —— 有效性检验
# ==========================================================================
class TestHoldout(unittest.TestCase):
    """样本内 / 样本外切分。"""

    def test_split_produces_two_segments(self):
        dates, series = _toy(n=20)
        mat = align(series, dates)
        r = validate.holdout(const_weights({"A": 1.0}), mat, dates,
                             split_ratio=0.5)
        self.assertTrue(r["is"])
        self.assertTrue(r["oos"])
        self.assertGreater(r["n_is"], 0)
        self.assertGreater(r["n_oos"], 0)
        self.assertEqual(r["n_is"] + r["n_oos"], 20)

    def test_explicit_split_date_wins(self):
        """给定切分日时，样本外首日 = 第一个 >= 切分日的交易日。"""
        dates, series = _toy(n=20)
        mat = align(series, dates)
        r = validate.holdout(const_weights({"A": 1.0}), mat, dates,
                             split_date="2020-06-15")
        expected = next(d for d in dates if d >= "2020-06-15")
        self.assertEqual(r["split_date"], expected)

    def test_segments_are_contiguous_and_ordered(self):
        dates, series = _toy(n=20)
        mat = align(series, dates)
        r = validate.holdout(const_weights({"A": 1.0}), mat, dates,
                             split_ratio=0.6)
        # 样本外首日必须严格晚于样本内末日，且两段之间没有缺口：
        # 样本外首日就是完整序列里紧接样本内末日的下一个交易日。
        self.assertLess(r["is_curve"][-1]["d"], r["oos_curve"][0]["d"])
        self.assertEqual(r["n_is"] + r["n_oos"], len(dates))
        joined = r["is_curve"] + r["oos_curve"]
        self.assertEqual([c["d"] for c in joined], dates)


class TestParameterSweep(unittest.TestCase):
    """参数网格搜索 + 样本外验证。"""

    def _grid(self):
        return [{"k": 1}, {"k": 2}, {"k": 3}]

    def _factory(self):
        def make(params):
            k = params["k"]

            def fn(d, m, ds, i):
                if i < k:
                    return {}
                return {"A": 1.0}
            return fn
        return make

    def test_sweep_returns_all_rows(self):
        dates, series = _toy(n=20)
        mat = align(series, dates)
        r = validate.parameter_sweep(self._factory(), self._grid(), mat, dates)
        self.assertEqual(r["n_combos"], 3)
        self.assertEqual(len(r["rows"]), 3)

    def test_oracle_is_never_worse_than_selected(self):
        """先知基线是搜索偏差的上界，绝不可能比样本内选出的更差。"""
        dates, series = _toy(n=30)
        mat = align(series, dates)
        r = validate.parameter_sweep(self._factory(), self._grid(), mat, dates)
        self.assertGreaterEqual(r["oracle_oos_metric"], r["selected_oos_metric"])

    def test_overfit_gap_matches_definition(self):
        dates, series = _toy(n=30)
        mat = align(series, dates)
        r = validate.parameter_sweep(self._factory(), self._grid(), mat, dates)
        self.assertAlmostEqual(
            r["overfit_gap"],
            r["selected_oos_metric"] - r["oracle_oos_metric"],
            places=9,
        )

    def test_winner_count_in_range(self):
        dates, series = _toy(n=30)
        mat = align(series, dates)
        r = validate.parameter_sweep(self._factory(), self._grid(), mat, dates)
        self.assertGreaterEqual(r["oos_winners"], 0)
        self.assertLessEqual(r["oos_winners"], r["n_combos"])

    def test_selected_params_come_from_grid(self):
        dates, series = _toy(n=30)
        mat = align(series, dates)
        r = validate.parameter_sweep(self._factory(), self._grid(), mat, dates)
        self.assertIn(r["selected"], self._grid())


class TestWalkForward(unittest.TestCase):
    """滚动前推。"""

    def _factory(self):
        def make(params):
            def fn(d, m, ds, i):
                return {"A": 1.0}
            return fn
        return make

    def test_produces_folds(self):
        dates, series = _toy(n=40)
        mat = align(series, dates)
        r = validate.walk_forward(self._factory(), [{"k": 1}], mat, dates,
                                 n_folds=4)
        self.assertEqual(r["n_folds"], 4)
        self.assertEqual(len(r["folds"]), 4)

    def test_each_fold_has_distinct_oos_period(self):
        dates, series = _toy(n=40)
        mat = align(series, dates)
        r = validate.walk_forward(self._factory(), [{"k": 1}], mat, dates,
                                 n_folds=4)
        oos_starts = [f["oos_start"] for f in r["folds"]]
        self.assertEqual(len(set(oos_starts)), len(oos_starts))

    def test_oos_starts_after_is_ends(self):
        """样本外必须严格晚于样本内 —— 否则就不是前推了。"""
        dates, series = _toy(n=40)
        mat = align(series, dates)
        r = validate.walk_forward(self._factory(), [{"k": 1}], mat, dates,
                                 n_folds=4)
        for f in r["folds"]:
            self.assertLess(f["is_end"], f["oos_start"])

    def test_composite_curve_is_normalized(self):
        """每段等权拼接：每段起点归一为 1.0。"""
        dates, series = _toy(n=40)
        mat = align(series, dates)
        r = validate.walk_forward(self._factory(), [{"k": 1}], mat, dates,
                                 n_folds=4)
        curve = r["walkforward_curve"]
        self.assertTrue(curve)
        # 第一条应当是 1.0（归一化基准）
        self.assertAlmostEqual(curve[0]["eq"], 1.0, places=9)

    def test_metrics_of_composite_present(self):
        dates, series = _toy(n=40)
        mat = align(series, dates)
        r = validate.walk_forward(self._factory(), [{"k": 1}], mat, dates,
                                 n_folds=4)
        m = r["walkforward_metrics"]
        self.assertIn("cagr", m)
        self.assertIn("maxdd", m)


class TestEvaluate(unittest.TestCase):
    """一站式报告。"""

    def test_evaluate_returns_full_and_windows(self):
        dates, series = _toy(n=40)
        mat = align(series, dates)
        r = validate.evaluate(const_weights({"A": 1.0}), mat, dates,
                              windows={"X": ("2020-01-01", "2020-01-20")})
        self.assertIn("full", r)
        self.assertIn("windows", r)
        self.assertIn("X", r["windows"])
        self.assertIn("holdout", r)


# ==========================================================================
# 回归：护栏接入后，原有策略结果不变
# ==========================================================================
class TestGuardDoesNotChangeResults(unittest.TestCase):
    """加了护栏不能改变任何已有策略的成绩。"""

    def test_constant_weight_result_unchanged(self):
        """满仓单资产、无费用时，净值应精确等于价格比值。

        末价为 ``100 + (n-1)``；这里关掉费用与滑点，才能对得上纯价格比。
        """
        n = 20
        dates, series = _toy(n)
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=0.0, slip_bps=0.0)
        eq = [c["eq"] for c in res["curve"]]
        # 引擎建仓时留 0.5% 现金缓冲（cash * 0.995），所以终值 =
        # 0.995 仓位 × 末价 + 0.5% 现金
        expected = 0.995 * (100.0 + n - 1) + 0.005 * 100.0
        self.assertAlmostEqual(eq[-1] / eq[0], expected / 100.0, places=6)

    def test_constant_weight_with_costs_is_below_price_ratio(self):
        """加了交易成本后，成绩必然低于纯价格比 —— 成本是真实损耗。"""
        n = 20
        dates, series = _toy(n)
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=50, slip_bps=50)
        eq = [c["eq"] for c in res["curve"]]
        self.assertLess(eq[-1] / eq[0], (100.0 + n - 1) / 100.0)

    def test_cash_never_negative(self):
        """护栏没有破坏现金守恒。"""
        dates, series = _toy(n=20)
        mat = align(series, dates)
        res = backtest(const_weights({"A": 1.0}), mat, dates,
                       start_cash=100_000.0, fee_bps=50, slip_bps=50)
        for c in res["curve"]:
            self.assertGreater(c["eq"], 0)


if __name__ == "__main__":
    unittest.main()
