"""
Zeiterfassung – Flask-App.

Starten:   flask --app app init-db      (Datenbank anlegen, löscht alte Daten)
           flask --app app run --debug
"""

import csv
import io
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import click
from flask import (
    Flask, Response, flash, g, redirect, render_template, request, session, url_for,
)

import db

app = Flask(__name__)
app.config["DATABASE"] = str(Path(__file__).parent / "zeiterfassung.sqlite")
app.config["SECRET_KEY"] = "nur-fuer-den-unterricht"  # für Login-Sessions und flash()-Meldungen
app.teardown_appcontext(db.schliessen)


# ---------- Anmeldung (UC10) ----------

@app.before_request
def benutzer_laden():
    g.benutzer = None
    if "mitarbeiter_id" in session:
        g.benutzer = db.mitarbeiter_holen(session["mitarbeiter_id"])


@app.context_processor
def benutzer_fuer_templates():
    return {"benutzer": g.benutzer}


def login_erforderlich(f):
    @wraps(f)
    def innen(*args, **kwargs):
        if g.benutzer is None:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return innen


def chefin_erforderlich(f):
    @wraps(f)
    def innen(*args, **kwargs):
        if g.benutzer is None:
            return redirect(url_for("login"))
        if not g.benutzer["ist_chefin"]:
            flash("Dafür hast du keine Berechtigung.", "fehler")
            return redirect(url_for("startseite"))
        return f(*args, **kwargs)
    return innen


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        zeile = db.anmelden(request.form["benutzername"].strip(), request.form["passwort"])
        if zeile:
            session.clear()
            session["mitarbeiter_id"] = zeile["id"]
            return redirect(url_for("startseite"))
        flash("Benutzername oder Passwort stimmt nicht.", "fehler")
    return render_template("login.html")


