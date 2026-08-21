import unittest
from service import startup_config


class StartupConfigTests(unittest.TestCase):
    def test_default_timeout_is_five_seconds(self):
        self.assertEqual(startup_config()["timeout"], 5.0)

    def test_retry_count_is_preserved(self):
        self.assertEqual(startup_config()["retries"], 3)
