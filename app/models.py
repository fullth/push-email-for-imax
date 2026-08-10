from dataclasses import dataclass


@dataclass(frozen=True)
class Screening:
    theater: str
    screen: str
    movie: str
    date: str
    time: str
    source_key: str

    @property
    def key(self) -> str:
        return "|".join((self.theater, self.screen, self.movie, self.date, self.time, self.source_key))
