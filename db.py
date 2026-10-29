"""
Zugriff auf die Datenbank (SQLite).

Alle SQL-Befehle gehören in diese Datei. app.py ruft nur Funktionen von hier auf.
"""

import sqlite3
from pathlib import Path

from flask import current_app, g


def verbindung() -> sqlite3.Connection:
    """Eine Verbindung pro Anfrage, wird am Ende der Anfrage automatisch geschlossen."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row  # Zeilen wie Dictionaries: zeile["name"]
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def schliessen(_fehler=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def tabellen_anlegen():
    """Führt schema.sql aus."""
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    verbindung().executescript(schema)


def sqlite_version() -> str:
    return verbindung().execute("SELECT sqlite_version()").fetchone()[0]


