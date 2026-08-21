import unittest
from unittest.mock import patch
from worker import wait_before_retry


class RetryDelayTests(unittest.TestCase):
    @patch("worker.sleep")
    def test_delay_is_quarter_second(self, mocked_sleep):
        wait_before_retry()
        mocked_sleep.assert_called_once_with(0.25)
