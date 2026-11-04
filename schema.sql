-- Datenmodell der Zeiterfassung.
-- Wird mit "flask --app app init-db" ausgeführt. Damit das wiederholt
-- funktioniert, zuerst jede Tabelle löschen und dann neu anlegen:
--
--   DROP TABLE IF EXISTS tabellenname;
--   CREATE TABLE tabellenname (
--       id INTEGER PRIMARY KEY AUTOINCREMENT,
--       ...
--   );

CREATE TABLE IF NOT EXISTS Projekte (
    projektnummer TEXT PRIMARY KEY,
    name TEXT NOT NULL
);