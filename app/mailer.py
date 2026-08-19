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
    return f"background:{background};color:{color};width:18px;height:18px;padding:0;text-align:center;font-size:9px"


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
                f'<td style="{_seat_style(seat.status)}">{escape(str(seat.number))}</td>'
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
        is_schedule = item.alert_type == "schedule"
        badge = "상영일 오픈" if is_schedule else "빈자리 변경"
        badge_color = "#2563eb" if is_schedule else "#e50914"
        cards.append(
            '<section class="screening">'
            f'<p style="display:inline-block;margin:0 0 8px;padding:4px 8px;'
            f'background:{badge_color};color:#fff;font-weight:bold;border-radius:4px">{badge}</p>'
            f'<h2 style="margin:4px 0">{escape(item.movie)}</h2>'
            f'<p style="font-size:16px;font-weight:bold;margin:8px 0">'
            f"상영일 {escape(item.date)} {escape(item.time)}</p>"
            f"<p>{escape(item.theater)} · {escape(item.screen)}</p>"
            + (
                f'<p><a href="{escape(item.booking_url, quote=True)}" '
                'style="display:inline-block;padding:9px 14px;background:#e50914;'
                'color:#fff;text-decoration:none;border-radius:6px">예매 화면 열기</a></p>'
                if item.booking_url
                else ""
            ) + ("" if is_schedule else _seat_map_html(item.seats)) + "</section>"
        )
    title = "새로운 CGV 상영 일정" if screenings[0].alert_type == "schedule" else "CGV 빈 좌석 변경"
    description = "새로 등록된 상영일입니다." if screenings[0].alert_type == "schedule" else "이전 확인 이후 빈 좌석 구성이 변경되었습니다."
    return '<!doctype html><html><body style="font-family:Arial,sans-serif;color:#222">' \
        f"<h1>{title}</h1><p>{description}</p>" + "".join(cards) + '</body></html>'


def send_screenings(settings: Settings, screenings: list[Screening]) -> None:
    if not screenings:
        return
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = settings.mail_to
    title = "CGV 상영 오픈" if screenings[0].alert_type == "schedule" else "CGV 좌석 알림"
    message["Subject"] = f"[{title}] {len(screenings)}건"
    is_schedule = screenings[0].alert_type == "schedule"
    lines = [
        "[상영일 오픈] 새 상영일 또는 회차가 등록되었습니다." if is_schedule else "[빈자리 변경] 이전 확인 이후 빈 좌석 구성이 변경되었습니다.",
        "",
    ]
    for item in screenings:
        lines.append(f"- 상영일: {item.date} {item.time} | {item.theater} | {item.screen} | {item.movie}")
        if item.booking_url:
            lines.append(f"  예매: {item.booking_url}")
    message.set_content("\n".join(lines))
    message.add_alternative(_html_body(screenings), subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.timeout_seconds) as client:
        if settings.smtp_use_tls:
            client.starttls()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
