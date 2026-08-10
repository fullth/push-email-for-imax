import logging
import time

from .cgv import CGVClient
from .config import Settings
from .mailer import send_screenings
from .state import StateStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def main() -> None:
    settings = Settings.from_env()
    client = CGVClient(
        settings.cgv_endpoint,
        settings.cgv_request,
        settings.cgv_headers,
        settings.cgv_cookies,
        settings.timeout_seconds,
    )
    state = StateStore(settings.state_path)
    initialized = False

    while True:
        try:
            screenings = client.fetch()
            new_screenings = state.unseen(screenings)
            state.save(screenings)
            if initialized:
                send_screenings(settings, new_screenings)
                LOGGER.info("screenings=%s new=%s", len(screenings), len(new_screenings))
            else:
                initialized = True
                LOGGER.info("initial state saved screenings=%s", len(screenings))
        except Exception:
            LOGGER.exception("poll failed")
        time.sleep(settings.poll_interval_seconds)
