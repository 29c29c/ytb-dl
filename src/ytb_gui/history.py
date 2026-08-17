from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    extractor: str
    video_id: str
    title: str
    file_path: str
    downloaded_at: str


class HistoryStore:
    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    extractor TEXT NOT NULL,
                    video_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    downloaded_at TEXT NOT NULL,
                    PRIMARY KEY (extractor, video_id)
                )
                """
            )

    def contains(self, extractor: str, video_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM downloads WHERE extractor = ? AND video_id = ?",
                (extractor, video_id),
            ).fetchone()
        return row is not None

    def get(self, extractor: str, video_id: str) -> HistoryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM downloads WHERE extractor = ? AND video_id = ?",
                (extractor, video_id),
            ).fetchone()
        return HistoryRecord(**dict(row)) if row else None

    def record(self, extractor: str, video_id: str, title: str, file_path: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO downloads (extractor, video_id, title, file_path, downloaded_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(extractor, video_id) DO UPDATE SET
                    title = excluded.title,
                    file_path = excluded.file_path,
                    downloaded_at = excluded.downloaded_at
                """,
                (extractor, video_id, title, file_path, timestamp),
            )

    def remove(self, extractor: str, video_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM downloads WHERE extractor = ? AND video_id = ?",
                (extractor, video_id),
            )