@app.route("/registrieren", methods=["GET", "POST"])
def registrieren():
    if request.method == "POST":
        ok, fehler = db.mitarbeiter_registrieren(
            request.form.get("name", ""),
            request.form.get("benutzername", ""),
            request.form.get("passwort", ""),
        )
        if ok:
            flash("Konto erstellt. Du kannst dich jetzt anmelden.", "erfolg")
            return redirect(url_for("login"))
        flash(fehler, "fehler")
    return render_template("registrieren.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Mitarbeiter/in ----------

@app.route("/")
@login_erforderlich
def startseite():
    laufend = db.laufende_stempelung(g.benutzer["id"])
    return render_template(
        "start.html", sqlite_version=db.sqlite_version(), laufend=laufend
    )


# UC2: Einstempeln
@app.route("/stempeln", methods=["GET", "POST"])
@login_erforderlich
def stempeln():
    if request.method == "POST":
        ok, fehler = db.einstempeln(g.benutzer["id"], request.form["projekt"])
        if ok:
            flash("Eingestempelt.", "erfolg")
            return redirect(url_for("startseite"))
        flash(fehler, "fehler")

    return render_template("stempeln.html", projekte=db.alle_projekte())

 
@app.route("/ausstempeln", methods=["POST"])
@login_erforderlich
def ausstempeln():
    ok, fehler = db.ausstempeln(g.benutzer["id"])
    if ok:
        flash("Ausgestempelt.", "erfolg")
    else:
        flash(fehler, "fehler")
    return redirect(url_for("startseite"))


# UC4: Tagesübersicht (mit Pausenwarnung)
@app.route("/tag")
@login_erforderlich
def tagesuebersicht():
    eintraege, total, warnung = db.tagesuebersicht(g.benutzer["id"])
    return render_template("tag.html", eintraege=eintraege, total=total, warnung=warnung)


# ---------- Verwaltung (nur Chefin) ----------

# UC1: Projekt erfassen
@app.route("/projekt", methods=["GET", "POST"])
@chefin_erforderlich
def projektverwaltung():
    if request.method == "POST":
        ok, fehler = db.projekt_erfassen(
            request.form["projektnummer"], request.form["name"]
        )
        if ok:
            flash("Projekt erfolgreich gespeichert.", "erfolg")
        else:
            flash(fehler, "fehler")
        return redirect(url_for("projektverwaltung"))

    return render_template("projektverwaltung.html", projekte=db.alle_projekte())


# UC7: Stempelung korrigieren
@app.route("/korrektur")
@chefin_erforderlich
def korrektur_liste():
    mitarbeiter_id = request.args.get("mitarbeiter", type=int)
    return render_template(
        "korrektur.html",
        stempelungen=db.stempelungen_liste(mitarbeiter_id),
        mitarbeiter=db.alle_mitarbeiter(),
        gewaehlt=mitarbeiter_id,
    )


@app.route("/korrektur/<int:stempelung_id>", methods=["GET", "POST"])
@chefin_erforderlich
def korrektur(stempelung_id):
    s = db.stempelung_holen(stempelung_id)
    if s is None:
        flash("Stempelung nicht gefunden.", "fehler")
        return redirect(url_for("korrektur_liste"))

    if request.method == "POST":
        ok, fehler = db.stempelung_korrigieren(
            stempelung_id, request.form["beginn"], request.form["ende"]
        )
        if ok:
            flash("Stempelung korrigiert.", "erfolg")
            return redirect(url_for("korrektur_liste"))
        flash(fehler, "fehler")

    return render_template("korrektur_form.html", s=s)


def _zeitraum():
    """Liest Von/Bis aus der URL. Gibt (von, bis, Fehlermeldung oder None) zurück."""
    von = request.args.get("von", "")
    bis = request.args.get("bis", "")
    try:
        if von:
            date.fromisoformat(von)
        if bis:
            date.fromisoformat(bis)
    except ValueError:
        return "", "", "Das Datum ist ungültig."
    if von and bis and von > bis:
        return von, bis, "Das Von-Datum muss vor dem Bis-Datum liegen."
    return von, bis, None


# UC9: Zeitraum wählen
@app.route("/auswertung")
@chefin_erforderlich
def auswertung():
    von, bis, fehler = _zeitraum()
    if fehler:
        flash(fehler, "fehler")
        eintraege, total = [], "0:00 h"
    else:
        eintraege, total = db.auswertung(von or None, bis or None)
    return render_template(
        "auswertung.html", eintraege=eintraege, total=total, von=von, bis=bis
    )


# UC8: Auswertung exportieren
@app.route("/export")
@chefin_erforderlich
def export():
    von, bis, fehler = _zeitraum()
    if fehler:
        flash(fehler, "fehler")
        return redirect(url_for("auswertung"))

    ausgabe = io.StringIO()
    schreiber = csv.writer(ausgabe, delimiter=";")
    schreiber.writerow(
        ["Mitarbeiter", "Projektnummer", "Projekt", "Datum", "Beginn", "Ende", "Dauer (Min)"]
    )

    for s in db.alle_stempelungen(von or None, bis or None):
        beginn = datetime.fromisoformat(s["beginn"])
        ende = datetime.fromisoformat(s["ende"]) if s["ende"] else None
        dauer = int((ende - beginn).total_seconds() // 60) if ende else ""
        schreiber.writerow([
            s["mitarbeiter"],
            s["nummer"],
            s["projekt"],
            beginn.strftime("%d.%m.%Y"),
            beginn.strftime("%H:%M"),
            ende.strftime("%H:%M") if ende else "",
            dauer,
        ])

    inhalt = "\ufeff" + ausgabe.getvalue()  # BOM, damit Excel UTF-8 erkennt
    return Response(
        inhalt,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=stempelungen.csv"},
    )


# ---------- Datenbank anlegen ----------

@app.cli.command("init-db")
def init_db():
    """Legt die Datenbank aus schema.sql neu an."""
    db.tabellen_anlegen()
    db.mitarbeiter_anlegen("Chefin", "chefin", "chefin123", ist_chefin=True)
    db.mitarbeiter_anlegen("Joel", "joel", "joel123")
    db.mitarbeiter_anlegen("Tijana", "tijana", "tijana123")
    db.mitarbeiter_anlegen("Jetish", "jetish", "Beis2015", ist_chefin=True)
    print("Datenbank angelegt.")


@app.cli.command("grant-admin")
@click.argument("benutzername")
def grant_admin(benutzername):
    """Vergibt Adminrechte, ohne Datenbank oder Stempelungen zurückzusetzen."""
    if not db.admin_rechte_vergeben(benutzername):
        raise click.ClickException(f"Benutzer {benutzername!r} wurde nicht gefunden.")
    print(f"Adminrechte für {benutzername} vergeben.")


if __name__ == "__main__":
    app.run(debug=True)