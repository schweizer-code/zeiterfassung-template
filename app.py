"""
Zeiterfassung – Flask-App.

Starten:   flask --app app init-db      (Datenbank anlegen, löscht alte Daten)
           flask --app app run --debug
"""

from flask import Flask, render_template

import db

app = Flask(__name__)
app.config["DATABASE"] = "zeiterfassung.sqlite"
app.config["SECRET_KEY"] = "nur-fuer-den-unterricht"  # für Login-Sessions und flash()-Meldungen
app.teardown_appcontext(db.schliessen)


@app.route("/")
def startseite():
    return render_template("start.html", sqlite_version=db.sqlite_version())

@app.route("./login.html")


@app.cli.command("init-db")
def init_db():
    """Legt die Datenbank aus schema.sql neu an."""
    db.tabellen_anlegen()
    print("Datenbank angelegt.")
