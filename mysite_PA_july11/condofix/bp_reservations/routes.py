from flask import Blueprint, render_template, session, url_for, redirect, request, flash, current_app
from html import escape
from services.email_service import send_html_email
from markupsafe import Markup  # Import Markup separately
import mysql.connector
from datetime import datetime,timedelta
import pytz
from pytz import timezone
from dateutil.relativedelta import relativedelta
from io import StringIO
import unicodedata
import csv
from werkzeug.wrappers import Response
import os
from utils import connect_db

# Helper function for reservation validation
from datetime import datetime, date, time, timedelta
from decimal import Decimal, InvalidOperation


def _as_date(value):
    """Convert MySQL date/string value to datetime.date."""
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _as_time(value):
    """Convert MySQL time/timedelta/string value to datetime.time."""
    if isinstance(value, timedelta):
        return (datetime.min + value).time()

    if isinstance(value, time):
        return value

    value_as_text = str(value)

    if len(value_as_text) == 5:
        return datetime.strptime(value_as_text, "%H:%M").time()

    return datetime.strptime(value_as_text[:8], "%H:%M:%S").time()


def _hours_to_minutes(value):
    """Convert decimal hours to minutes."""
    if value is None:
        return 0

    return int(round(float(value) * 60))


def _build_reservation_window(reservation_date, start_time, duration_hours):
    """Return reservation start/end datetimes."""
    start_datetime = datetime.combine(
        _as_date(reservation_date),
        _as_time(start_time)
    )

    end_datetime = start_datetime + timedelta(
        minutes=_hours_to_minutes(duration_hours)
    )

    return start_datetime, end_datetime


def _find_reservation_conflicts(cur, client_ident, resource_id, requested_windows, interval_hours):
    """
    Detect conflicts for a resource.

    A conflict exists when the requested window overlaps an existing reservation,
    including the mandatory buffer interval before and after existing reservations.
    """

    interval_minutes = _hours_to_minutes(interval_hours)

    cur.execute("""
        SELECT IDReservation, Date, HeureDebut, DureeHres, NoUnite
        FROM reservations
        WHERE IDClient = %s
          AND IDRessource = %s
    """, (client_ident, resource_id))

    conflicts = []

    for existing in cur.fetchall():
        existing_id = existing[0]
        existing_date = existing[1]
        existing_time = existing[2]
        existing_duration = existing[3]
        existing_unit = existing[4]

        existing_start, existing_end = _build_reservation_window(
            existing_date,
            existing_time,
            existing_duration
        )

        protected_start = existing_start - timedelta(minutes=interval_minutes)
        protected_end = existing_end + timedelta(minutes=interval_minutes)

        for requested_start, requested_end in requested_windows:
            if requested_start < protected_end and requested_end > protected_start:
                conflicts.append({
                    "id": existing_id,
                    "date": existing_start.strftime("%Y-%m-%d"),
                    "start": existing_start.strftime("%H:%M"),
                    "end": existing_end.strftime("%H:%M"),
                    "unit": existing_unit
                })

    return conflicts
# ********************************************



bp_reservations = Blueprint('bp_reservations', __name__)

def _send_reservation_facturable_email(
    subject,
    recipients,
    desc_ress,
    no_unite,
    date_rez,
    heure,
    duree,
    note,
    courriel=None,
    mode_de_paiement=None,
    jours=None
):
    """
    Envoie les avis de réservation facturable.

    Utilisé pour:
    - création d'une réservation facturable par admin;
    - création d'une réservation facturable par copropriétaire;
    - annulation/suppression d'une réservation facturable future.

    L'échec d'envoi ne doit pas annuler l'opération métier déjà effectuée.
    """

    if not recipients:
        current_app.logger.warning(
            "Courriel de réservation facturable non envoyé: aucun destinataire configuré."
        )
        return

    rows = [
        ("Ressource", desc_ress),
        ("Soumis par unité", no_unite),
        ("Date", date_rez),
        ("Heure", heure),
        ("Durée (h.)", duree),
    ]

    if jours is not None:
        rows.append(("Jours", jours))

    if courriel is not None:
        rows.append(("Courriel", courriel))

    if mode_de_paiement is not None:
        rows.append(("Mode de paiement", mode_de_paiement))

    rows.append(("Note", note))

    html_rows = "<br/>".join(
        "<b>{label}:</b>&nbsp;{value}".format(
            label=escape(str(label)),
            value=escape(str(value or ""))
        )
        for label, value in rows
    )

    html = """
        <html><body>
        <p>{html_rows}</p>
        </body></html>
    """.format(html_rows=html_rows)

    try:
        send_html_email(
            subject=subject,
            recipients=recipients,
            html_body=html
        )
    except Exception:
        current_app.logger.exception(
            "Erreur lors de l'envoi du courriel de réservation facturable."
        )

