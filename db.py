"""
Zugriff auf die Datenbank (SQLite).

Alle SQL-Befehle gehören in diese Datei. app.py ruft nur Funktionen von hier auf.
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash


# ---------- Verbindung ----------

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


# ---------- Hilfsfunktionen ----------

def _minuten(dauer: timedelta) -> int:
    return int(dauer.total_seconds() // 60)


def _dauer_text(dauer: timedelta) -> str:
    minuten = _minuten(dauer)
    return f"{minuten // 60}:{minuten % 60:02d} h"


# ---------- Mitarbeiter und Anmeldung (UC10) ----------

def mitarbeiter_anlegen(name, benutzername, passwort, ist_chefin=False):
    db = verbindung()
    db.execute(
        "INSERT INTO mitarbeiter (name, benutzername, passwort_hash, ist_chefin) "
        "VALUES (?, ?, ?, ?)",
        (name, benutzername, generate_password_hash(passwort), int(ist_chefin)),
    )
    db.commit()


def anmelden(benutzername: str, passwort: str):
    """Gibt die Zeile der Person zurück, wenn Benutzername und Passwort stimmen, sonst None."""
    zeile = verbindung().execute(
        "SELECT id, name, passwort_hash, ist_chefin FROM mitarbeiter WHERE benutzername = ?",
        (benutzername,),
    ).fetchone()
    if zeile is None or not check_password_hash(zeile["passwort_hash"], passwort):
        return None
    return zeile


def mitarbeiter_holen(mitarbeiter_id: int):
    return verbindung().execute(
        "SELECT id, name, ist_chefin FROM mitarbeiter WHERE id = ?", (mitarbeiter_id,)
    ).fetchone()


def alle_mitarbeiter():
    return verbindung().execute(
        "SELECT id, name FROM mitarbeiter ORDER BY name"
    ).fetchall()


# ---------- Projekte (UC1) ----------

def alle_projekte():
    return verbindung().execute(
        "SELECT nummer, name FROM projekt ORDER BY nummer"
    ).fetchall()


def projekt_erfassen(nummer: str, name: str):
    """UC1: gibt (True, None) bei Erfolg zurück, sonst (False, Fehlermeldung)."""
    nummer = nummer.strip()
    name = name.strip()

    if not nummer or not name:
        return False, "Projektnummer und Name dürfen nicht leer sein."

    try:
        db = verbindung()
        db.execute("INSERT INTO projekt (nummer, name) VALUES (?, ?)", (nummer, name))
        db.commit()
    except sqlite3.IntegrityError:
        return False, f"Die Projektnummer {nummer} existiert bereits."

    return True, None


# ---------- Einstempeln (UC2) ----------

def laufende_stempelung(mitarbeiter_id: int):
    return verbindung().execute(
        """
        SELECT s.beginn, p.nummer, p.name
        FROM stempelung s
        JOIN projekt p ON p.nummer = s.projekt_nummer
        WHERE s.mitarbeiter_id = ? AND s.ende IS NULL
        """,
        (mitarbeiter_id,),
    ).fetchone()


def einstempeln(mitarbeiter_id: int, projekt_nummer: str):
    """UC2: gibt (True, None) bei Erfolg zurück, sonst (False, Fehlermeldung)."""
    if not alle_projekte():
        return False, "Es gibt noch kein Projekt."

    laufend = laufende_stempelung(mitarbeiter_id)
    if laufend and laufend["nummer"] == projekt_nummer:
        return False, "Du bist auf dieses Projekt schon eingestempelt."

    jetzt = datetime.now().isoformat(timespec="seconds")
    db = verbindung()
    try:
        # Projektwechsel: laufende Stempelung zur selben Uhrzeit beenden
        db.execute(
            "UPDATE stempelung SET ende = ? WHERE mitarbeiter_id = ? AND ende IS NULL",
            (jetzt, mitarbeiter_id),
        )
        db.execute(
            "INSERT INTO stempelung (mitarbeiter_id, projekt_nummer, beginn) VALUES (?, ?, ?)",
            (mitarbeiter_id, projekt_nummer, jetzt),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        return False, "Mitarbeiter/in oder Projekt gibt es nicht."

    return True, None


# ---------- Tagesübersicht mit Pausenwarnung (UC4, UC5) ----------

def benoetigte_pause(arbeitszeit: timedelta) -> timedelta:
    """Mindestpause nach Art. 15 ArG."""
    stunden = arbeitszeit.total_seconds() / 3600
    if stunden > 9:
        return timedelta(minutes=60)
    if stunden > 7:
        return timedelta(minutes=30)
    if stunden > 5.5:
        return timedelta(minutes=15)
    return timedelta(0)


def tagesuebersicht(mitarbeiter_id: int, tag: str | None = None):
    """Gibt (Stempelungen, Total als Text, Pausenwarnung oder None) zurück."""
    tag = tag or date.today().isoformat()

    zeilen = verbindung().execute(
        """
        SELECT s.beginn, s.ende, p.nummer, p.name
        FROM stempelung s
        JOIN projekt p ON p.nummer = s.projekt_nummer
        WHERE s.mitarbeiter_id = ? AND substr(s.beginn, 1, 10) = ?
        ORDER BY s.beginn
        """,
        (mitarbeiter_id, tag),
    ).fetchall()

    jetzt = datetime.now()
    total = timedelta()
    pause = timedelta()
    vorheriges_ende = None
    eintraege = []

    for z in zeilen:
        beginn = datetime.fromisoformat(z["beginn"])
        ende = datetime.fromisoformat(z["ende"]) if z["ende"] else None
        dauer = (ende or jetzt) - beginn
        total += dauer

        # Pause = Lücke zwischen dem Ende der vorigen und dem Beginn dieser Stempelung
        if vorheriges_ende and beginn > vorheriges_ende:
            pause += beginn - vorheriges_ende
        vorheriges_ende = ende

        eintraege.append({
            "beginn": beginn.strftime("%H:%M"),
            "ende": ende.strftime("%H:%M") if ende else "läuft",
            "nummer": z["nummer"],
            "name": z["name"],
            "dauer": _dauer_text(dauer),
        })

    noetig = benoetigte_pause(total)
    warnung = None
    if pause < noetig:
        warnung = (
            f"Zu wenig Pause: Bei {_dauer_text(total)} Arbeit sind mindestens "
            f"{_minuten(noetig)} Minuten Pause vorgeschrieben. "
            f"Bisher: {_minuten(pause)} Minuten."
        )

    return eintraege, _dauer_text(total), warnung


# ---------- Stempelung korrigieren (UC7) ----------

_STEMPELUNG_SELECT = """
    SELECT s.id, s.mitarbeiter_id, m.name AS mitarbeiter,
           p.nummer, p.name AS projekt, s.beginn, s.ende
    FROM stempelung s
    JOIN mitarbeiter m ON m.id = s.mitarbeiter_id
    JOIN projekt p ON p.nummer = s.projekt_nummer
