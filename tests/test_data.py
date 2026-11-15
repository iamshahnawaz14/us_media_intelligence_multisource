import unittest
from generate_data import build_rows


class SyntheticDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_rows()

    def test_nonempty_dataset(self):
        self.assertGreater(len(self.rows), 1000)

    def test_reproducible_data(self):
        self.assertEqual(self.rows[:5], build_rows()[:5])

    def test_all_values_valid(self):
        for row in self.rows:
            self.assertGreater(row["viewers"], 0)
            self.assertGreaterEqual(row["impressions"], row["viewers"])
            self.assertGreaterEqual(row["rating_pct"], 0)
            self.assertLessEqual(row["rating_pct"], 100)
            self.assertEqual(row["data_source"], "Synthetic demo data")

    def test_unique_observations(self):
        keys = [(r["date"], r["region"], r["network"], r["program"]) for r in self.rows]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
