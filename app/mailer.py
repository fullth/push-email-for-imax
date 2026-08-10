import smtplib
from email.message import EmailMessage

from .config import Settings
from .models import Screening


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
    message.set_content("\n".join(lines))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.timeout_seconds) as client:
        if settings.smtp_use_tls:
            client.starttls()
        client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)
