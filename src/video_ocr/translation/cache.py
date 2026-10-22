"""Cache persistant des traductions (SQLite, clé = moteur + texte source + contexte)."""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path


class TranslationCache:
    """Cache clé/valeur thread-safe."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS translations (key TEXT PRIMARY KEY, engine TEXT, source TEXT, target TEXT)"
        )
        self._conn.commit()

    @staticmethod
    def make_key(engine: str, source: str, context: str = "") -> str:
        return hashlib.sha256(f"{engine}\x00{source}\x00{context}".encode("utf-8")).hexdigest()

    def get(self, engine: str, source: str, context: str = "") -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT target FROM translations WHERE key = ?", (self.make_key(engine, source, context),)
            ).fetchone()
        return row[0] if row else None

    def put(self, engine: str, source: str, target: str, context: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO translations VALUES (?, ?, ?, ?)",
                (self.make_key(engine, source, context), engine, source, target),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
