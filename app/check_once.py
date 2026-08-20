import os
import re
import logging
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta

import requests

from .cgv import parse_current_seats
from .config import Settings
from .mailer import send_ntfy, send_screenings
from .models import Screening
from .state import StateStore

CGV_BASE = "https://cgv.co.kr/api/v1"
CO_CD = "A420"
LOGGER = logging.getLogger(__name__)


def _field(body: str, name: str) -> str:
    match = re.search(rf"^### {re.escape(name)}\s*$\n+\s*(.+?)\s*(?=^### |\Z)", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _row_range(body: str) -> tuple[str, str]:
    raw = _field(body, "관심 행 범위") or _field(body, "최소 관심 행")
    values = [value.strip().upper() for value in re.split(r"[-~]", raw) if value.strip()]
    return (values[0], values[-1] if len(values) > 1 else values[0]) if values else ("A", "Z")


def _get(path: str, params: dict[str, str]) -> dict:
    response = requests.get(
        f"{CGV_BASE}{path}",
        params=params,
        headers={
            "Accept": "application/json",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://cgv.co.kr/cnm/movieBook/movie",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("statusCode") not in (0, "0", None):
        raise RuntimeError(f"CGV API error: {payload.get('statusMessage')}")
    return payload


def _dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _dicts(child)


def _movie_no(movie: str, attr_cd: str) -> str | None:
    data = list(_dicts(_get("/booking/searchAtktTopPostrList", {"coCd": CO_CD, "movNm": movie, "div": "", "attrCd": attr_cd}).get("data")))
    candidates = [item for item in data if item.get("movNo")]
    match = next((item for item in candidates if item.get("movNm") == movie), None)
    if not match:
        LOGGER.info("upcoming movie is not listed yet: %s", movie)
        return None
    return str(match["movNo"])


def _site_no(theater: str) -> str:
    data = list(_dicts(_get("/content/site/searchAllRegionAndSite", {"coCd": CO_CD}).get("data")))
    candidates = [item for item in data if item.get("siteNo") and item.get("siteNm")]
    match = next((item for item in candidates if item.get("siteNm") == theater or item.get("siteNm", "").endswith(theater)), None)
    if not match:
        raise RuntimeError(f"극장을 찾을 수 없습니다: {theater}")
    return str(match["siteNo"])


def _dates(schedule: str) -> list[str]:
    found = re.findall(r"20\d{2}-\d{2}-\d{2}", schedule)
    if found:
        return found
    today = date.today()
    if "주말" in schedule:
        weekdays = {5, 6}
    elif "평일" in schedule:
        weekdays = {0, 1, 2, 3, 4}
    elif schedule.strip() == "전체":
        weekdays = set(range(7))
    else:
        weekdays = {5, 6}
    return [(today + timedelta(days=i)).isoformat() for i in range(14) if (today + timedelta(days=i)).weekday() in weekdays]


def _matching_seats(seats, minimum_row: str, maximum_row: str, consecutive: int) -> list[str]:
    rows: dict[str, list[int]] = {}
    for seat in seats:
        if seat.status != "available" or seat.row < minimum_row or seat.row > maximum_row:
            continue
        rows.setdefault(seat.row, []).append(seat.number)
    matches = []
    for row, numbers in rows.items():
        values = sorted(set(numbers))
        for start in values:
            group = list(range(start, start + consecutive))
            if all(number in values for number in group):
                matches.append(f"{row}{start}-{row}{start + consecutive - 1}")
    return matches


def _subscriptions() -> list[dict]:
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    response = requests.get(
        f"https://api.github.com/repos/{repo}/issues",
        params={"state": "open", "labels": "seat-alert", "per_page": "100"},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=20,
    )
    response.raise_for_status()
    subscriptions = []
    for issue in response.json():
        body = issue.get("body") or ""
        minimum_row, maximum_row = _row_range(body)
        subscriptions.append({
            "issue": issue["number"],
            "email": _field(body, "수신 이메일"),
            "movie": _field(body, "영화"),
            "theater": _field(body, "극장"),
            "screen": _field(body, "상영관"),
            "min_row": minimum_row,
            "max_row": maximum_row,
            "consecutive": int(_field(body, "필요한 연속 좌석 수") or _field(body, "필요한 연석 수") or "1"),
            "schedule": _field(body, "대상 회차"),
        })
    return subscriptions


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    state = StateStore(os.getenv("CGV_STATE_PATH", "/tmp/state.sqlite3"))
    subscriptions = _subscriptions()
    LOGGER.info("checking subscriptions=%d", len(subscriptions))
    pending: list[tuple[str, Screening]] = []
    for subscription in subscriptions:
        if not subscription["email"] or not subscription["movie"]:
            continue
        movie_no = _movie_no(subscription["movie"], "04" if "IMAX" in subscription["screen"].upper() else "")
        if not movie_no:
            continue
        site_no = _site_no(subscription["theater"])
        for day in _dates(subscription["schedule"]):
            payload = _get("/booking/searchSchByMov", {
                "coCd": CO_CD, "siteNo": site_no, "scnYmd": day.replace("-", ""),
                "scnsNo": "", "scnSseq": "", "movNo": movie_no, "prodNo": "",
                "rtctlScopCd": "08", "salsTznCd": "", "tcscnsGradCd": "", "sascnsGradCd": "", "custNo": "",
            })
            for item in payload.get("data") or []:
                if subscription["screen"].upper() not in item.get("scnsNm", "").upper() and subscription["screen"].upper() not in item.get("expoProdNm", "").upper():
                    continue
                start = item.get("scnsrtTm", "")
                requested = re.search(r"(\d{1,2}):(\d{2})", subscription["schedule"])
                if requested and start != f"{int(requested.group(1)):02d}{requested.group(2)}":
                    continue
                seat_payload = _get("/booking/searchIfSeatData", {
                    "coCd": CO_CD, "siteNo": site_no, "scnYmd": item["scnYmd"], "scnsNo": item["scnsNo"],
                    "scnSseq": item["scnSseq"], "movNo": item["movNo"], "prodNo": item["prodNo"], "custNo": "",
                })
                seats = parse_current_seats(seat_payload)
                matches = _matching_seats(seats, subscription["min_row"], subscription["max_row"], subscription["consecutive"])
                available_key = ",".join(
                    sorted(seat.label for seat in seats if seat.status == "available")
                )
                state_key = available_key if matches else "no-matching-seats"
                screening = Screening(
                    theater=item.get("siteNm", subscription["theater"]), screen=item.get("scnsNm", subscription["screen"]),
                    movie=item.get("expoProdNm", subscription["movie"]), date=item["scnYmd"], time=start,
                    source_key=f"{subscription['issue']}|{item['scnsNo']}|{item['scnSseq']}|{state_key}",
                    seats=seats, booking_url="https://cgv.co.kr/cnm/movieBook/movie",
                    alert_type="seat" if matches else "schedule",
                )
                pending.append((subscription["email"], screening))
    screenings = [screening for _, screening in pending]
    new = state.unseen(screenings)
    LOGGER.info("available screenings=%d newly_available=%d", len(screenings), len(new))
    if new:
        settings = Settings.from_env()
        new_keys = {screening.key for screening in new}
        recipients: dict[tuple[str, str], list[Screening]] = defaultdict(list)
        delivered = False
        for email, screening in pending:
            if screening.key in new_keys:
                recipients[(email, screening.alert_type)].append(screening)
        for (email, _alert_type), recipient_screenings in recipients.items():
            recipient_settings = replace(settings, mail_to=email)
            try:
                send_ntfy(recipient_settings, recipient_screenings)
                delivered = True
            except Exception:
                LOGGER.exception("ntfy notification failed")
            try:
                send_screenings(recipient_settings, recipient_screenings)
                delivered = True
            except Exception:
                # Railway may restrict outbound SMTP; keep ntfy as the primary
                # alert channel and do not lose the state transition.
                LOGGER.exception("email notification failed")
        if new and not delivered:
            LOGGER.warning("no notification channel succeeded; retaining state for retry")
            return
    # Do not mark seats as notified until every recipient's email succeeds.
    # A transient SMTP failure must be retried on the next workflow run.
    state.save(screenings)


if __name__ == "__main__":
    main()
