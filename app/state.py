import sqlite3
from collections.abc import Iterable

from .models import Screening


class StateStore:
    def __init__(self, path: str) -> None:
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS screenings (key TEXT PRIMARY KEY)")
        self.db.commit()

    def unseen(self, screenings: Iterable[Screening]) -> list[Screening]:
        result = []
        for screening in screenings:
            exists = self.db.execute("SELECT 1 FROM screenings WHERE key = ?", (screening.key,)).fetchone()
            if not exists:
                result.append(screening)
        return result

    def save(self, screenings: Iterable[Screening]) -> None:
        current = list(screenings)
        keys = [screening.key for screening in current]
        if keys:
            placeholders = ", ".join("?" for _ in keys)
            self.db.execute(f"DELETE FROM screenings WHERE key NOT IN ({placeholders})", keys)
        else:
            self.db.execute("DELETE FROM screenings")
        self.db.executemany(
            "INSERT OR IGNORE INTO screenings(key) VALUES (?)",
            ((key,) for key in keys),
        )
        self.db.commit()
