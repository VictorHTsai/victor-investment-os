import unittest
from scripts.build_ai_market_snapshot import rsi, summarize, exploratory_analogs, validate_daily_cadence
from scripts.ai_analog_validation import selected_analog_indices, validate_analogs
from scripts.ai_walkforward import walk_forward_diagnostic
from scripts.ai_rebound_study import rebound_study, first_passage, scan_dislocations
from scripts.ai_price_volume_experiment import compare_price_volume, relative_volume

class DailyMetricsTests(unittest.TestCase):
    def test_rvol_does_not_use_future_or_current_in_denominator(self):
        vols = [100.0] * 20 + [200.0] + [300.0] * 10
        self.assertEqual(relative_volume(vols, 20), 2.0)
        self.assertIsNone(relative_volume(vols, 19))

    def test_missing_volume_keeps_price_model_untouched(self):
        prices = [100.0 + (i % 45) for i in range(1000)]
        result = compare_price_volume(prices, [None] * 1000, rsi)
        self.assertEqual(result["status"], "insufficient")
        self.assertEqual(result["decision"], "undetermined")
        self.assertFalse(result["volume_available"])

    def test_price_volume_challenger_cannot_auto_promote(self):
        prices = [100.0 + (i % 120) * 0.1 for i in range(1100)]
        volumes = [100.0] * 1100
        result = compare_price_volume(prices, volumes, rsi)
        self.assertEqual(result["decision"], "undetermined")
        self.assertTrue(result["volume_available"])
        self.assertLessEqual(result["price_volume_n"], result["price_only_n"])

    def test_daily_cadence_rejects_monthly_downsampling(self):
        with self.assertRaisesRegex(ValueError, "daily frequency integrity"):
            validate_daily_cadence([i * 30 * 86400 for i in range(181)])

    def test_daily_cadence_accepts_weekend_gaps(self):
        validate_daily_cadence([i * 86400 for i in range(30)])

    def test_daily_cadence_rejects_too_few_bars(self):
        with self.assertRaisesRegex(ValueError, "insufficient daily bars"):
            validate_daily_cadence([0, 86400])

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
    def test_walkforward_short_history(self):
        result = walk_forward_diagnostic([100.0] * 400)
        self.assertEqual(result["status"], "insufficient")

    def test_walkforward_frozen_train_and_no_future_entries(self):
        prices = [100 + 5 * __import__("math").sin(i / 20) + i * 0.01 for i in range(1300)]
        result = walk_forward_diagnostic(prices)
        self.assertGreater(result["train_bars"], 0)
        self.assertGreater(result["test_bars"], 0)
        self.assertIn(result["status"], ("insufficient", "exploratory_holdout"))
        self.assertLessEqual(result["signal_events"], result["unconditional_events"] + 1)
        self.assertIn("frozen_thresholds", result)

    def test_first_passage_target_before_stop(self):
        self.assertEqual(first_passage([100, 96, 111, 80], 0, 3, 10, -10), ("profit", 2))
        self.assertEqual(first_passage([100, 89, 120, 120], 0, 3, 10, -10), ("stop", 1))
        self.assertEqual(first_passage([100, 101, 102, 103], 0, 3, 10, -10), ("neither", None))

    def test_rebound_insufficient_history(self):
        self.assertEqual(rebound_study([100.] * 100, rsi)["status"], "insufficient")

    def test_rebound_dislocation_spacing_and_forward_window(self):
        prices = [100.0] * 260 + [max(15., 99. - (i % 85) * 1.0) for i in range(450)]
        events = scan_dislocations(prices, rsi)
        self.assertTrue(all(j - i >= 30 for i, j in zip(events, events[1:])))
        self.assertTrue(all(i + 30 < len(prices) for i in events))
        result = rebound_study(prices, rsi)
        self.assertEqual(result["count"], len(events))
        self.assertIn(result["status"], ("exploratory", "insufficient"))

    def test_no_future_tail_selection(self):
        prices = [100.0 + (i % 130) * 0.12 for i in range(1100)]
        inds = selected_analog_indices(prices, rsi)
        self.assertTrue(all(i + 90 < len(prices) for i in inds))
        self.assertTrue(all(j - i >= 90 for i,j in zip(inds,inds[1:])))

if __name__ == "__main__":
    unittest.main()
