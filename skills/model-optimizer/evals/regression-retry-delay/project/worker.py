from time import sleep
from settings import RETRY_DELAY_MS


def wait_before_retry():
    sleep(RETRY_DELAY_MS)