"""


def stempelungen_liste(mitarbeiter_id: int | None = None):
    sql = _STEMPELUNG_SELECT
    params = ()
    if mitarbeiter_id:
        sql += " WHERE s.mitarbeiter_id = ?"
        params = (mitarbeiter_id,)
    sql += " ORDER BY s.beginn DESC LIMIT 200"
    return verbindung().execute(sql, params).fetchall()


def stempelung_holen(stempelung_id: int):
    return verbindung().execute(
        _STEMPELUNG_SELECT + " WHERE s.id = ?", (stempelung_id,)
    ).fetchone()


def stempelung_korrigieren(stempelung_id: int, beginn_text: str, ende_text: str):
    """UC7: gibt (True, None) bei Erfolg zurück, sonst (False, Fehlermeldung)."""
    try:
        beginn = datetime.fromisoformat(beginn_text)
        ende = datetime.fromisoformat(ende_text) if ende_text else None
    except ValueError:
        return False, "Datum und Uhrzeit sind ungültig."

    if ende and ende <= beginn:
        return False, "Das Ende muss nach dem Beginn liegen."

    db = verbindung()
    s = db.execute(
        "SELECT mitarbeiter_id FROM stempelung WHERE id = ?", (stempelung_id,)
    ).fetchone()
    if s is None:
        return False, "Diese Stempelung gibt es nicht."

    # Ohne Ende läuft die Stempelung wieder. Pro Person darf nur eine laufen.
    if ende is None:
        andere = db.execute(
            "SELECT 1 FROM stempelung WHERE mitarbeiter_id = ? AND ende IS NULL AND id != ?",
            (s["mitarbeiter_id"], stempelung_id),
        ).fetchone()
        if andere:
            return False, "Diese Person ist schon auf eine andere Stempelung eingestempelt. Bitte ein Ende eintragen."

    db.execute(
        "UPDATE stempelung SET beginn = ?, ende = ? WHERE id = ?",
        (
            beginn.isoformat(timespec="seconds"),
            ende.isoformat(timespec="seconds") if ende else None,
            stempelung_id,
        ),
    )
    db.commit()
    return True, None


# ---------- Auswertung, Zeitraum und Export (UC8, UC9) ----------

def alle_stempelungen(von: str | None = None, bis: str | None = None):
    """Alle Stempelungen, optional nur im Zeitraum von..bis (inklusive, Format JJJJ-MM-TT)."""
    bedingungen = []
    params = []
    if von:
        bedingungen.append("substr(s.beginn, 1, 10) >= ?")
        params.append(von)
    if bis:
        bedingungen.append("substr(s.beginn, 1, 10) <= ?")
        params.append(bis)
    where = "WHERE " + " AND ".join(bedingungen) if bedingungen else ""

    return verbindung().execute(
        f"""
        SELECT m.name AS mitarbeiter, p.nummer, p.name AS projekt, s.beginn, s.ende
        FROM stempelung s
        JOIN mitarbeiter m ON m.id = s.mitarbeiter_id
        JOIN projekt p ON p.nummer = s.projekt_nummer
        {where}
        ORDER BY s.beginn
        """,
        params,
    ).fetchall()


def auswertung(von: str | None = None, bis: str | None = None):
    """Gibt (Stempelungen im Zeitraum, Total als Text) zurück."""
    jetzt = datetime.now()
    total = timedelta()
    eintraege = []
    for s in alle_stempelungen(von, bis):
        beginn = datetime.fromisoformat(s["beginn"])
        ende = datetime.fromisoformat(s["ende"]) if s["ende"] else None
        dauer = (ende or jetzt) - beginn
        total += dauer
        eintraege.append({
            "mitarbeiter": s["mitarbeiter"],
            "projekt": f"{s['nummer']}: {s['projekt']}",
            "datum": beginn.strftime("%d.%m.%Y"),
            "beginn": beginn.strftime("%H:%M"),
            "ende": ende.strftime("%H:%M") if ende else "läuft",
            "dauer": _dauer_text(dauer),
        })
    return eintraege, _dauer_text(total)