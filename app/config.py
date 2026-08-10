import json
import os
from dataclasses import dataclass


def _json_env(name: str, default: dict) -> dict:
    raw = os.getenv(name)
    if not raw:
        return default
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    cgv_endpoint: str
    cgv_request: dict
    cgv_headers: dict
    cgv_cookies: dict
    poll_interval_seconds: int
    timeout_seconds: int
    state_path: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    mail_from: str
    mail_to: str
    mail_subject_prefix: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            cgv_endpoint=os.environ["CGV_ENDPOINT"],
            cgv_request=_json_env("CGV_REQUEST_JSON", {}),
            cgv_headers=_json_env("CGV_HEADERS_JSON", {}),
            cgv_cookies=_json_env("CGV_COOKIES_JSON", {}),
            poll_interval_seconds=int(os.getenv("CGV_POLL_INTERVAL_SECONDS", "300")),
            timeout_seconds=int(os.getenv("CGV_TIMEOUT_SECONDS", "20")),
            state_path=os.getenv("CGV_STATE_PATH", "state.sqlite3"),
            smtp_host=os.environ["SMTP_HOST"],
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_username=os.environ["SMTP_USERNAME"],
            smtp_password=os.environ["SMTP_PASSWORD"],
            smtp_use_tls=_bool_env("SMTP_USE_TLS", True),
            mail_from=os.environ["MAIL_FROM"],
            mail_to=os.environ["MAIL_TO"],
            mail_subject_prefix=os.getenv("MAIL_SUBJECT_PREFIX", "[CGV 예매 오픈]"),
        )
