import unittest

from scamlens.url_features import lexical_features


class UrlFeatureTests(unittest.TestCase):
    def test_ip_and_suspicious_tokens(self):
        features = lexical_features("hxxp://192.0.2.10/login/verify")
        self.assertEqual(features["has_ip_literal"], 1)
        self.assertGreaterEqual(features["suspicious_token_count"], 2)
        self.assertEqual(features["path_depth"], 2)

    def test_defanged_url_is_parseable_offline(self):
        features = lexical_features("hxxps://secure-check[.]invalid/update")
        self.assertEqual(features["has_ip_literal"], 0)
        self.assertGreater(features["hostname_length"], 0)

    def test_malformed_url_is_flagged_without_crashing(self):
        features = lexical_features("http://[not-an-ipv6]/login")
        self.assertEqual(features["is_malformed"], 1)

    def test_scheme_and_root_slash_do_not_change_features(self):
        bare = lexical_features("example.invalid")
        full = lexical_features("https://example.invalid/")
        self.assertEqual(bare, full)


if __name__ == "__main__":
    unittest.main()
