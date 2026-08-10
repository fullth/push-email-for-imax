import json
import logging
import xml.etree.ElementTree as ET
from typing import Any

import requests

from .models import Screening, Seat

LOGGER = logging.getLogger(__name__)


def parse_current_seats(payload: dict[str, Any]) -> tuple[Seat, ...]:
    """Convert CGV's current searchIfSeatData response to mail-ready seats."""
    data = payload.get("data") if isinstance(payload, dict) else None
    items = data.get("items", []) if isinstance(data, dict) else []
    seats: list[Seat] = []
    for item in items:
        for raw in item.get("seats", []):
            status_code = str(raw.get("seatStusCd", ""))
            # CGV uses seatStusCd=01 for a seat that exists, not an available seat.
            # The actual selectable state is seatSaleYn=Y; status 00 + N is not selectable.
            status = "available" if raw.get("seatSaleYn") == "Y" else "occupied" if status_code == "01" else "blocked"
            seats.append(
                Seat(
                    row=str(raw.get("seatRowNm", "?")),
                    number=int(raw.get("seatNo", 0)),
                    status=status,
                    x=int(raw.get("xcoordStartVal", 0)),
                    y=int(raw.get("ycoordStartVal", 0)),
                    kind=str(raw.get("stkndExpoNm", "일반석")),
                    zone=str(raw.get("szoneExpoNm", "")),
                )
            )
    return tuple(seats)


def _text(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        child = element.find(f".//{name}")
        if child is not None and child.text:
            return child.text.strip()
    return ""


def _xml_from_response(payload: Any) -> str | None:
    if isinstance(payload, str) and payload.lstrip().startswith("<"):
        return payload
    if isinstance(payload, dict):
        data = payload.get("d", {}).get("DATA") if isinstance(payload.get("d"), dict) else None
        if isinstance(data, str):
            return data
    return None


def parse_screenings(response: requests.Response) -> list[Screening]:
    payload: Any
    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    xml_text = _xml_from_response(payload)
    if not xml_text:
        raise ValueError("CGV response did not contain XML schedule data")

    root = ET.fromstring(xml_text)
    result: list[Screening] = []
    for index, element in enumerate(root.iter()):
        date = _text(element, ("FORMAT_DATE", "PLAY_YMD", "PLAY_DATE", "PLAY_DT"))
        time = _text(element, ("PLAY_START_TM", "PLAY_START_TIME", "START_TIME"))
        if not date or not time:
            continue
        theater = _text(element, ("THEATER_NM", "THEATER_NAME"))
        screen = _text(element, ("SCREEN_NM", "SCREEN_NAME", "SCREEN_CD"))
        movie = _text(element, ("MOVIE_GROUP_NM", "MOVIE_NM", "MOVIE_NAME"))
        result.append(Screening(theater, screen, movie, date, time, str(index)))

    unique = {screening.key: screening for screening in result}
    return list(unique.values())


class CGVClient:
    def __init__(self, endpoint: str, request_json: dict, headers: dict, cookies: dict, timeout: int) -> None:
        self.endpoint = endpoint
        self.request_json = request_json
        self.headers = headers
        self.cookies = cookies
        self.timeout = timeout

    def fetch(self) -> list[Screening]:
        response = requests.post(
            self.endpoint,
            json=self.request_json,
            headers=self.headers,
            cookies=self.cookies,
            timeout=self.timeout,
        )
        response.raise_for_status()
        LOGGER.info("CGV response status=%s bytes=%s", response.status_code, len(response.content))
        return parse_screenings(response)
