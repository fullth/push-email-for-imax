import logging
import os
import time

from .check_once import main as check_once

LOGGER = logging.getLogger(__name__)


def main() -> None:
    interval = int(os.getenv("CGV_POLL_INTERVAL_SECONDS", "60"))
    LOGGER.info("Railway worker started interval=%ss", interval)
    while True:
        try:
            check_once()
        except Exception:
            LOGGER.exception("check failed")
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