#page de la liste de reservations avec fonction ajout (ADMIN SEULEMENT)
@bp_reservations.route("/reservations_table")
def reservations_table():
    """Pour admin seulement: affiche tous les enregistrements dans une table et permet le contrôle des réservations (ajout, modif, suppression) sans l'application
    d'aucune restriction."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier si le client a acheté le module réservations
    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))
    # vérifier type d'usager si bp_admin ou concierge
    if profile_list[2] > 3:
        return redirect(url_for('bp_admin.permission'))
    fill_reservations=[]
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("SELECT IDReservation, IDRessource, Date, HeureDebut, DureeHres, NoUnite, DateHeureCreation, Note,"
                "Courriel, ModePaiement FROM reservations WHERE  IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        cur.execute("SELECT Description FROM ressources WHERE IDRessource=%s AND IDClient=%s", (row[1],client_ident))
        for item in cur.fetchall():
            ressource=item
            row+=(ressource)
        cur.execute("SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s", (row[9],client_ident))
        for item in cur.fetchall():
            desc_mode_paiement=item[0]
            row+=(desc_mode_paiement,)
        fill_reservations.append(row)
    cnx.close()
    return render_template('reservations_table.html', date_debut='', fill_reservations=fill_reservations,bd=profile_list[3])


# page du calendrier de reservations avec fonction ajout
@bp_reservations.route("/calendrier_rez/<usager>")
def calendrier_rez(usager):
    """Afficher les réservations à l'aide du calendrier JavaScript.

    Cette route prépare le modèle d'événements pour FullCalendar.

    Améliorations ajoutées:
    - ID de réservation exposé dans chaque événement.
    - Date/heure de fin calculée selon la durée.
    - Libellé de durée plus lisible pour l'interface.
    - Liste de légende propre, non rembourrée, pour la future refonte UI.
    - Conservation de fill_ressources rembourrée à 10 éléments pour compatibilité
      avec les anciens templates/CSS.
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # vérifier si le client a acheté le module réservations
    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]

    # ---------------------------------------------------------------------
    # Helpers locaux à cette route
    # ---------------------------------------------------------------------

    def time_to_python_time(value):
        """Convertit une heure MySQL en datetime.time.

        MySQL peut retourner une heure sous forme de:
        - datetime.time
        - datetime.timedelta
        - string: "HH:MM:SS" ou "H:MM:SS"
        """

        if isinstance(value, timedelta):
            return (datetime.min + value).time()

        if hasattr(value, "hour") and hasattr(value, "minute"):
            return value

        value_s = str(value or '').strip()

        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(value_s[:8], fmt).time()
            except ValueError:
                pass

        # Fallback défensif: minuit.
        return datetime.strptime("00:00:00", "%H:%M:%S").time()

    def hours_to_minutes(value):
        """Convertit une durée en heures décimales vers minutes."""
        if value is None:
            return 0

        return int(round(float(value) * 60))

    def format_duration_label(value):
        """Retourne un libellé lisible: 30 min, 1 h, 1 h 30, 4 h, etc."""
        minutes_total = hours_to_minutes(value)

        if minutes_total <= 0:
            return "0 min"

        hours = minutes_total // 60
        minutes = minutes_total % 60

        if hours == 0:
            return str(minutes) + " min"

        if minutes == 0:
            return str(hours) + " h"

        return str(hours) + " h " + str(minutes).zfill(2)

    def format_time_label(value):
        """Retourne HH:MM pour affichage."""
        return time_to_python_time(value).strftime("%H:%M")

    # ---------------------------------------------------------------------
    # Connexion DB
    # ---------------------------------------------------------------------

    cnx = connect_db(mode)
    cur = cnx.cursor()

    # ---------------------------------------------------------------------
    # 1) Ressources actives
    # ---------------------------------------------------------------------
    # ressources_actives:
    # - liste réelle, non rembourrée
    # - utilisée pour la légende moderne et les KPIs
    #
    # liste_ress_actives:
    # - version rembourrée à 10 éléments
    # - conservée pour compatibilité avec les templates existants

    ressources_actives = []

    cur.execute("""
        SELECT IDRessource, Description
        FROM ressources
        WHERE Actif = 1
          AND IDClient = %s
        ORDER BY IDRessource
    """, (client_ident,))

    for item in cur.fetchall():
        ressources_actives.append(item)

    liste_ress_actives = list(ressources_actives)

    while len(liste_ress_actives) < 10:
        liste_ress_actives.append((0, ''))

    # ---------------------------------------------------------------------
    # 2) Couleurs par ressource
    # ---------------------------------------------------------------------
    # On conserve les couleurs historiques pour les 10 premières ressources.
    # Si un client a plus de 10 ressources actives, on réutilise la palette
    # en boucle au lieu d'ignorer les réservations.

    colors = [
        'black', 'lawngreen', 'blue', 'red', 'orange',
        'pink', 'lightslategrey', 'magenta', 'peru', 'purple'
    ]

    color_by_ressource = {}
    desc_by_ressource = {}
    legend_ressources = []

    for idx, (res_id, desc) in enumerate(ressources_actives):
        if res_id and desc:
            color = colors[idx % len(colors)]

            color_by_ressource[res_id] = color
            desc_by_ressource[res_id] = desc

            legend_ressources.append({
                "id": res_id,
                "description": desc,
                "couleur": color
            })

    # ---------------------------------------------------------------------
    # 3) Réservations à partir d'aujourd'hui -> events_list
    # ---------------------------------------------------------------------
    # Pour les vues semaine/jour, FullCalendar a besoin de start ET end.
    # On conserve aussi date_heure pour compatibilité avec le JS actuel.

    today_montreal = datetime.now(
        pytz.timezone('America/Montreal')
    ).strftime('%Y-%m-%d')

    cur.execute("""
        SELECT
            IDReservation,
            IDRessource,
            Date,
            HeureDebut,
            DureeHres,
            NoUnite,
            Note
        FROM reservations
        WHERE Date >= %s
          AND IDClient = %s
        ORDER BY Date, HeureDebut
    """, (today_montreal, client_ident))

    events_list = []

    for row in cur.fetchall():
        reservation_id = row[0]
        res_id = row[1]
        date_rez = row[2]
        heure_debut = row[3]
        duree_hres = row[4]
        no_unite = row[5]
        note = row[6] or ""

        # ignorer les réservations dont la ressource est inactive ou inconnue
        if res_id not in color_by_ressource:
            continue

        date_s = str(date_rez)[:10]
        heure_obj = time_to_python_time(heure_debut)

        start_dt = datetime(
            int(date_s[0:4]),
            int(date_s[5:7]),
            int(date_s[8:10]),
            heure_obj.hour,
            heure_obj.minute,
            heure_obj.second
        )

        end_dt = start_dt + timedelta(
            minutes=hours_to_minutes(duree_hres)
        )

        duree_label = format_duration_label(duree_hres)
        heure_label = format_time_label(heure_debut)
        ressource_desc = desc_by_ressource.get(res_id, "")

        tooltip = (
            ressource_desc
            + " — Unité "
            + str(no_unite)
            + " — "
            + duree_label
        )

        if note:
            tooltip = tooltip + " — " + str(note).replace("\n", " ")

        events_list.append({
            # Nouveau modèle FullCalendar
            "id": reservation_id,
            "title": heure_label + " h " + str(no_unite) + " (" + duree_label + ")",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),

            # Compatibilité avec le template actuel
            "date_heure": start_dt.isoformat(),
            "date_heure_fin": end_dt.isoformat(),

            # Données métier
            "no_unite": no_unite,
            "ressource": res_id,
            "ressource_desc": ressource_desc,
            "duree": duree_hres,
            "duree_label": duree_label,
            "heure_label": heure_label,
            "note": note,
            "couleur": color_by_ressource[res_id],
            "tooltip": tooltip
        })

    cnx.close()

    # ---------------------------------------------------------------------
    # 4) KPIs simples pour la future refonte du calendrier admin
    # ---------------------------------------------------------------------

    total_reservations_futures = len(events_list)
    total_ressources_actives = len(ressources_actives)

    prochaine_reservation = None
    if events_list:
        prochaine_reservation = (
            events_list[0]["date_heure"][0:10]
            + " "
            + events_list[0]["heure_label"]
            + " — "
            + events_list[0]["ressource_desc"]
        )

    # ---------------------------------------------------------------------
    # 5) Rendu admin / copropriétaire
    # ---------------------------------------------------------------------

    if usager == 'admin':
        return render_template(
            'calendrier_rez_admin.html',
            events_list=events_list,
            fill_ressources=liste_ress_actives,
            legend_ressources=legend_ressources,
            total_reservations_futures=total_reservations_futures,
            total_ressources_actives=total_ressources_actives,
            prochaine_reservation=prochaine_reservation,
            bd=profile_list[3]
        )

    # proprio
    return render_template(
        'calendrier_rez.html',
        events_list=events_list,
        fill_ressources=liste_ress_actives,
        legend_ressources=legend_ressources,
        total_reservations_futures=total_reservations_futures,
        total_ressources_actives=total_ressources_actives,
        prochaine_reservation=prochaine_reservation,
        bd=profile_list[3]
    )

#fonctions pour afficher page d'ajout de rez
@bp_reservations.route("/reservation_affiche_admin", methods=['GET', 'POST'])
def reservation_affiche_admin():
    """Afficher l'écran pour effectuer une réservation pour l'admin."""

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Admin CondoFix seulement.
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]

    cnx = connect_db(mode)
    cur = cnx.cursor()

    fill_ressources = []
    fill_modes_paiement = []

    # Important:
    # La page utilise ces colonnes dans les attributs data-* du <option>.
    cur.execute("""
        SELECT
            IDRessource,
            Description,
            DureeMaxHres,
            DelaiMinHres,
            DelaiMaxJrs,
            JoursConsecutifsPermis,
            DateDebutNonDispo,
            DureeNonDispoHres,
            IntervalleRezHres,
            HreDebutPermise,
            HreFinPermise,
            Facturable
        FROM ressources
        WHERE Actif = 1
          AND IDClient = %s
        ORDER BY Description
    """, (client_ident,))

    for item in cur.fetchall():
        fill_ressources.append(item)

    cur.execute("""
        SELECT IDPaiement, Description
        FROM modepaiement
        WHERE IDClient = %s
        ORDER BY Description
    """, (client_ident,))

    for item in cur.fetchall():
        fill_modes_paiement.append(item)

    cnx.close()

    return render_template(
        'reservation_ajout_admin.html',
        fill_ressources=fill_ressources,
        fill_modes_paiement=fill_modes_paiement,
        bd=profile_list[3]
    )

