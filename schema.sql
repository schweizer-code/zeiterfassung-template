-- Alte Tabellen löschen (zuerst die, die auf andere verweisen)
DROP TABLE IF EXISTS stempelung;
DROP TABLE IF EXISTS projekt;
DROP TABLE IF EXISTS Projekte;
DROP TABLE IF EXISTS mitarbeiter;

CREATE TABLE projekt (
    nummer TEXT PRIMARY KEY,
    name   TEXT NOT NULL
);

CREATE TABLE mitarbeiter (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    benutzername  TEXT    NOT NULL UNIQUE,
    passwort_hash TEXT    NOT NULL,
    ist_chefin    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE stempelung (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    mitarbeiter_id INTEGER NOT NULL REFERENCES mitarbeiter(id),
    projekt_nummer TEXT    NOT NULL REFERENCES projekt(nummer),
    beginn         TEXT    NOT NULL,
    ende           TEXT              -- NULL = läuft noch
);