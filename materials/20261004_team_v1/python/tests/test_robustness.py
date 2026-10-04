import unittest
import unicodedata

from scamlens.robustness import generate_variants


class RobustnessTests(unittest.TestCase):
    def test_variants_are_named_and_reproducible(self):
        variants = generate_variants("배송지 확인")
        self.assertEqual(variants["original"], "배송지 확인")
        self.assertIn(" ", variants["space_insertion"])
        self.assertIn("·", variants["symbol_insertion"])
        self.assertTrue(unicodedata.is_normalized("NFD", variants["jamo_decomposition"]))


if __name__ == "__main__":
    unittest.main()
