from dataclasses import dataclass, field


@dataclass(frozen=True)
class Seat:
    """A seat returned by the CGV seat-map API."""

    row: str
    number: int
    status: str
    x: int = 0
    y: int = 0
    kind: str = "일반석"
    zone: str = ""

    @property
    def label(self) -> str:
        return f"{self.row}{self.number}"


@dataclass(frozen=True)
class Screening:
    theater: str
    screen: str
    movie: str
    date: str
    time: str
    source_key: str
    seats: tuple[Seat, ...] = field(default_factory=tuple)
    booking_url: str = ""
    alert_type: str = "seat"

    @property
    def key(self) -> str:
        return "|".join((self.theater, self.screen, self.movie, self.date, self.time, self.source_key))
