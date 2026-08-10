import smtplib
from collections import defaultdict
from email.message import EmailMessage
from html import escape

from .config import Settings
from .models import Screening, Seat


def _seat_class(seat: Seat) -> str:
    return {
        "available": "seat available",
        "occupied": "seat occupied",
        "blocked": "seat blocked",
        "aisle": "seat aisle",
    }.get(seat.status, "seat unknown")


def _seat_style(status: str) -> str:
    colors = {
        "available": ("#2196f3", "#ffffff"),
        "occupied": ("#3b3b3b", "#ffffff"),
        "blocked": ("#9ca3af", "#ffffff"),
        "unknown": ("#f59e0b", "#ffffff"),
    }
    background, color = colors.get(status, colors["unknown"])
    return (
        f"background-color:{background};color:{color};width:18px;height:18px;"
        "padding:0;text-align:center;border-radius:3px;font-size:9px;line-height:18px"
    )


def _seat_map_html(seats: tuple[Seat, ...]) -> str:
    if not seats:
        return ""
    # CGV coordinates are two-digit cells; retaining them preserves the three
    # IMAX seat blocks and the side seats instead of flattening every row.
    positions = {(seat.y // 2, seat.x // 2): seat for seat in seats}
    max_x = max(x for _, x in positions) + 1
    max_y = max(y for y, _ in positions) + 1
    body = []
    for y in range(max_y):
        cells = []
        for x in range(max_x):
            seat = positions.get((y, x))
            if seat is None:
                cells.append('<td style="width:18px;height:18px;padding:0" aria-hidden="true"></td>')
                continue
            cells.append(
                f'<td style="{_seat_style(seat.status)}" title="{escape(seat.label)} '
                f'({escape(seat.kind)})">{escape(str(seat.number))}</td>'
            )
        body.append(f'<tr><th style="width:4px;padding:2px 4px" scope="row"></th>{"".join(cells)}</tr>')
    return (
        '<div style="overflow-x:auto"><div style="margin:8px auto 12px;max-width:440px;'
        'padding:5px;text-align:center;background-color:#111;color:#fff;border-radius:3px;'
        'font-size:11px;letter-spacing:2px">SCREEN</div>'
        '<table style="border-collapse:separate;border-spacing:2px;margin:0 auto 12px">'
        '<caption style="text-align:left;font-weight:bold;margin-bottom:6px">좌석 배치도</caption><tbody>'
        + "".join(body)
        + '</tbody></table><p style="font-size:12px">'
        '<span style="display:inline-block;margin-right:12px"><i style="display:inline-block;width:12px;'
        'height:12px;border-radius:3px;vertical-align:-2px;margin-right:4px;background-color:#2196f3"></i>예매 가능</span>'
        '<span style="display:inline-block;margin-right:12px"><i style="display:inline-block;width:12px;'
        'height:12px;border-radius:3px;vertical-align:-2px;margin-right:4px;background-color:#3b3b3b"></i>예매됨</span>'
        '<span style="display:inline-block"><i style="display:inline-block;width:12px;height:12px;'
        'border-radius:3px;vertical-align:-2px;margin-right:4px;background-color:#9ca3af"></i>선택 불가</span>'
        "</p></div>"
    )


def _html_body(screenings: list[Screening]) -> str:
    cards = []
    for item in screenings:
        cards.append(
            '<section class="screening">'
            f"<h2>{escape(item.movie)}</h2>"
            f"<p>{escape(item.date)} {escape(item.time)} · "
            f"{escape(item.theater)} · {escape(item.screen)}</p>"
            + (
                f'<p><a href="{escape(item.booking_url, quote=True)}" '
                'style="display:inline-block;padding:9px 14px;background:#e50914;'
                'color:#fff;text-decoration:none;border-radius:6px">예매 화면 열기</a></p>'
                if item.booking_url
                else ""
            ) + f"{_seat_map_html(item.seats)}</section>"
        )
    return """<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222">
<h1>새로운 CGV 상영 일정</h1>""" + "".join(cards) + """
<style>
.screening{margin:20px 0;padding:16px;border:1px solid #ddd;border-radius:10px}
.seat-map-wrap{overflow-x:auto}.screen-label{margin:8px auto 12px;max-width:440px;padding:5px;text-align:center;background:#111;color:#fff;border-radius:3px;font-size:11px;letter-spacing:2px}.seat-map{border-collapse:separate;border-spacing:2px;margin:0 auto 12px}
.seat-map caption{text-align:left;font-weight:bold;margin-bottom:6px}.seat-map th{padding:2px 4px}.seat-axis{width:4px}
.seat{width:28px;height:28px;text-align:center;border-radius:5px;font-size:11px}
.seat-gap{width:10px;height:10px;padding:0}
.available{background:#4caf50;color:#fff}.occupied{background:#e5e7eb;color:#9ca3af}
.blocked{background:#374151;color:#fff}.unknown{background:#f59e0b;color:#fff}
.legend{font-size:12px}.legend-item{margin-right:12px}.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-2px;margin-right:4px}
</style></body></html>"""


def send_screenings(settings: Settings, screenings: list[Screening]) -> None:
    if not screenings:
        return
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = settings.mail_to
    message["Subject"] = f"{settings.mail_subject_prefix} {len(screenings)}건"
    lines = ["새로운 CGV 상영 일정이 등록되었습니다.", ""]
    for item in screenings:
        lines.append(f"- {item.date} {item.time} | {item.theater} | {item.screen} | {item.movie}")
        if item.booking_url:
            lines.append(f"  예매: {item.booking_url}")
    message.set_content("\n".join(lines))
    message.add_alternative(_html_body(screenings), subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.timeout_seconds) as client:
        if settings.smtp_use_tls:
            client.starttls()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
