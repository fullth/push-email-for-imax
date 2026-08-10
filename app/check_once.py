import os
import re
from datetime import date, datetime, timedelta

import requests

from .cgv import parse_current_seats
from .config import Settings
from .mailer import send_screenings
from .models import Screening
from .state import StateStore

CGV_BASE = "https://cgv.co.kr/api/v1"
CO_CD = "A420"


def _field(body: str, name: str) -> str:
    match = re.search(rf"^### {re.escape(name)}\s*$\n+\s*(.+?)\s*(?=^### |\Z)", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _get(path: str, params: dict[str, str]) -> dict:
    response = requests.get(f"{CGV_BASE}{path}", params=params, headers={"Accept": "application/json"}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get("statusCode") not in (0, "0", None):
        raise RuntimeError(f"CGV API error: {payload.get('statusMessage')}")
    return payload


def _movie_no(movie: str, attr_cd: str) -> str:
    data = _get("/booking/searchAtktTopPostrList", {"coCd": CO_CD, "movNm": movie, "div": "", "attrCd": attr_cd}).get("data") or []
    match = next((item for item in data if item.get("movNm") == movie), data[0] if data else None)
    if not match:
        raise RuntimeError(f"영화를 찾을 수 없습니다: {movie}")
    return str(match["movNo"])


def _site_no(theater: str) -> str:
    data = _get("/content/site/searchAllRegionAndSite", {"coCd": CO_CD}).get("data") or []
    match = next((item for item in data if item.get("siteNm") == theater or item.get("siteNm", "").endswith(theater)), None)
    if not match:
        raise RuntimeError(f"극장을 찾을 수 없습니다: {theater}")
    return str(match["siteNo"])


def _dates(schedule: str) -> list[str]:
    found = re.findall(r"20\d{2}-\d{2}-\d{2}", schedule)
    if found:
        return found
    today = date.today()
    return [(today + timedelta(days=i)).isoformat() for i in range(14) if (today + timedelta(days=i)).weekday() >= 5]


def _matching_seats(seats, minimum_row: str, consecutive: int) -> list[str]:
    rows: dict[str, list[int]] = {}
    for seat in seats:
        if seat.status != "available" or seat.row < minimum_row:
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
        subscriptions.append({
            "issue": issue["number"],
            "email": _field(body, "수신 이메일"),
            "movie": _field(body, "영화"),
            "theater": _field(body, "극장"),
            "screen": _field(body, "상영관"),
            "min_row": _field(body, "최소 관심 행").upper(),
            "consecutive": int(_field(body, "필요한 연석 수") or "1"),
            "schedule": _field(body, "대상 회차"),
        })
    return subscriptions


def main() -> None:
    settings = Settings.from_env()
    state = StateStore(settings.state_path)
    screenings = []
    for subscription in _subscriptions():
        if not subscription["email"] or not subscription["movie"]:
            continue
        movie_no = _movie_no(subscription["movie"], "04" if "IMAX" in subscription["screen"].upper() else "")
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
                matches = _matching_seats(seats, subscription["min_row"], subscription["consecutive"])
                if not matches:
                    continue
                screening = Screening(
                    theater=item.get("siteNm", subscription["theater"]), screen=item.get("scnsNm", subscription["screen"]),
                    movie=item.get("expoProdNm", subscription["movie"]), date=item["scnYmd"], time=start,
                    source_key=f"{subscription['issue']}|{item['scnsNo']}|{item['scnSseq']}|{','.join(matches)}",
                    seats=seats, booking_url="https://cgv.co.kr/cnm/movieBook/movie",
                )
                screenings.append(screening)
    new = state.unseen(screenings)
    state.save(screenings)
    if new:
        send_screenings(settings, new)


if __name__ == "__main__":
    main()
