import logging
import os
import socket
import time

from .check_once import main as check_once

LOGGER = logging.getLogger(__name__)


def main() -> None:
    original_getaddrinfo = socket.getaddrinfo

    def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_getaddrinfo
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
