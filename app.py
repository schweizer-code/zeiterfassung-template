"""
Zeiterfassung – Flask-App.

Starten:   flask --app app init-db      (Datenbank anlegen, löscht alte Daten)
           flask --app app run --debug
"""

from flask import Flask, render_template, request, redirect, url_for, flash

import db

app = Flask(__name__)
app.config["DATABASE"] = str(
    __import__("pathlib").Path(__file__).parent / "zeiterfassung.sqlite"
)
app.config["SECRET_KEY"] = "nur-fuer-den-unterricht"  # für Login-Sessions und flash()-Meldungen
app.teardown_appcontext(db.schliessen)

@app.route("/projekt", methods=["GET", "POST"])
def projektverwaltung():
    if request.method == "POST":
        projektnummer = request.form["projektnummer"].strip()
        name = request.form["name"].strip()

        try:
            db.projekt_speichern(projektnummer, name)
            flash("Projekt erfolgreich gespeichert.", "success")
        except Exception:
            flash("Diese Projektnummer existiert bereits.", "error")

        return redirect(url_for("projektverwaltung"))

    projekte = db.projekte_anzeigen()
    return render_template(
        "projektverwaltung.html",
        projekte=projekte
    )

@app.route("/")
def startseite():
    return render_template("start.html", sqlite_version=db.sqlite_version())


@app.cli.command("init-db")
def init_db():
    """Legt die Datenbank aus schema.sql neu an."""
    db.tabellen_anlegen()
    print("Datenbank angelegt.")
    
    
if __name__ == "__main__":
    app.run(debug=True)
