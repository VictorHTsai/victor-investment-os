import unittest
from scripts.build_ai_market_snapshot import rsi, summarize, exploratory_analogs

class DailyMetricsTests(unittest.TestCase):
    def test_rsi_uptrend(self):
        self.assertEqual(rsi([float(x) for x in range(20)]), 100.0)
    def test_rsi_flat(self):
        self.assertEqual(rsi([10.0] * 20), 50.0)
    def test_insufficient_bars(self):
        self.assertIsNone(rsi([1.0, 2.0]))
        with self.assertRaises(ValueError):
            summarize([1.0, 2.0], [1, 2])
    def test_exploratory_insufficient(self):
        self.assertEqual(exploratory_analogs([100.0] * 200)["status"], "insufficient")

    def test_exploratory_nonoverlap_and_no_future_leak(self):
        prices = [100.0 + (i % 120) * 0.1 for i in range(900)]
        result = exploratory_analogs(prices)
        self.assertLessEqual(result["count"], 7)
        self.assertIn(result["status"], ("insufficient", "exploratory"))
        self.assertEqual(result["method"].split(";")[1].strip(), "90-session non-overlap")

    def test_drawdown(self):
        result = summarize([100.0] * 19 + [80.0], list(range(1, 21)))
        self.assertEqual(result["drawdown_52w_pct"], -20.0)
        self.assertIsNone(result["oversold_score"])

if __name__ == "__main__":
    unittest.main()
