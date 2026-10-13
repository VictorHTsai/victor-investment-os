import unittest
from scripts.build_ai_market_snapshot import rsi, summarize, exploratory_analogs
from scripts.ai_analog_validation import selected_analog_indices, validate_analogs

class DailyMetricsTests(unittest.TestCase):
    def test_rsi_uptrend(self):
        self.assertEqual(rsi([float(x) for x in range(20)]), 100.0)
    def test_rsi_flat(self):
        self.assertEqual(rsi([10.0] * 20), 50.0)
    def test_insufficient_bars(self):
        self.assertIsNone(rsi([1.0, 2.0]))
        with self.assertRaises(ValueError):
            summarize([1.0, 2.0], [1, 2])
    def test_drawdown(self):
        result = summarize([100.0] * 19 + [80.0], list(range(1, 21)))
        self.assertEqual(result["drawdown_52w_pct"], -20.0)
        self.assertIsNone(result["oversold_score"])
    def test_exploratory_insufficient(self):
        self.assertEqual(exploratory_analogs([100.0] * 200)["status"], "insufficient")
    def test_exploratory_nonoverlap_and_no_future_leak(self):
        prices = [100.0 + (i % 120) * 0.1 for i in range(900)]
        result = exploratory_analogs(prices)
        self.assertLessEqual(result["count"], 7)
        self.assertIn(result["status"], ("insufficient", "exploratory"))
        self.assertIn("90-session non-overlap", result["method"])
    def test_benchmark_zero_excess_for_identical_history(self):
        prices = [100.0 + (i % 130) * 0.12 for i in range(1100)]
        dates = [1600000000 + i * 86400 for i in range(len(prices))]
        result = validate_analogs(prices, dates, {"QQQ": (dates, prices)}, rsi)
        self.assertEqual(result["status"], "exploratory")
        for h in ("30", "60", "90"):
            self.assertEqual(result["benchmarks"]["QQQ"][h]["excess_median_pp"], 0)
            self.assertEqual(result["benchmarks"]["QQQ"][h]["outperform_pct"], 0)
    def test_missing_benchmark_days_are_not_filled(self):
        prices = [100.0 + (i % 130) * 0.12 for i in range(1100)]
        dates = [1600000000 + i * 86400 for i in range(len(prices))]
        result = validate_analogs(prices, dates, {"SMH": ([], [])}, rsi)
        self.assertEqual(result["status"], "exploratory")
        self.assertEqual(result["benchmarks"]["SMH"]["90"]["status"], "insufficient")
    def test_no_future_tail_selection(self):
        prices = [100.0 + (i % 130) * 0.12 for i in range(1100)]
        inds = selected_analog_indices(prices, rsi)
        self.assertTrue(all(i + 90 < len(prices) for i in inds))
        self.assertTrue(all(j - i >= 90 for i,j in zip(inds,inds[1:])))

if __name__ == "__main__":
    unittest.main()
