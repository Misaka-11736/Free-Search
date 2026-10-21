import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("evaluate", Path(__file__).parents[1] / "scripts/evaluate.py")
evaluate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluate)


class FileMetricsTest(unittest.TestCase):
    def test_chunk_duplicates_do_not_change_file_rank(self):
        metrics = evaluate.file_metrics(
            [{"path": "miss"}, {"path": "miss"}, {"path": "target"}],
            [{"path": "target"}, {"path": "other_target"}],
        )
        self.assertEqual(metrics["mrr_at_10"], 0.5)
        self.assertEqual(metrics["recall_at_10"], 0.5)
        self.assertEqual(metrics["hit_at_5"], 1.0)

    def test_no_hit_and_cutoff(self):
        results = [{"path": f"file{i}"} for i in range(11)]
        metrics = evaluate.file_metrics(results, [{"path": "file10"}])
        self.assertEqual(metrics["mrr_at_10"], 0.0)
        self.assertEqual(metrics["hit_at_5"], 0.0)
        self.assertEqual(metrics["recall_at_10"], 0.0)

    def test_empty_expected_is_not_a_retrieval_success(self):
        with self.assertRaises(ValueError):
            evaluate.file_metrics([], [])


if __name__ == "__main__":
    unittest.main()