#fonctions pour afficher page d'ajout de rez
@bp_reservations.route("/reservation_affiche_proprio", methods=['GET', 'POST'])
def reservation_affiche_proprio():
    """Afficher l'écran pour effectuer une réservation pour les copropriétaires.

    La ressource peut être présélectionnée depuis le calendrier, mais demeure
    modifiable dans le formulaire.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Vérifier si le client a acheté le module réservations.
    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]

    selected_resource_id = (
        request.values.get('ress_select')
        or request.values.get('ident_ress')
        or ''
    ).strip()

    cnx = connect_db(mode)
    cur = cnx.cursor()

    fill_ressources = []
    fill_modes_paiement = []

    cur.execute("""
        SELECT
            IDRessource,
            Description,
            DureeMaxHres,
            DelaiMinHres,
            DelaiMaxJrs,
            JoursConsecutifsPermis,
            DateDebutNonDispo,
            DureeNonDispoHres,
            IntervalleRezHres,
            HreDebutPermise,
            HreFinPermise,
            Facturable
        FROM ressources
        WHERE Actif = 1
          AND IDClient = %s
        ORDER BY Description
    """, (client_ident,))

    for item in cur.fetchall():
        fill_ressources.append(item)

    valid_resource_ids = {str(item[0]) for item in fill_ressources}

    if selected_resource_id not in valid_resource_ids:
        selected_resource_id = ''

    cur.execute("""
        SELECT IDPaiement, Description
        FROM modepaiement
        WHERE IDClient = %s
        ORDER BY Description
    """, (client_ident,))

    for item in cur.fetchall():
        fill_modes_paiement.append(item)

    message_affiche = 0
    message_rez = ''

    cur.execute("""
        SELECT AfficheMessageRez, MessageRez
        FROM parametres
        WHERE IDClient = %s
    """, (client_ident,))

    row = cur.fetchone()

    if row is not None:
        message_affiche = int(row[0] or 0)
        message_rez = row[1] or ''

    form_data = {
        "ress_select": selected_resource_id,
        "no_unite": '',
        "date_rez": '',
        "heure_rez": '12:00',
        "duree_rez": '',
        "jrs_consecutifs": '1',
        "note": '',
        "courriel": '',
        "mode_paiement": ''
    }

    if selected_resource_id:
        selected_resource = next(
            (item for item in fill_ressources if str(item[0]) == selected_resource_id),
            None
        )

        if selected_resource is not None:
            duree_max = selected_resource[2]
            delai_min_hres = float(selected_resource[3] or 0)
            heure_debut_permise = selected_resource[9]
            heure_fin_permise = selected_resource[10]

            now_montreal = datetime.now(
                pytz.timezone('America/Montreal')
            ).replace(tzinfo=None)

            suggested_start_base = now_montreal + timedelta(hours=delai_min_hres)

            try:
                allowed_start = _as_time(heure_debut_permise)
                allowed_end = _as_time(heure_fin_permise)
            except Exception:
                allowed_start = time(12, 0)
                allowed_end = time(0, 0)

            # Convention CondoFix:
            # 00:00 à 00:00 = disponible 24 h/24.
            if allowed_start == time(0, 0) and allowed_end == time(0, 0):
                suggested_time = time(12, 0)
            else:
                suggested_time = allowed_start

            if suggested_start_base.time() > suggested_time:
                suggested_start = datetime.combine(
                    suggested_start_base.date() + timedelta(days=1),
                    suggested_time
                )
            else:
                suggested_start = datetime.combine(
                    suggested_start_base.date(),
                    suggested_time
                )

            form_data["date_rez"] = suggested_start.strftime("%Y-%m-%d")
            form_data["heure_rez"] = suggested_start.strftime("%H:%M")
            form_data["duree_rez"] = str(duree_max or '')

    cnx.close()

    return render_template(
        'reservation_ajout_proprio.html',
        fill_ressources=fill_ressources,
        fill_modes_paiement=fill_modes_paiement,
        form_data=form_data,
        message_affiche=message_affiche,
        message_rez=message_rez,
        bd=profile_list[3]
    )

# fonctions pour ajouter une réservation
@bp_reservations.route("/reservation_ajout_admin", methods=['POST'])
def reservation_ajout_admin():
    """Ajout d'une réservation à la table reservations par l'admin.

    Champs reservations utilisés:
    - DateHeureCreation
    - IDRessource
    - IDClient
    - Date
    - HeureDebut
    - DureeHres
    - NoUnite
    - Note
    - Courriel
    - ModePaiement

    Champs ressources utilisés:
    - IDRessource
    - IDClient
    - Description
    - DureeMaxHres
    - DelaiMinHres
    - DelaiMaxJrs
    - DateDebutNonDispo
    - DureeNonDispoHres
    - JoursConsecutifsPermis
    - IntervalleRezHres
    - HreDebutPermise
    - HreFinPermise
    - Facturable
    - Actif
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Admin CondoFix seulement.
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]

    # ---------------------------------------------------------------------
    # Helpers locaux
    # ---------------------------------------------------------------------

    def parse_positive_integer(value):
        """Retourne int si entier positif, sinon None."""
        value = str(value or '').strip()
        if value.isdigit() and int(value) > 0:
            return int(value)
        return None

    def parse_optional_integer(value):
        """Retourne int si entier >= 0, sinon None."""
        value = str(value or '').strip()
        if value.isdigit() and int(value) >= 0:
            return int(value)
        return None

    def parse_float(value):
        """Retourne float; accepte virgule ou point décimal."""
        try:
            return float(str(value or '').strip().replace(',', '.'))
        except (TypeError, ValueError):
            return None

    def parse_date(value):
        """Accepte YYYY-MM-DD."""
        try:
            return datetime.strptime(str(value or '').strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    def parse_time(value):
        """Accepte HH:MM ou HH:MM:SS."""
        value = str(value or '').strip()

        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                pass

        return None

    def db_date_to_date(value):
        """Convertit date/datetime/string MySQL en date Python."""
        if isinstance(value, datetime):
            return value.date()

        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            return value

        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()

    def db_time_to_time(value):
        """Convertit time/timedelta/string MySQL en time Python."""
        if isinstance(value, timedelta):
            return (datetime.min + value).time()

        if hasattr(value, "hour") and hasattr(value, "minute"):
            return value

        value_as_text = str(value or '').strip()

        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(value_as_text[:8], fmt).time()
            except ValueError:
                pass

        return None

    def hours_to_minutes(value):
        """Convertit des heures décimales en minutes."""
        return int(round(float(value or 0) * 60))

    def is_half_hour_increment(value):
        """Valide les blocs de 30 minutes: 0.5, 1, 1.5, 2, etc."""
        return value is not None and round(value * 2, 8).is_integer()

    def is_midnight(value):
        """Vrai si l'heure est 00:00:00."""
        return (
            value is not None
            and value.hour == 0
            and value.minute == 0
            and value.second == 0
        )

    def windows_overlap(start_a, end_a, start_b, end_b):
        """Chevauchement strict: permet les limites qui se touchent exactement."""
        return start_a < end_b and end_a > start_b

    def flash_and_return(errors, cur, cnx_to_close=None):
        """Affiche les erreurs et retourne au formulaire en conservant les valeurs saisies."""

        form_data = {
            "ress_select": ress_select_raw,
            "no_unite": no_unite_raw,
            "date_rez": date_rez_raw,
            "heure_rez": heure_rez_raw,
            "duree_rez": duree_rez_raw,
            "jrs_consecutifs": jrs_consecutifs_raw,
            "note": note,
            "courriel": courriel,
            "mode_paiement": mode_paiement_raw
        }

        fill_ressources = []
        fill_modes_paiement = []

        cur.execute("""
            SELECT
                IDRessource,
                Description,
                DureeMaxHres,
                DelaiMinHres,
                DelaiMaxJrs,
                JoursConsecutifsPermis,
                DateDebutNonDispo,
                DureeNonDispoHres,
                IntervalleRezHres,
                HreDebutPermise,
                HreFinPermise,
                Facturable
            FROM ressources
            WHERE Actif = 1
              AND IDClient = %s
            ORDER BY Description
        """, (client_ident,))

        for item in cur.fetchall():
            fill_ressources.append(item)

        cur.execute("""
            SELECT IDPaiement, Description
            FROM modepaiement
            WHERE IDClient = %s
            ORDER BY Description
        """, (client_ident,))

        for item in cur.fetchall():
            fill_modes_paiement.append(item)

        if cnx_to_close is not None:
            cnx_to_close.close()

        flash(Markup("<br>".join(errors)), "warning")

        return render_template(
            'reservation_ajout_admin.html',
            fill_ressources=fill_ressources,
            fill_modes_paiement=fill_modes_paiement,
            form_data=form_data,
            bd=profile_list[3]
        )

    # ---------------------------------------------------------------------
    # Lecture du formulaire
    # ---------------------------------------------------------------------

    errors = []

    ress_select_raw = request.form.get('ress_select', '').strip()
    no_unite_raw = request.form.get('no_unite', '').strip()
    date_rez_raw = request.form.get('date_rez', '').strip()
    heure_rez_raw = request.form.get('heure_rez', '').strip()
    duree_rez_raw = request.form.get('duree_rez', '').strip()
    jrs_consecutifs_raw = request.form.get('jrs_consecutifs', '').strip()
    note = request.form.get('note', '').strip()
    courriel = request.form.get('courriel', '').strip()
    mode_paiement_raw = request.form.get('mode_paiement', '').strip()

    resource_id = parse_positive_integer(ress_select_raw)
    no_unite = parse_positive_integer(no_unite_raw)
    date_rez_obj = parse_date(date_rez_raw)
    heure_rez_obj = parse_time(heure_rez_raw)
    duree_rez = parse_float(duree_rez_raw)
    jrs_consecutifs = parse_positive_integer(jrs_consecutifs_raw)

    if resource_id is None:
        errors.append("Veuillez sélectionner une ressource valide.")

    if no_unite is None:
        errors.append("Le numéro d'unité doit être un nombre entier positif.")

    if date_rez_obj is None:
        errors.append("La date de réservation est invalide.")

    if heure_rez_obj is None:
        errors.append("L'heure de début est invalide.")

    if duree_rez is None or duree_rez <= 0:
        errors.append("La durée doit être supérieure à 0.")
    elif not is_half_hour_increment(duree_rez):
        errors.append("La durée doit être saisie en blocs de 30 minutes : 0.5, 1, 1.5, 2, etc.")

    if jrs_consecutifs is None:
        errors.append("Les jours consécutifs doivent être un nombre entier positif.")

    if len(note) > 200:
        errors.append("La note ne peut pas dépasser 200 caractères.")

    cnx = connect_db(mode)
    cur = cnx.cursor()

    # ---------------------------------------------------------------------
    # Lecture de la ressource sélectionnée
    # ---------------------------------------------------------------------

    desc_ress = ''
    facturable = 0
    duree_max = 0
    delai_min_hres = 0
    delai_max_jrs = 0
    date_debut_non_dispo = None
    duree_non_dispo_hres = 0
    jrs_consecutifs_permis = 0
    intervalle_rez_hres = 0
    hre_debut_permise = None
    hre_fin_permise = None

    if resource_id is not None:
        cur.execute("""
            SELECT
                Description,
                Facturable,
                DureeMaxHres,
                DelaiMinHres,
                DelaiMaxJrs,
                DateDebutNonDispo,
                DureeNonDispoHres,
                JoursConsecutifsPermis,
                IntervalleRezHres,
                HreDebutPermise,
                HreFinPermise
            FROM ressources
            WHERE IDRessource = %s
              AND IDClient = %s
              AND Actif = 1
        """, (resource_id, client_ident))

        ressource = cur.fetchone()

        if ressource is None:
            errors.append("La ressource sélectionnée est invalide ou inactive.")
        else:
            desc_ress = ressource[0]
            facturable = int(ressource[1] or 0)
            duree_max = parse_float(ressource[2]) or 0
            delai_min_hres = parse_float(ressource[3]) or 0
            delai_max_jrs = parse_float(ressource[4]) or 0
            date_debut_non_dispo = ressource[5]
            duree_non_dispo_hres = parse_float(ressource[6]) or 0
            jrs_consecutifs_permis = parse_optional_integer(ressource[7]) or 0
            intervalle_rez_hres = parse_float(ressource[8]) or 0
            hre_debut_permise = db_time_to_time(ressource[9])
            hre_fin_permise = db_time_to_time(ressource[10])

    # ---------------------------------------------------------------------
    # Validation du mode de paiement
    # ---------------------------------------------------------------------

    if mode_paiement_raw == '':
        mode_de_paiement = 0
    else:
        mode_de_paiement = parse_positive_integer(mode_paiement_raw)

        if mode_de_paiement is None:
            errors.append("Le mode de paiement est invalide.")
            mode_de_paiement = 0
        else:
            cur.execute("""
                SELECT COUNT(*)
                FROM modepaiement
                WHERE IDPaiement = %s
                  AND IDClient = %s
            """, (mode_de_paiement, client_ident))

            if cur.fetchone()[0] == 0:
                errors.append("Le mode de paiement sélectionné est invalide.")

    if facturable == 1:
        if not courriel:
            errors.append("Le courriel est obligatoire pour une ressource facturable.")

        if mode_de_paiement == 0:
            errors.append("Le mode de paiement est obligatoire pour une ressource facturable.")

    # Si les champs essentiels sont invalides, on arrête ici.
    if errors:
        return flash_and_return(errors, cur, cnx)

    # ---------------------------------------------------------------------
    # Validation des contraintes de la ressource
    # ---------------------------------------------------------------------

    now_montreal = datetime.now(pytz.timezone('America/Montreal')).replace(tzinfo=None)

    requested_windows = []

    for day_index in range(jrs_consecutifs):
        requested_start = datetime.combine(
            date_rez_obj + timedelta(days=day_index),
            heure_rez_obj
        )

        requested_end = requested_start + timedelta(
            minutes=hours_to_minutes(duree_rez)
        )

        requested_windows.append((requested_start, requested_end))

    first_requested_start = requested_windows[0][0]
    last_requested_start = requested_windows[-1][0]

    # 1) Durée maximale permise pour une réservation.
    if duree_max > 0 and duree_rez > duree_max:
        errors.append(
            "La durée demandée dépasse la durée maximale permise pour cette ressource "
            + "(" + str(duree_max) + " h)."
        )

    # 2) Nombre maximal de jours consécutifs permis.
    if jrs_consecutifs_permis > 0 and jrs_consecutifs > jrs_consecutifs_permis:
        errors.append(
            "Le nombre de jours consécutifs dépasse la limite permise pour cette ressource "
            + "(" + str(jrs_consecutifs_permis) + " jour(s))."
        )

    # 3) Délai minimal avant la réservation.
    delai_rez_hres = (first_requested_start - now_montreal).total_seconds() / 3600

    if delai_rez_hres < 0:
        errors.append("La réservation ne peut pas être créée dans le passé.")
    elif delai_min_hres > 0 and delai_rez_hres < delai_min_hres:
        errors.append(
            "La réservation ne respecte pas le délai minimal configuré pour cette ressource "
            + "(" + str(delai_min_hres) + " h)."
        )

    # 4) Délai maximal en jours.
    delai_rez_jrs = (last_requested_start - now_montreal).total_seconds() / 86400

    if delai_max_jrs > 0 and delai_rez_jrs > delai_max_jrs:
        errors.append(
            "La réservation dépasse le délai maximal configuré pour cette ressource "
            + "(" + str(delai_max_jrs) + " jour(s))."
        )

    # 5) Plage horaire permise.
    # Convention CondoFix:
    # - 00:00 à 00:00 = disponible 24 h/24.
    # - Si l'heure de fin est plus petite ou égale à l'heure de début, on considère
    #   que la plage se termine le lendemain. Exemple: 14:00 à 00:00.
    is_24h_available = is_midnight(hre_debut_permise) and is_midnight(hre_fin_permise)

    if not is_24h_available and hre_debut_permise is not None and hre_fin_permise is not None:
        for requested_start, requested_end in requested_windows:
            allowed_start = datetime.combine(requested_start.date(), hre_debut_permise)
            allowed_end = datetime.combine(requested_start.date(), hre_fin_permise)

            if allowed_end <= allowed_start:
                allowed_end = allowed_end + timedelta(days=1)

            if requested_start < allowed_start or requested_end > allowed_end:
                errors.append(
                    "La réservation doit respecter la plage horaire permise pour cette ressource "
                    + "("
                    + hre_debut_permise.strftime("%H:%M")
                    + " à "
                    + hre_fin_permise.strftime("%H:%M")
                    + ")."
                )
                break

    # 6) Période temporaire de non-disponibilité.
    if date_debut_non_dispo not in (None, '', 'None') and duree_non_dispo_hres > 0:
        try:
            non_dispo_date = db_date_to_date(date_debut_non_dispo)

            non_dispo_start = datetime(
                non_dispo_date.year,
                non_dispo_date.month,
                non_dispo_date.day
            )

            non_dispo_end = non_dispo_start + timedelta(
                minutes=hours_to_minutes(duree_non_dispo_hres)
            )

            for requested_start, requested_end in requested_windows:
                if windows_overlap(requested_start, requested_end, non_dispo_start, non_dispo_end):
                    errors.append(
                        "Cette ressource est temporairement non disponible à partir du "
                        + str(non_dispo_date)
                        + " pour "
                        + str(duree_non_dispo_hres)
                        + " h."
                    )
                    break

        except (TypeError, ValueError):
            errors.append("La période de non-disponibilité configurée pour cette ressource est invalide.")

    # ---------------------------------------------------------------------
    # Validation des conflits avec réservations existantes
    # ---------------------------------------------------------------------

    if not errors:
        intervalle_minutes = hours_to_minutes(intervalle_rez_hres)

        cur.execute("""
            SELECT
                IDReservation,
                Date,
                HeureDebut,
                DureeHres,
                NoUnite
            FROM reservations
            WHERE IDClient = %s
              AND IDRessource = %s
        """, (client_ident, resource_id))

        conflicts = []

        for existing in cur.fetchall():
            existing_id = existing[0]
            existing_date = existing[1]
            existing_time = existing[2]
            existing_duration = existing[3]
            existing_unit = existing[4]

            existing_start = datetime.combine(
                db_date_to_date(existing_date),
                db_time_to_time(existing_time)
            )

            existing_end = existing_start + timedelta(
                minutes=hours_to_minutes(existing_duration)
            )

            protected_start = existing_start - timedelta(minutes=intervalle_minutes)
            protected_end = existing_end + timedelta(minutes=intervalle_minutes)

            for requested_start, requested_end in requested_windows:
                if windows_overlap(requested_start, requested_end, protected_start, protected_end):
                    conflicts.append({
                        "id": existing_id,
                        "date": existing_start.strftime("%Y-%m-%d"),
                        "start": existing_start.strftime("%H:%M"),
                        "end": existing_end.strftime("%H:%M"),
                        "unit": existing_unit
                    })
                    break

            if conflicts:
                break

        if conflicts:
            first_conflict = conflicts[0]

            errors.append(
                "Cette ressource est déjà réservée ou trop près d’une autre réservation."
            )

            errors.append(
                "Conflit détecté le "
                + first_conflict["date"]
                + " de "
                + first_conflict["start"]
                + " à "
                + first_conflict["end"]
                + " pour l'unité "
                + str(first_conflict["unit"])
                + "."
            )

            if intervalle_rez_hres > 0:
                errors.append(
                    "Intervalle obligatoire entre réservations : "
                    + str(intervalle_rez_hres)
                    + " h."
                )

    if errors:
        return flash_and_return(errors, cur, cnx)

    # ---------------------------------------------------------------------
    # Insertion des réservations consécutives
    # ---------------------------------------------------------------------

    utc_time = datetime.utcnow()
    tz = pytz.timezone('America/Montreal')
    local_time = utc_time.replace(tzinfo=pytz.UTC).astimezone(tz)

    for day_index in range(jrs_consecutifs):
        date_rez_courante = date_rez_obj + timedelta(days=day_index)

        cur.execute("""
            INSERT INTO reservations
                (
                    DateHeureCreation,
                    IDRessource,
                    IDClient,
                    Date,
                    HeureDebut,
                    DureeHres,
                    NoUnite,
                    Note,
                    Courriel,
                    ModePaiement
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [
            local_time,
            resource_id,
            client_ident,
            date_rez_courante,
            heure_rez_obj,
            duree_rez,
            no_unite,
            note,
            courriel,
            mode_de_paiement
        ])

    cnx.commit()

    # ---------------------------------------------------------------------
    # Courriel pour réservation facturable
    # ---------------------------------------------------------------------

    email_list = []

    cur.execute("""
        SELECT EmailRezFacturable
        FROM parametres
        WHERE IDClient = %s
    """, (client_ident,))

    for item in cur.fetchall():
        email_a = item[0]
        if email_a:
            email_list = [email.strip() for email in email_a.split(',') if email.strip()]

    mode_text = ''

    if mode_de_paiement != 0:
        cur.execute("""
            SELECT Description
            FROM modepaiement
            WHERE IDPaiement = %s
              AND IDClient = %s
        """, (mode_de_paiement, client_ident))

        mode_row = cur.fetchone()
        if mode_row is not None:
            mode_text = mode_row[0]

    cnx.close()

    if facturable == 1:
        _send_reservation_facturable_email(
            subject="Réservation facturable",
            recipients=email_list,
            desc_ress=desc_ress,
            no_unite=no_unite,
            date_rez=date_rez_raw,
            heure=heure_rez_raw,
            duree=str(duree_rez),
            jours=str(jrs_consecutifs),
            courriel=courriel,
            mode_de_paiement=mode_text,
            note=note
        )

    return redirect(url_for('bp_reservations.reservations_table'))

# fonctions pour ajouter une réservations
@bp_reservations.route("/reservation_ajout_proprio", methods=['POST'])
def reservation_ajout_proprio():
    """Ajout d'une réservation à la table reservations par les copropriétaires.

    La validation applique les mêmes contraintes métier que le formulaire admin:
    - ressource active du client;
    - unité positive;
    - date/heure/durée valides;
    - durée en blocs de 30 minutes;
    - limites de durée, délai minimal, délai maximal, jours consécutifs;
    - plage horaire permise;
    - période temporaire de non-disponibilité;
    - conflit avec réservations existantes, incluant l'intervalle obligatoire;
    - courriel et mode de paiement obligatoires pour les ressources facturables.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Vérifier si le client a acheté le module réservations.
    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]

    # ---------------------------------------------------------------------
    # Helpers locaux
    # ---------------------------------------------------------------------

    def parse_positive_integer(value):
        value = str(value or '').strip()

        if value.isdigit() and int(value) > 0:
            return int(value)

        return None

    def parse_float(value):
        try:
            return float(str(value or '').strip().replace(',', '.'))
        except (TypeError, ValueError):
            return None

    def parse_date(value):
        try:
            return datetime.strptime(str(value or '').strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    def parse_time(value):
        value = str(value or '').strip()

        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                pass

        return None

    def db_date_to_date(value):
        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()

    def db_time_to_time(value):
        if value in (None, '', 'None'):
            return None

        if isinstance(value, timedelta):
            return (datetime.min + value).time()

        if isinstance(value, time):
            return value

        value_as_text = str(value or '').strip()

        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(value_as_text[:8], fmt).time()
            except ValueError:
                pass

        return None

    def hours_to_minutes(value):
        return int(round(float(value or 0) * 60))

    def is_half_hour_increment(value):
        return value is not None and round(value * 2, 8).is_integer()

    def is_midnight(value):
        return (
            value is not None
            and value.hour == 0
            and value.minute == 0
            and value.second == 0
        )

    def windows_overlap(start_a, end_a, start_b, end_b):
        return start_a < end_b and end_a > start_b

    def load_form_lists(cur):
        fill_ressources = []
        fill_modes_paiement = []

        cur.execute("""
            SELECT
                IDRessource,
                Description,
                DureeMaxHres,
                DelaiMinHres,
                DelaiMaxJrs,
                JoursConsecutifsPermis,
                DateDebutNonDispo,
                DureeNonDispoHres,
                IntervalleRezHres,
                HreDebutPermise,
                HreFinPermise,
                Facturable
            FROM ressources
            WHERE Actif = 1
              AND IDClient = %s
            ORDER BY Description
        """, (client_ident,))

        for item in cur.fetchall():
            fill_ressources.append(item)

        cur.execute("""
            SELECT IDPaiement, Description
            FROM modepaiement
            WHERE IDClient = %s
            ORDER BY Description
        """, (client_ident,))

        for item in cur.fetchall():
            fill_modes_paiement.append(item)

        return fill_ressources, fill_modes_paiement

    def load_reservation_message(cur):
        message_affiche = 0
        message_rez = ''

        cur.execute("""
            SELECT AfficheMessageRez, MessageRez
            FROM parametres
            WHERE IDClient = %s
        """, (client_ident,))

        row = cur.fetchone()

        if row is not None:
            message_affiche = int(row[0] or 0)
            message_rez = row[1] or ''

        return message_affiche, message_rez

    def flash_and_return(errors, cur, cnx_to_close=None):
        form_data = {
            "ress_select": ress_select_raw,
            "no_unite": no_unite_raw,
            "date_rez": date_rez_raw,
            "heure_rez": heure_rez_raw,
            "duree_rez": duree_rez_raw,
            "jrs_consecutifs": jrs_consecutifs_raw,
            "note": note,
            "courriel": courriel,
            "mode_paiement": mode_paiement_raw
        }

        fill_ressources, fill_modes_paiement = load_form_lists(cur)
        message_affiche, message_rez = load_reservation_message(cur)

        if cnx_to_close is not None:
            cnx_to_close.close()

        flash(Markup("<br>".join(errors)), "warning")

        return render_template(
            'reservation_ajout_proprio.html',
            fill_ressources=fill_ressources,
            fill_modes_paiement=fill_modes_paiement,
            form_data=form_data,
            message_affiche=message_affiche,
            message_rez=message_rez,
            bd=profile_list[3]
        )

    # ---------------------------------------------------------------------
    # Lecture du formulaire
    # ---------------------------------------------------------------------

    errors = []

    ress_select_raw = (
        request.form.get('ress_select')
        or request.form.get('ident_ress')
        or ''
    ).strip()

    no_unite_raw = request.form.get('no_unite', '').strip()
    date_rez_raw = request.form.get('date_rez', '').strip()
    heure_rez_raw = request.form.get('heure_rez', '').strip()
    duree_rez_raw = request.form.get('duree_rez', '').strip()
    jrs_consecutifs_raw = request.form.get('jrs_consecutifs', '').strip()
    note = request.form.get('note', '').strip()
    courriel = request.form.get('courriel', '').strip()
    mode_paiement_raw = request.form.get('mode_paiement', '').strip()

    resource_id = parse_positive_integer(ress_select_raw)
    no_unite = parse_positive_integer(no_unite_raw)
    date_rez_obj = parse_date(date_rez_raw)
    heure_rez_obj = parse_time(heure_rez_raw)
    duree_rez = parse_float(duree_rez_raw)
    jrs_consecutifs = parse_positive_integer(jrs_consecutifs_raw)

    if resource_id is None:
        errors.append("Veuillez sélectionner une ressource valide.")

    if no_unite is None:
        errors.append("Le numéro d'unité doit être un nombre entier positif.")

    if date_rez_obj is None:
        errors.append("La date de réservation est invalide.")

    if heure_rez_obj is None:
        errors.append("L'heure de début est invalide.")

    if duree_rez is None or duree_rez <= 0:
        errors.append("La durée doit être supérieure à 0.")
    elif not is_half_hour_increment(duree_rez):
        errors.append("La durée doit être saisie en blocs de 30 minutes : 0.5, 1, 1.5, 2, etc.")

    if jrs_consecutifs is None:
        errors.append("Les jours consécutifs doivent être un nombre entier positif.")

    if len(note) > 200:
        errors.append("La note ne peut pas dépasser 200 caractères.")

    cnx = connect_db(mode)
    cur = cnx.cursor()

    # ---------------------------------------------------------------------
    # Lecture de la ressource sélectionnée
    # ---------------------------------------------------------------------

    desc_ress = ''
    facturable = 0
    duree_max = 0
    delai_min_hres = 0
    delai_max_jrs = 0
    date_debut_non_dispo = None
    duree_non_dispo_hres = 0
    jrs_consecutifs_permis = 0
    intervalle_rez_hres = 0
    hre_debut_permise = None
    hre_fin_permise = None

    if resource_id is not None:
        cur.execute("""
            SELECT
                Description,
                Facturable,
                DureeMaxHres,
                DelaiMinHres,
                DelaiMaxJrs,
                DateDebutNonDispo,
                DureeNonDispoHres,
                JoursConsecutifsPermis,
                IntervalleRezHres,
                HreDebutPermise,
                HreFinPermise
            FROM ressources
            WHERE IDRessource = %s
              AND IDClient = %s
              AND Actif = 1
        """, (resource_id, client_ident))

        ressource = cur.fetchone()

        if ressource is None:
            errors.append("La ressource sélectionnée est invalide ou inactive.")
        else:
            desc_ress = ressource[0]
            facturable = int(parse_float(ressource[1]) or 0)
            duree_max = parse_float(ressource[2]) or 0
            delai_min_hres = parse_float(ressource[3]) or 0
            delai_max_jrs = parse_float(ressource[4]) or 0
            date_debut_non_dispo = ressource[5]
            duree_non_dispo_hres = parse_float(ressource[6]) or 0
            jrs_consecutifs_permis = int(parse_float(ressource[7]) or 0)
            intervalle_rez_hres = parse_float(ressource[8]) or 0
            hre_debut_permise = db_time_to_time(ressource[9])
            hre_fin_permise = db_time_to_time(ressource[10])

    # ---------------------------------------------------------------------
    # Validation du mode de paiement
    # ---------------------------------------------------------------------

    if mode_paiement_raw == '':
        mode_de_paiement = 0
    else:
        mode_de_paiement = parse_positive_integer(mode_paiement_raw)

        if mode_de_paiement is None:
            errors.append("Le mode de paiement est invalide.")
            mode_de_paiement = 0
        else:
            cur.execute("""
                SELECT COUNT(*)
                FROM modepaiement
                WHERE IDPaiement = %s
                  AND IDClient = %s
            """, (mode_de_paiement, client_ident))

            if cur.fetchone()[0] == 0:
                errors.append("Le mode de paiement sélectionné est invalide.")

    if facturable == 1:
        if not courriel:
            errors.append("Le courriel est obligatoire pour une ressource facturable.")

        if mode_de_paiement == 0:
            errors.append("Le mode de paiement est obligatoire pour une ressource facturable.")

    if errors:
        return flash_and_return(errors, cur, cnx)

    # ---------------------------------------------------------------------
    # Validation des contraintes de la ressource
    # ---------------------------------------------------------------------

    now_montreal = datetime.now(
        pytz.timezone('America/Montreal')
    ).replace(tzinfo=None)

    requested_windows = []

    for day_index in range(jrs_consecutifs):
        requested_start = datetime.combine(
            date_rez_obj + timedelta(days=day_index),
            heure_rez_obj
        )

        requested_end = requested_start + timedelta(
            minutes=hours_to_minutes(duree_rez)
        )

        requested_windows.append((requested_start, requested_end))

    first_requested_start = requested_windows[0][0]
    last_requested_start = requested_windows[-1][0]

    if duree_max > 0 and duree_rez > duree_max:
        errors.append(
            "La durée demandée dépasse la durée maximale permise pour cette ressource "
            + "(" + str(duree_max) + " h)."
        )

    if jrs_consecutifs_permis > 0 and jrs_consecutifs > jrs_consecutifs_permis:
        errors.append(
            "Le nombre de jours consécutifs dépasse la limite permise pour cette ressource "
            + "(" + str(jrs_consecutifs_permis) + " jour(s))."
        )

    delai_rez_hres = (first_requested_start - now_montreal).total_seconds() / 3600

    if delai_rez_hres < 0:
        errors.append("La réservation ne peut pas être créée dans le passé.")
    elif delai_min_hres > 0 and delai_rez_hres < delai_min_hres:
        errors.append(
            "La réservation ne respecte pas le délai minimal configuré pour cette ressource "
            + "(" + str(delai_min_hres) + " h)."
        )

    delai_rez_jrs = (last_requested_start - now_montreal).total_seconds() / 86400

    if delai_max_jrs > 0 and delai_rez_jrs > delai_max_jrs:
        errors.append(
            "La réservation dépasse le délai maximal configuré pour cette ressource "
            + "(" + str(delai_max_jrs) + " jour(s))."
        )

    # Convention CondoFix:
    # - 00:00 à 00:00 = disponible 24 h/24.
    # - Si l'heure de fin est plus petite ou égale à l'heure de début,
    #   la plage se termine le lendemain.
    is_24h_available = is_midnight(hre_debut_permise) and is_midnight(hre_fin_permise)

    if not is_24h_available and hre_debut_permise is not None and hre_fin_permise is not None:
        for requested_start, requested_end in requested_windows:
            allowed_start = datetime.combine(requested_start.date(), hre_debut_permise)
            allowed_end = datetime.combine(requested_start.date(), hre_fin_permise)

            if allowed_end <= allowed_start:
                allowed_end = allowed_end + timedelta(days=1)

            if requested_start < allowed_start or requested_end > allowed_end:
                errors.append(
                    "La réservation doit respecter la plage horaire permise pour cette ressource "
                    + "("
                    + hre_debut_permise.strftime("%H:%M")
                    + " à "
                    + hre_fin_permise.strftime("%H:%M")
                    + ")."
                )
                break

    if date_debut_non_dispo not in (None, '', 'None') and duree_non_dispo_hres > 0:
        try:
            non_dispo_date = db_date_to_date(date_debut_non_dispo)

            non_dispo_start = datetime(
                non_dispo_date.year,
                non_dispo_date.month,
                non_dispo_date.day
            )

            non_dispo_end = non_dispo_start + timedelta(
                minutes=hours_to_minutes(duree_non_dispo_hres)
            )

            for requested_start, requested_end in requested_windows:
                if windows_overlap(requested_start, requested_end, non_dispo_start, non_dispo_end):
                    errors.append(
                        "Cette ressource est temporairement non disponible à partir du "
                        + str(non_dispo_date)
                        + " pour "
                        + str(duree_non_dispo_hres)
                        + " h."
                    )
                    break

        except (TypeError, ValueError):
            errors.append("La période de non-disponibilité configurée pour cette ressource est invalide.")

    # ---------------------------------------------------------------------
    # Validation des conflits avec réservations existantes
    # ---------------------------------------------------------------------

    if not errors:
        intervalle_minutes = hours_to_minutes(intervalle_rez_hres)
        today_montreal = datetime.now(
            pytz.timezone('America/Montreal')
        ).strftime('%Y-%m-%d')

        cur.execute("""
            SELECT
                IDReservation,
                Date,
                HeureDebut,
                DureeHres,
                NoUnite
            FROM reservations
            WHERE IDClient = %s
              AND IDRessource = %s
              AND Date >= %s
        """, (client_ident, resource_id, today_montreal))

        conflicts = []

        for existing in cur.fetchall():
            existing_id = existing[0]
            existing_date = existing[1]
            existing_time = existing[2]
            existing_duration = existing[3]
            existing_unit = existing[4]

            existing_start = datetime.combine(
                db_date_to_date(existing_date),
                db_time_to_time(existing_time)
            )

            existing_end = existing_start + timedelta(
                minutes=hours_to_minutes(existing_duration)
            )

            protected_start = existing_start - timedelta(minutes=intervalle_minutes)
            protected_end = existing_end + timedelta(minutes=intervalle_minutes)

            for requested_start, requested_end in requested_windows:
                if windows_overlap(requested_start, requested_end, protected_start, protected_end):
                    conflicts.append({
                        "id": existing_id,
                        "date": existing_start.strftime("%Y-%m-%d"),
                        "start": existing_start.strftime("%H:%M"),
                        "end": existing_end.strftime("%H:%M"),
                        "unit": existing_unit
                    })
                    break

            if conflicts:
                break

        if conflicts:
            first_conflict = conflicts[0]

            errors.append(
                "Cette ressource est déjà réservée ou trop près d’une autre réservation."
            )

            errors.append(
                "Conflit détecté le "
                + first_conflict["date"]
                + " de "
                + first_conflict["start"]
                + " à "
                + first_conflict["end"]
                + " pour l'unité "
                + str(first_conflict["unit"])
                + "."
            )

            if intervalle_rez_hres > 0:
                errors.append(
                    "Intervalle obligatoire entre réservations : "
                    + str(intervalle_rez_hres)
                    + " h."
                )

    if errors:
        return flash_and_return(errors, cur, cnx)

    # ---------------------------------------------------------------------
    # Insertion des réservations consécutives
    # ---------------------------------------------------------------------

    utc_time = datetime.utcnow()
    tz = pytz.timezone('America/Montreal')
    local_time = utc_time.replace(tzinfo=pytz.UTC).astimezone(tz)

    for day_index in range(jrs_consecutifs):
        date_rez_courante = date_rez_obj + timedelta(days=day_index)

        cur.execute("""
            INSERT INTO reservations
                (
                    DateHeureCreation,
                    IDRessource,
                    IDClient,
                    Date,
                    HeureDebut,
                    DureeHres,
                    NoUnite,
                    Note,
                    Courriel,
                    ModePaiement
                )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, [
            local_time,
            resource_id,
            client_ident,
            date_rez_courante,
            heure_rez_obj,
            duree_rez,
            no_unite,
            note,
            courriel,
            mode_de_paiement
        ])

    cnx.commit()

    # ---------------------------------------------------------------------
    # Courriel pour réservation facturable
    # ---------------------------------------------------------------------

    email_list = []

    cur.execute("""
        SELECT EmailRezFacturable
        FROM parametres
        WHERE IDClient = %s
    """, (client_ident,))

    for item in cur.fetchall():
        email_a = item[0]
        if email_a:
            email_list = [
                email.strip()
                for email in email_a.split(',')
                if email.strip()
            ]

    mode_text = ''

    if mode_de_paiement != 0:
        cur.execute("""
            SELECT Description
            FROM modepaiement
            WHERE IDPaiement = %s
              AND IDClient = %s
        """, (mode_de_paiement, client_ident))

        mode_row = cur.fetchone()

        if mode_row is not None:
            mode_text = mode_row[0]

    cnx.close()

    if facturable == 1:
        _send_reservation_facturable_email(
            subject="Réservation facturable",
            recipients=email_list,
            desc_ress=desc_ress,
            no_unite=no_unite,
            date_rez=date_rez_raw,
            heure=heure_rez_raw,
            duree=str(duree_rez),
            jours=str(jrs_consecutifs),
            courriel=courriel,
            mode_de_paiement=mode_text,
            note=note
        )

    flash("La réservation a été enregistrée.", "success")
    return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))

# affichage de la page de 'mes reservations'
@bp_reservations.route("/mes_rez")
def mes_rez():
    """Afficher les réservations futures du syndicat pour les copropriétaires.

    Note importante:
    La table reservations ne contient actuellement pas d'identifiant d'usager créateur.
    Il n'est donc pas possible de limiter cette vue aux réservations créées par
    l'usager connecté sans modifier le modèle de données.

    MVP:
    - afficher toutes les réservations futures du client;
    - offrir une recherche dans la table;
    - permettre l'annulation seulement par POST et seulement pour les réservations futures.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Vérifier si le client a acheté le module réservations.
    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]
    today_montreal = datetime.now(
        pytz.timezone('America/Montreal')
    ).strftime('%Y-%m-%d')

    def format_duration_label(value):
        """Retourne un libellé lisible: 30 min, 1 h, 1 h 30, 4 h, etc."""
        minutes_total = _hours_to_minutes(value)

        if minutes_total <= 0:
            return "0 min"

        hours = minutes_total // 60
        minutes = minutes_total % 60

        if hours == 0:
            return str(minutes) + " min"

        if minutes == 0:
            return str(hours) + " h"

        return str(hours) + " h " + str(minutes).zfill(2)

    cnx = connect_db(mode)
    cur = cnx.cursor()

    cur.execute("""
        SELECT
            rez.IDReservation,
            rez.IDRessource,
            rez.Date,
            rez.HeureDebut,
            rez.DureeHres,
            rez.NoUnite,
            COALESCE(rez.Note, ''),
            COALESCE(ress.Description, ''),
            COALESCE(ress.Facturable, 0)
        FROM reservations rez
        LEFT JOIN ressources ress
            ON ress.IDRessource = rez.IDRessource
           AND ress.IDClient = rez.IDClient
        WHERE rez.Date >= %s
          AND rez.IDClient = %s
        ORDER BY rez.Date, rez.HeureDebut, rez.NoUnite
    """, (today_montreal, client_ident))

    reservations = []

    for row in cur.fetchall():
        start_datetime, end_datetime = _build_reservation_window(
            row[2],
            row[3],
            row[4]
        )

        reservations.append({
            "id": row[0],
            "resource_id": row[1],
            "date": row[2],
            "date_label": start_datetime.strftime("%Y-%m-%d"),
            "date_order": start_datetime.strftime("%Y-%m-%d"),
            "start_label": start_datetime.strftime("%H:%M"),
            "start_order": start_datetime.strftime("%H:%M"),
            "end_label": end_datetime.strftime("%H:%M"),
            "duration_label": format_duration_label(row[4]),
            "no_unite": row[5],
            "note": row[6] or "—",
            "ressource": row[7] or "—",
            "facturable": int(row[8] or 0)
        })

    cnx.close()

    total_reservations = len(reservations)
    total_units = len({str(item["no_unite"]) for item in reservations if item["no_unite"]})
    total_resources = len({str(item["resource_id"]) for item in reservations if item["resource_id"]})

    prochaine_reservation = "Aucune réservation future"
    if reservations:
        first = reservations[0]
        prochaine_reservation = (
            first["date_label"]
            + " "
            + first["start_label"]
            + " — "
            + first["ressource"]
            + " — unité "
            + str(first["no_unite"])
        )

    return render_template(
        'reservations_mon_unite.html',
        reservations=reservations,
        total_reservations=total_reservations,
        total_units=total_units,
        total_resources=total_resources,
        prochaine_reservation=prochaine_reservation,
        bd=profile_list[3]
    )

# Ancienne route conservée pour compatibilité avec les anciens formulaires/liens.
@bp_reservations.route("/reservations_unite", methods=['POST', 'GET'])
def reservations_unite():
    """Ancienne recherche par numéro d'unité.

    La page copropriétaire affiche maintenant toutes les réservations futures
    du client et utilise une recherche côté table.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    return redirect(url_for('bp_reservations.mes_rez'))

# fonctions pour supprimer une réservation
@bp_reservations.route("/rez_unite_supprime/<int:id_rez>", methods=['POST'])
def rez_unite_supprime(id_rez):
    """Annuler une réservation future à partir de la page copropriétaire.

    Sécurité MVP:
    - suppression par POST seulement;
    - restriction au client connecté;
    - restriction aux réservations futures.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode = profile_list[8]
    today_montreal = datetime.now(
        pytz.timezone('America/Montreal')
    ).strftime('%Y-%m-%d')

    cnx = connect_db(mode)
    cur = cnx.cursor()

    cur.execute("""
        SELECT
            rez.IDRessource,
            rez.Date,
            rez.HeureDebut,
            rez.DureeHres,
            rez.NoUnite,
            COALESCE(rez.Note, ''),
            COALESCE(ress.Facturable, 0),
            COALESCE(ress.Description, '')
        FROM reservations rez
        LEFT JOIN ressources ress
            ON ress.IDRessource = rez.IDRessource
           AND ress.IDClient = rez.IDClient
        WHERE rez.IDReservation = %s
          AND rez.IDClient = %s
          AND rez.Date >= %s
    """, (id_rez, client_ident, today_montreal))

    reservation = cur.fetchone()

    if reservation is None:
        cnx.close()
        flash("La réservation est introuvable ou ne peut plus être annulée.", "warning")
        return redirect(url_for('bp_reservations.mes_rez'))

    id_ressource = reservation[0]
    date = str(reservation[1])
    heure = str(reservation[2])
    duree = str(reservation[3])
    no_unite = reservation[4]
    note = reservation[5]
    facturable = int(reservation[6] or 0)
    desc_ress = reservation[7]

    cur.execute("""
        DELETE FROM reservations
        WHERE IDReservation = %s
          AND IDClient = %s
          AND Date >= %s
    """, (id_rez, client_ident, today_montreal))

    cnx.commit()

    email_list = []

    if facturable == 1:
        cur.execute("""
            SELECT EmailRezFacturable
            FROM parametres
            WHERE IDClient = %s
        """, (client_ident,))

        for item in cur.fetchall():
            email_a = item[0]
            if email_a:
                email_list = [
                    email.strip()
                    for email in email_a.split(',')
                    if email.strip()
                ]

    cnx.close()

    if facturable == 1:
        _send_reservation_facturable_email(
            subject="Annulation d'une réservation facturable",
            recipients=email_list,
            desc_ress=desc_ress,
            no_unite=no_unite,
            date_rez=date,
            heure=heure,
            duree=duree,
            note=note
        )

    flash("La réservation a été annulée.", "success")
    return redirect(url_for('bp_reservations.mes_rez'))

#fonctions pour supprimer une réservation par l'administrateur
@bp_reservations.route("/reservation_supprimer/<id_rez>", methods=['POST','GET'])
def reservation_supprimer(id_rez):
    """Suppression d'un enregistrement par l'admin."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()

    id_ressource=0
    facturable=0
    desc_ress=''
    date=''
    heure=''
    duree=0
    note=str()
    no_unite=str()
    futur=0

    #trouver ressource de la réservation (premier élément des paramètres)
    cur.execute("SELECT IDRessource, Date, HeureDebut, DureeHres, NoUnite, Note from reservations WHERE IDReservation=%s AND IDClient=%s",(id_rez,client_ident))
    for item in cur.fetchall():
        id_ressource=item[0]
        if item[1]>=datetime.now().date():
            futur=1
        date=str(item[1])
        heure=str(item[2])
        duree=str(item[3])
        note=item[5]
        no_unite=str(item[4])
    #trouver type de réservation (facturable)
    cur.execute("SELECT Facturable,Description from ressources WHERE IDRessource=%s AND IDClient=%s",(id_ressource,client_ident))
    for item_1 in cur.fetchall():
        facturable=item_1[0]
        desc_ress=item_1[1]
    # supprimer la réservation
    cur.execute("DELETE FROM reservations WHERE IDReservation=%s AND IDClient=%s",(id_rez,client_ident))
    cnx.commit()
    email_list=[]
    # si réservation est facturable, aviser de la suppression par email
    # ATTENTION: seulement pour rez dans le futur
    if facturable == 1 and futur == 1:
        cur.execute(
            "SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",
            (client_ident,)
        )

        for item_2 in cur.fetchall():
            email_a = item_2[0] or ""
            email_list = [
                email.strip()
                for email in email_a.split(',')
                if email.strip()
            ]

        _send_reservation_facturable_email(
            subject="Annulation d'une réservation facturable",
            recipients=email_list,
            desc_ress=desc_ress,
            no_unite=no_unite,
            date_rez=date,
            heure=heure,
            duree=duree,
            note=note
        )

    cnx.close()
    return redirect(url_for("bp_reservations.reservations_table"))

#fonctions pour supprimer des réservations en bloc par l'administrateur
@bp_reservations.route("/supprime_bloc_affiche", methods=['POST','GET'])
def supprime_bloc_affiche():
    """Suppression d'un bloc d'enregistrements par l'admin."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    # trouver les ressources actives
    cur.execute("SELECT IDRessource, Description FROM ressources WHERE Actif=%s AND IDClient=%s",(1,client_ident))
    liste_ressources=cur.fetchall()
    return render_template('reservation_supprime_bloc.html', liste_ressources=liste_ressources, bd=profile_list[3])

#fonctions pour supprimer des réservations en bloc par l'administrateur
@bp_reservations.route("/supprime_bloc", methods=['POST','GET'])
def supprime_bloc():
    """Suppression d'un bloc d'enregistrements par l'admin."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    no_unite=int(request.form['no_unite'])
    id_ress = request.form['ress']
    date_debut = request.form['date_debut']
    date_fin = request.form['date_fin']
    # convertir date en datetime
    date_start = datetime.strptime(date_debut, "%Y-%m-%d").date
    date_end = datetime.strptime(date_fin, "%Y-%m-%d").date
    # placer les réservations visées dans une liste
    list_rez_supprime=[]
    cur.execute("SELECT IDReservation from reservations WHERE Date>=%s AND Date<=%s AND IDRessource=%s AND NoUnite=%s AND IDClient=%s",(date_debut,date_fin,id_ress,no_unite,client_ident))
    for item in cur.fetchall():
        list_rez_supprime.append(item[0])
    print(list_rez_supprime)
    # test pour vérifier que critères de sélection sont ok (liste vide)
    if len(list_rez_supprime)==0:
        flash('Aucun enregistrement trouvé pour ces critères','warning')
        return render_template('reservation_supprime_bloc.html', bd=profile_list[3])

    # # supprimer les réservations de la liste
    for item in list_rez_supprime:
        cur.execute("DELETE FROM reservations WHERE IDReservation=%s AND IDClient=%s",(item,client_ident))
        cnx.commit()
    cnx.close()
    return redirect(url_for("bp_reservations.reservations_table"))

@bp_reservations.route("/afficher_de_date_1", methods=['POST','GET'])
def afficher_de_date_1():
    """afficher la page de la table de réservations à partir de date spécifiée
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    # # sélectionner enregistrements depuis date demandée
    date = request.form['date_debut']
    if date == '':
        flash('Vous devez sélectionner une date de début des réservations.', "warning")
        return redirect(url_for('bp_reservations.reservations_table'))
    # convertir date en datetime
    date_hre = datetime.strptime(date, "%Y-%m-%d")

    client_ident = profile_list[0]
    fill_reservations = []
    cur.execute("SELECT IDReservation, IDRessource, Date, HeureDebut, DureeHres, NoUnite, DateHeureCreation, Note,"
                "Courriel, ModePaiement FROM reservations WHERE Date>%s AND IDClient=%s", (date_hre,client_ident))
    for row in cur.fetchall():
        cur.execute("SELECT Description FROM ressources WHERE IDRessource=%s AND IDClient=%s", (row[1], client_ident))
        for item in cur.fetchall():
            ressource = item
            row += (ressource)
        cur.execute("SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s", (row[9], client_ident))
        for item in cur.fetchall():
            desc_mode_paiement = item[0]
            row += (desc_mode_paiement,)
        fill_reservations.append(row)
    cnx.close()
    return render_template('reservations_table.html', fill_reservations=fill_reservations, date=date_hre.date(), bd=profile_list[3])
