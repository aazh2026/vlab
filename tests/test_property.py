# -*- coding: utf-8 -*-
"""房产模块回归测试 / Property module regression tests.

这些用例钉死"持币 vs 持房"计算里的每一个易错点，
和策略回测的测试一样，是这个仓库最有价值的资产。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))

from vlab import property as P   # noqa: E402


class TestMonthGrid(unittest.TestCase):
    """月份轴必须连续、且含首尾月。"""

    def test_basic(self):
        m = P.month_grid("2026-01-01", "2026-04-01")
        self.assertEqual(m, ["2026-01", "2026-02", "2026-03", "2026-04"])
        self.assertEqual(len(m), 4)

    def test_crosses_year(self):
        m = P.month_grid("2025-11-01", "2026-02-01")
        self.assertEqual(m, ["2025-11", "2025-12", "2026-01", "2026-02"])

    def test_single_month(self):
        self.assertEqual(P.month_grid("2026-03-01", "2026-03-01"),
                         ["2026-03"])

    def test_months_between(self):
        self.assertEqual(P.months_between("2026-01-01", "2026-12-01"), 12)
        self.assertEqual(P.months_between("2026-01-01", "2026-01-01"), 1)


class TestMortgage(unittest.TestCase):
    """等额本息：月供、期末余额、利息总额。"""

    def test_payment_matches_formula(self):
        p, rate, years = 1_000_000.0, 0.03, 30
        m = P.mortgage_payment(p, rate, years)
        r = rate / 12.0
        n = years * 12
        expect = p * r * (1 + r) ** n / ((1 + r) ** n - 1)
        self.assertAlmostEqual(m, expect, places=6)

    def test_zero_rate_is_principal_only(self):
        m = P.mortgage_payment(120_000.0, 0.0, 10)
        self.assertAlmostEqual(m, 1000.0, places=6)

    def test_amortization_ends_at_zero(self):
        rows = P.amortization(1_000_000.0, 0.03, 30)
        self.assertEqual(len(rows), 360)
        self.assertAlmostEqual(rows[-1]["balance"], 0.0, places=6)

    def test_principal_sums_to_loan(self):
        loan = 1_000_000.0
        rows = P.amortization(loan, 0.035, 20)
        self.assertAlmostEqual(sum(r["principal"] for r in rows), loan, places=4)

    def test_interest_decreases_over_time(self):
        rows = P.amortization(1_000_000.0, 0.04, 30)
        self.assertGreater(rows[0]["interest"], rows[-1]["interest"])

    def test_payment_stable_except_last(self):
        rows = P.amortization(1_000_000.0, 0.03, 30)
        self.assertAlmostEqual(rows[0]["payment"], rows[100]["payment"], places=6)

    def test_last_payment_clears_balance(self):
        """末期月供可以与之前不同，但必须把余额还清。"""
        rows = P.amortization(500_000.0, 0.028, 15)
        self.assertAlmostEqual(rows[-1]["balance"], 0.0, places=6)
        self.assertGreaterEqual(rows[-1]["payment"], rows[0]["payment"] - 1)


class TestPricePath(unittest.TestCase):
    """房价路径必须按月复利，且起点等于 p0。"""

    def test_starts_at_p0(self):
        vals = P.property_value_path(1_000_000.0, 0.02,
                                     P.month_grid("2026-01-01", "2026-12-01"),
                                     "2026-01-01")
        self.assertAlmostEqual(vals[0], 1_000_000.0, places=6)

    def test_annual_growth_over_12_months(self):
        months = P.month_grid("2026-01-01", "2027-01-01")
        vals = P.property_value_path(1_000_000.0, 0.03, months, "2026-01-01")
        # 13 个月度点，最后一个正好是 12 个月之后
        self.assertAlmostEqual(vals[-1] / vals[0], 1.03, places=4)

    def test_monotonic_increasing(self):
        months = P.month_grid("2026-01-01", "2028-01-01")
        vals = P.property_value_path(1_000_000.0, 0.02, months, "2026-01-01")
        self.assertEqual(vals, sorted(vals))


class TestCompare(unittest.TestCase):
    """持币 vs 持房的核心守恒关系。"""

    def setUp(self):
        self.a = dict(P.ASSUMPTIONS)
        self.p0 = self.a["price_per_sqm"] * self.a["area_sqm"]
        self.months = P.month_grid("2026-01-01", "2029-01-01")

    def test_cash_initial_equals_down_plus_buy_cost(self):
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        self.assertAlmostEqual(r["cash_series"][0],
                               r["down_payment"] + r["buy_cost"], places=6)

    def test_loan_plus_down_equals_price(self):
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        self.assertAlmostEqual(r["loan"] + r["down_payment"], self.p0, places=4)

    def test_cash_grows_at_cash_apy(self):
        """无房无贷时，现金侧应严格按 cash_apy 月复利增长。"""
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        rate = self.a["cash_apy"] / 12.0
        self.assertAlmostEqual(r["cash_series"][1], r["cash_series"][0] * (1 + rate),
                               places=4)

    def test_house_equity_definition(self):
        """持房总财富 = 市值 - 剩余贷款 + 累计净现金流。"""
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        self.assertAlmostEqual(r["house_equity"][0],
                               r["price_path"][0] - r["loan"], places=6)

    def test_diff_is_house_minus_cash(self):
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        for i in range(len(self.months)):
            self.assertAlmostEqual(r["diff"][i],
                                   r["house_equity"][i] - r["cash_series"][i],
                                   places=6)

    def test_no_recursion(self):
        """求解器嵌套调用不得无限递归（回归保护）。"""
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        self.assertIsNotNone(r["final_diff"])

    def test_breakeven_rent_makes_diff_zero(self):
        """用保本租金回代，终值差额应接近 0。"""
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        be = r["breakeven_rent"]
        self.assertIsNotNone(be)
        r2 = P.compare(self.months, "2026-01-01", self.p0, be, self.a,
                       price_growth=r["price_growth"])
        self.assertAlmostEqual(r2["final_diff"], 0.0, delta=max(abs(r["final_diff"]) * 0.05, 1.0))

    def test_breakeven_growth_makes_diff_zero(self):
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        g = r["breakeven_price_growth"]
        self.assertIsNotNone(g)
        r2 = P.compare(self.months, "2026-01-01", self.p0,
                       self.a["monthly_rent"], self.a, price_growth=g)
        self.assertAlmostEqual(r2["final_diff"], 0.0, delta=max(abs(r["final_diff"]) * 0.05, 1.0))

    def test_carry_is_net_yield_minus_rate(self):
        r = P.compare(self.months, "2026-01-01", self.p0,
                      self.a["monthly_rent"], self.a)
        self.assertAlmostEqual(r["carry"],
                               r["net_rent_yield"] - self.a["mortgage_rate"],
                               places=9)

    def test_higher_rent_improves_house_side(self):
        lo = P.compare(self.months, "2026-01-01", self.p0, 5000.0, self.a)
        hi = P.compare(self.months, "2026-01-01", self.p0, 7000.0, self.a)
        self.assertGreater(hi["final_house"], lo["final_house"])

    def test_lower_price_improves_cash_side_ratio(self):
        """同样的租金，买入价越低，租售比越高，carry 越不负。"""
        hi = P.compare(self.months, "2026-01-01", self.p0 * 1.2,
                       self.a["monthly_rent"], self.a)
        lo = P.compare(self.months, "2026-01-01", self.p0 * 0.8,
                       self.a["monthly_rent"], self.a)
        self.assertGreater(lo["net_rent_yield"], hi["net_rent_yield"])

    def test_requires_two_months(self):
        with self.assertRaises(ValueError):
            P.compare(["2026-01"], "2026-01-01", self.p0, 6000.0, self.a)


class TestSensitivity(unittest.TestCase):
    """敏感性网格：结论必须在参数区间内一致才稳健。"""

    def setUp(self):
        self.a = dict(P.ASSUMPTIONS)
        self.months = P.month_grid("2026-01-01", "2029-01-01")

    def test_grid_shape(self):
        s = P.sensitivity(self.months, "2026-01-01", self.a)
        self.assertEqual(len(s["grid"]), len(s["prices"]) * len(s["rents"]))
        for row in s["grid"]:
            self.assertEqual(len(row["cells"]), len(s["rates"]))

    def test_sign_flag_is_consistent(self):
        s = P.sensitivity(self.months, "2026-01-01", self.a)
        if s["all_same_sign"]:
            self.assertTrue(s["sign_positive_count"] in (0, s["total"]))
        else:
            self.assertTrue(0 < s["sign_positive_count"] < s["total"])

    def test_monotonic_in_rent(self):
        """同一价格下，租金越高差额越大（网格内可验证）。"""
        s = P.sensitivity(self.months, "2026-01-01", self.a,
                          rents=[0.8, 1.2], prices=[1.0], rates=[0.03])
        lo = s["grid"][0]["cells"][0]["final_diff"]
        hi = s["grid"][1]["cells"][0]["final_diff"]
        self.assertGreater(hi, lo)


class TestMonthlyReturns(unittest.TestCase):
    """日频净值 -> 月频收益率。"""

    def test_monthly_returns_from_flat_equity(self):
        eq = [100.0] * 300
        dates = ["2026-%02d-%02d" % (1 + i // 28, 1 + i % 28)
                 for i in range(300)]
        mr = P.monthly_returns_from_equity(eq, dates)
        for r in mr:
            self.assertAlmostEqual(r, 0.0, places=9)

    def test_monthly_returns_compound(self):
        """首月为基期返回 0；此后每月是相对上月的收益率。"""
        eq = [100.0, 110.0, 121.0]
        dates = ["2026-01-01", "2026-02-01", "2026-03-01"]
        mr = P.monthly_returns_from_equity(eq, dates)
        self.assertEqual(len(mr), 3)
        self.assertAlmostEqual(mr[0], 0.0, places=9)   # 基期
        self.assertAlmostEqual(mr[1], 0.10, places=9)   # 100 -> 110
        self.assertAlmostEqual(mr[2], 0.10, places=9)   # 110 -> 121

    def test_average_monthly_return(self):
        """均值只统计基期之后的月份（这里是 1 月->2 月、2 月->3 月两段）。"""
        eq = [100.0, 101.0, 102.0]
        dates = ["2026-01-01", "2026-02-01", "2026-03-01"]
        expect = ((101.0 / 100.0 - 1.0) + (102.0 / 101.0 - 1.0)) / 2.0
        self.assertAlmostEqual(P.average_monthly_return(eq, dates),
                               expect, places=9)


class TestBuildSection(unittest.TestCase):
    """面板区块构建。"""

    def test_builds_with_downsampling(self):
        r = P.build_property_section("2026-01-01", 5)
        self.assertEqual(len(r["months_downsampled"]),
                         len(r["cash_downsampled"]))
        self.assertEqual(len(r["months_downsampled"]),
                         len(r["house_downsampled"]))
        self.assertEqual(len(r["months_downsampled"]),
                         len(r["diff_downsampled"]))

    def test_carries_disclaimer(self):
        r = P.build_property_section("2026-01-01", 3)
        self.assertIn("不构成", r["note_zh"])
        self.assertIn("not decision-grade", r["note_en"])

    def test_includes_sensitivity(self):
        r = P.build_property_section("2026-01-01", 3)
        self.assertIn("sensitivity", r)
        self.assertIn("all_same_sign", r["sensitivity"])


if __name__ == "__main__":
    unittest.main()
