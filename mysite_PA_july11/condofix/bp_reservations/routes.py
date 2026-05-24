from flask import Blueprint, render_template,session,url_for,redirect,request,flash
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
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback
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

# @bp_reservations.route("/calendrier_rez/<usager>")
# def calendrier_rez(usager):
#     """Afficher les réservations des copropriétaires à l'aide du calendrier javascript. Affiche
#     seulement les enregistrements à partir de la date actuelle et permet d'ajouter une réservation.
#     Application d'un code de couleur selon la ressource spécifiée"""
#
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#
#     profile_list = session.get('ProfilUsager')
#
#     # vérifier si le client a acheté le module réservations
#     if profile_list[5] == 0:
#         return redirect(url_for('bp_admin.permission'))
#
#     client_ident = profile_list[0]
#     mode = profile_list[8]
#
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#
#     # ---------------------------------------------------------------------
#     # 1) Ressources actives + padding à 10 (on garde pour compat CSS .ressource_1..10)
#     # ---------------------------------------------------------------------
#     liste_ress_actives = []
#     cur.execute(
#         "SELECT IDRessource, Description FROM ressources WHERE Actif=1 AND IDClient=%s",
#         (client_ident,)
#     )
#     for item in cur.fetchall():
#         liste_ress_actives.append(item)
#
#     while len(liste_ress_actives) < 10:
#         liste_ress_actives.append((0, ''))
#
#     # ---------------------------------------------------------------------
#     # 2) Map IDRessource -> couleur (basé sur l'ordre de liste_ress_actives)
#     #    (ignore les placeholders (0,''))
#     # ---------------------------------------------------------------------
#     colors = [
#         'black', 'lawngreen', 'blue', 'red', 'orange',
#         'pink', 'lightslategrey', 'magenta', 'peru', 'purple'
#     ]
#     color_by_ressource = {}
#     for idx, (res_id, desc) in enumerate(liste_ress_actives):
#         if res_id and desc:
#             if idx < len(colors):
#                 color_by_ressource[res_id] = colors[idx]
#
#     # Also keep description by resource id (for tooltips)
#     desc_by_ressource = {}
#     for res_id, desc in liste_ress_actives:
#         if res_id and desc:
#             desc_by_ressource[res_id] = desc
#
#     # ---------------------------------------------------------------------
#     # 3) Réservations à partir d'aujourd'hui -> events_list
#     #    - dict neuf par event (pas de "stale values")
#     #    - start en ISO string (FullCalendar friendly)
#     #    - skip si ressource inactive / non mappée
#     # ---------------------------------------------------------------------
#     cur.execute(
#         "SELECT IDReservation, IDRessource, Date, HeureDebut, DureeHres, NoUnite, Note "
#         "FROM reservations "
#         "WHERE Date >= %s AND IDClient = %s",
#         (datetime.now().strftime('%Y-%m-%d'), client_ident)
#     )
#
#     events_list = []
#     for row in cur.fetchall():
#         res_id = row[1]
#
#         # ignorer réservations dont la ressource n'est pas active / pas mappée
#         if res_id not in color_by_ressource:
#             continue
#
#         date_s = str(row[2])          # YYYY-MM-DD
#         time_s = str(row[3])          # H:MM:SS ou HH:MM:SS
#
#         # parsing robuste HH/MM/SS
#         parts = time_s.split(':')
#         hh = int(parts[0])
#         mm = int(parts[1]) if len(parts) > 1 else 0
#         ss = int(parts[2]) if len(parts) > 2 else 0
#
#         start_dt = datetime(
#             int(date_s[0:4]),
#             int(date_s[5:7]),
#             int(date_s[8:10]),
#             hh, mm, ss
#         )
#
#         events_list.append({
#             "no_unite": row[5],
#             "date_heure": start_dt.isoformat(),
#             "ressource": res_id,
#             "duree": row[4],
#             "couleur": color_by_ressource[res_id],
#             "note": row[6],
#             "ressource_desc": desc_by_ressource.get(res_id, "")
#         })
#
#     cnx.close()
#
#     if usager == 'admin':
#         return render_template(
#             'calendrier_rez_admin.html',
#             events_list=events_list,
#             fill_ressources=liste_ress_actives,
#             bd=profile_list[3]
#         )
#     else:  # proprio
#         return render_template(
#             'calendrier_rez.html',
#             events_list=events_list,
#             fill_ressources=liste_ress_actives,
#             bd=profile_list[3]
#         )


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
# @bp_reservations.route("/reservation_affiche_admin", methods=['GET','POST'])
# def reservation_affiche_admin():
#     """Afficher l'écran pour effectuer une réservation pour l'admin"""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     # vérifier type d'usager si  admin condofix
#     if profile_list[2] > 2:
#         return redirect(url_for('bp_admin.permission'))
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#     fill_ressources=[]
#     fill_modes_paiement=[]
#     cur.execute("SELECT IDRessource,Description FROM ressources WHERE Actif=1 AND IDClient=%s", (client_ident,))
#     for item in cur.fetchall():
#         fill_ressources.append(item)
#     cur.execute("SELECT IDPaiement,Description FROM modepaiement WHERE IDClient=%s", (client_ident,))
#     for item in cur.fetchall():
#         fill_modes_paiement.append(item)
#     cnx.close()
#     return render_template('reservation_ajout_admin.html',fill_ressources=fill_ressources, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])

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
# @bp_reservations.route("/reservation_affiche_proprio", methods=['GET','POST'])
# def reservation_affiche_proprio():
#     """Afficher l'écran pour effectuer une réservation pour les copropriétaires.
#     Les champs sont remplis selon les paramètres fixés pour la ressource sélectionnée dans le calendrier de réservations."""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#     fill_ressource=[]
#     fill_modes_paiement=[]
#     ident_ress=request.form.get('ress_select')
#     desc_ressource=str()
#     cur.execute("SELECT Description FROM ressources WHERE IDRessource=%s AND IDClient=%s", (ident_ress,client_ident))
#     row = cur.fetchone()
#     if row == None:  # pas d'enregistrement trouvé: on retourne au calendrier de réservation
#         return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))
#     else:
#         desc_ressource=row[0]
#
#     # pour remplir combo de mode de paiement
#     cur.execute("SELECT IDPaiement,Description FROM modepaiement WHERE IDClient=%s", (client_ident,))
#     for item in cur.fetchall():
#         fill_modes_paiement.append(item)
#
#     # pour afficher un message avant de permettre la réservation
#     message_affiche=0
#     message_rez=str()
#     cur.execute("SELECT AfficheMessageRez, MessageRez FROM parametres WHERE IDClient=%s", (client_ident,))
#     for item in cur.fetchall():
#         if item[0]==1:
#             message_affiche=1
#             message_rez=item[1]
#
#     # pour remplir les champs de date, heure et durée (déclarer variables globales)
#     date_debut=datetime
#     delai=int()
#     hre_debut=datetime
#     rez_duree=float()
#     delai_min_hres=float()
#     delai_max_jrs=0
#     interv_rez_hres=float()
#     hre_debut_permise = datetime
#     # aller chercher la valeur des paramètres pour cette ressource
#     cur.execute("SELECT  DureeMaxHres, DelaiMinHres, HreDebutPermise, HreFinPermise, DelaiMaxJrs, IntervalleRezHres FROM ressources WHERE Actif=1 "
#                 "AND IDRessource=%s AND IDClient=%s", (ident_ress, client_ident))
#     for item in cur.fetchall():
#         rez_duree=item[0]
#         delai_min_hres=item[1]
#         hre_debut_permise=item[2]
#         hre_fin_permise=item[3]
#         delai_max_jrs=item[4]
#         interv_rez_hres=item[5]
#
#     # 1- Pour la prod, convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
#     # donne aussi l'heure locale sur l'environnement dev
#     utc_time = datetime.utcnow()
#     tz = pytz.timezone('America/Montreal')
#     utc_time_1 =utc_time.replace(tzinfo=pytz.UTC) #replace method
#     local_time=utc_time_1.astimezone(tz)
#     dateheure=datetime.now()
#     # 2- Ajouter le délai min en h. à l’heure actuelle de la demande = heure_act_delai
#     heure_act_delai=local_time+timedelta(hours=delai_min_hres)
#     #return 'delai:'+str(delai_min_hres)+'dateheure avec delai:'+str(heure_act_delai)
#
#     # 3- Vérifier si heure act_delai de demande >paramètre heure début permise.
#     # transformer hre_debut_permise dans paramètres en format datetime.time
#     # par ex. selon que l'heure de début permise (dans bd) se lit '8:00'  ou '18:00'
#
#     if len(str(hre_debut_permise).split(':')[0])==1:
#         dateheure = datetime.strptime(str(hre_debut_permise),"%H:%M:%S")
#     if len(str(hre_debut_permise).split(':')[0])==2:
#         dateheure = datetime.strptime(str(hre_debut_permise),"%H:%M:%S")
#     #heure_debut=dateheure.time()
#     heure_debut = datetime.time(dateheure)
#     #print('Dateheure:',dateheure)
#     #print('heure début en datetime:', heure_debut)
#
#     if heure_act_delai.time()>heure_debut:
#         dateheure_act=heure_act_delai+timedelta(days=1)
#         dateheure_dem=datetime.strptime(str(dateheure_act.date())+' '+str(heure_debut),"%Y-%m-%d %H:%M:%S")
#     else:
#         dateheure_dem=datetime.strptime(str(heure_act_delai.date())+' '+str(heure_debut),"%Y-%m-%d %H:%M:%S")
#
#     # vérifier si conflit avec réservations actuelles (boucle):
#     # requête des enregistrements de réservation pour cette ressource avec date >= date demandée
#     liste_enreg=[]
#     cur.execute("SELECT IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite FROM reservations WHERE IDRessource=%s AND Date>=%s AND IDClient=%s",
#                 (ident_ress, dateheure_dem.date(), client_ident))
#     for row in cur.fetchall():
#         date_1=row[2]
#         time_delta=row[3]
#         date=str(date_1)
#         time=str(time_delta)
#         enreg_time=datetime.strptime(date+' '+time,"%Y-%m-%d %H:%M:%S")
#         de= enreg_time
#         secondes_debut_enreg= float(de.timestamp())
#         plage=float(row[4]*3600)
#         secondes_fin_enreg=float(secondes_debut_enreg)+plage
#         enreg=(secondes_debut_enreg,secondes_fin_enreg)
#         liste_enreg.append(enreg)
#
#     # si liste est vide, on va directement à l'affichage de la page de nouvelle réservation
#     if len(liste_enreg)==0:
#         # prévoir date avec délai minimum
#         date_today=datetime.now().date()
#         date_debut=date_today+timedelta(days=round(delai_min_hres/24))
#         if message_affiche==0:
#             return render_template('reservation_ajout_proprio.html', id_ress=ident_ress, desc_ressource=desc_ressource,
#                                date=dateheure_dem.date(), heure=dateheure_dem.time(), duree=rez_duree, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])
#         else:
#             return render_template('reservation_ajout_proprio_message.html', id_ress=ident_ress, desc_ressource=desc_ressource,
#                                    date=dateheure_dem.date(), heure=dateheure_dem.time(), duree=rez_duree,
#                                    fill_modes_paiement=fill_modes_paiement, message_rez=message_rez, bd=profile_list[3])
#
#     # la liste contient des réservations: trier la liste des enregistrements à partir d'aujourd'hui
#     liste_enreg.sort( key=lambda tup: tup[0])
#     cnx.close()
#     compteur_jrs=0
#     conflit=False
#
#     # heure de réservation selon les jours consécutifs débutant à 0
#     #rez_time = rez_time+timedelta(days=round(delai_min_hres/24,0))
#     # secondes depuis 1970-01-01
#
#     # pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
#     # on retranche/ajoute l'intervalle exigé entre chaque réservation
#     # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
#     secondes_rez_debut = dateheure_dem.timestamp()-(float(interv_rez_hres)*3600)+1
#     secondes_rez_fin = dateheure_dem.timestamp()+float(rez_duree*3600)+(float(interv_rez_hres)*3600)-2
#     nbr_enreg=len(liste_enreg)
#     # voir s'il y a chevauchement avec une réservation actuelle
#     while compteur_jrs<delai_max_jrs:
#         enreg_courant=0
#         for item in liste_enreg:
#             secondes_debut_enreg= item[0]
#             secondes_fin_enreg=item[1]
#             # ne pas traiter les enregistrements précédant la date rajustée avec compteurs jours
#             if secondes_rez_debut>secondes_fin_enreg:
#                 enreg_courant+=1
#                 if enreg_courant==nbr_enreg: # pas d'enregistrement applicable à la demande, on sort de la boucle et on affiche la page de nouvelle rez
#                     date_debut=dateheure_dem+timedelta(days=compteur_jrs)
#                     if message_affiche == 0:
#                         return render_template('reservation_ajout_proprio.html', id_ress=ident_ress, desc_ressource=desc_ressource, date=date_debut.date(),
#                                        heure=date_debut.time(), duree=rez_duree, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])
#                     else:
#                         return render_template('reservation_ajout_proprio_message.html', id_ress=ident_ress,
#                                         desc_ressource=desc_ressource, date=date_debut.date(),
#                                         heure=date_debut.time(), duree=rez_duree,
#                                         fill_modes_paiement=fill_modes_paiement, message_rez=message_rez, bd=profile_list[3])
#
#                 else:
#                     continue
#
#
#             # print('enreg:',secondes_debut_enreg, secondes_fin_enreg)
#             # print('enreg:',datetime.fromtimestamp(secondes_debut_enreg),datetime.fromtimestamp(secondes_fin_enreg))
#             # print('rez:',secondes_rez_debut, secondes_rez_fin)
#             # print('rez:',datetime.fromtimestamp(secondes_rez_debut),datetime.fromtimestamp(secondes_rez_fin))
#             # print('compteur:',compteur_jrs)
#
#             if secondes_rez_debut<=secondes_debut_enreg<=secondes_rez_fin:
#                 conflit=True
#             elif secondes_debut_enreg<=secondes_rez_debut<=secondes_fin_enreg:
#                 conflit=True
#
#             if conflit==True:
#                 conflit=False
#                 compteur_jrs+=1
#                 # supprimer enregistrement de la liste pour éviter erreur de comparaison multiple
#
#                 #liste_enreg.remove(item)
#                 dr = dateheure_dem+timedelta(days=compteur_jrs)
#
#                 # secondes depuis 1970-01-01
#                 # pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
#                 # on retranche/ajoute l'intervalle exigé entre chaque réservation
#                 # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
#                 secondes_rez_debut = dr.timestamp()-(float(interv_rez_hres)*3600)+1
#                 secondes_rez_fin=dr.timestamp()+float(rez_duree*3600)+(float(interv_rez_hres)*3600)-2
#                 break
#             else:
#                 date_debut=dateheure_dem+timedelta(days=compteur_jrs)
#                 if message_affiche == 0:
#                     return render_template('reservation_ajout_proprio.html', id_ress=ident_ress, desc_ressource=desc_ressource, date=date_debut.date(),
#                                        heure=date_debut.time(), duree=rez_duree, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])
#                 else:
#                     return render_template('reservation_ajout_proprio_message.html', id_ress=ident_ress,
#                                            desc_ressource=desc_ressource, date=date_debut.date(),
#                                            heure=date_debut.time(), duree=rez_duree,
#                                            fill_modes_paiement=fill_modes_paiement, message_rez=message_rez, bd=profile_list[3])

        # fin de la boucle WHILE compteur




#fonctions pour ajouter une réservations
# fonctions pour ajouter une réservation
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

    if facturable == 1 and email_list:
        yahoo_mail_user = 'condofix.ca@yahoo.com'

        # TODO PBI sécurité:
        # déplacer ce mot de passe dans une variable d'environnement.
        yahoo_mail_password = 'spyvlumgfwscqfkc'

        msg = MIMEMultipart("related")
        msg['Subject'] = "Réservation facturable"
        msg['From'] = yahoo_mail_user

        html = """
            <html><body>
            <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
            <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
            <b>Date:</b>&nbsp;{date}<br/>
            <b>Heure:</b>&nbsp;{heure}<br/>
            <b>Durée (h.):</b>&nbsp;{duree}<br/>
            <b>Jours:</b>&nbsp;{jours}<br/>
            <b>Courriel:</b>&nbsp;{courriel}<br/>
            <b>Mode de paiement:</b>&nbsp;{mode_de_paiement}<br/>
            <b>Note:</b>&nbsp;{note}</p>
            </body></html>
        """

        html = html.format(
            desc_ress=desc_ress,
            no_unite=no_unite,
            date=date_rez_raw,
            heure=heure_rez_raw,
            duree=str(duree_rez),
            jours=str(jrs_consecutifs),
            courriel=courriel,
            mode_de_paiement=mode_text,
            note=note
        )

        msg.attach(MIMEText(html, 'html'))

        try:
            server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
            server.ehlo()
            server.login(yahoo_mail_user, yahoo_mail_password)

            for email in email_list:
                server.sendmail(yahoo_mail_user, email, msg.as_string())

            server.quit()

        except:
            print(traceback.format_exc())

    return redirect(url_for('bp_reservations.reservations_table'))
# @bp_reservations.route("/reservation_ajout_admin", methods=['POST'])
# def reservation_ajout_admin():
#     """Ajout d'une réservation à la table de la bd par l'admin. Si la réservation est facturable, un courriel
#     est expédié aux destinataires spécifiés dans les paramètres."""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     # vérifier type d'usager si  admin condofix
#     if profile_list[2] > 2:
#         return redirect(url_for('bp_admin.permission'))
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#     # convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
#     utc_time = datetime.utcnow()
#     tz = pytz.timezone('America/Montreal')
#     utc_time_1 =utc_time.replace(tzinfo=pytz.UTC) #replace method
#     local_time=utc_time_1.astimezone(tz)
#
#     # assembler les deux valeurs date et heure selon le bon format 'datetime'
#     date_rez=request.form['date_rez']
#     time_rez=request.form['heure_rez']
#     rez_time = datetime(int(date_rez[0:4]),int(date_rez[5:7]),int(date_rez[8:10]),int(time_rez[0:2]),int(time_rez[3:5]))
#
#     # savoir si facturable  pour cette ressource...aucune autre contrainte de réservation pour l'administrateur
#     facturable=int()
#     desc_ress=str()
#     cur.execute("SELECT Facturable, Description FROM ressources WHERE IDRessource=%s AND IDClient=%s", (request.form['ress_select'],client_ident))
#     for item in cur.fetchall():
#         facturable=item[0]
#         desc_ress=item[1]
#     email_list=[]
#
#     if request.form['mode_paiement']== '':
#         mode_de_paiement=0
#     else:
#         mode_de_paiement=request.form['mode_paiement']
#
#     # b) pour toute réservation (boucle): aucune vérification de chevauchement
#     compteur_jrs=0
#     while compteur_jrs<float(request.form['jrs_consecutifs']):
#         date_rez_courante=rez_time+timedelta(days=compteur_jrs)
#         heure_rez_courante=request.form['heure_rez']
#         # ajout de la réservation
#         cur.execute('INSERT INTO reservations (DateHeureCreation,IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, '
#                     'Note, Courriel, ModePaiement) '
#                     'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
#                     [local_time, request.form['ress_select'], client_ident, date_rez_courante, heure_rez_courante,
#                      request.form['duree_rez'],request.form['no_unite'],request.form['note'],request.form['courriel'], mode_de_paiement])
#         cnx.commit()
#         compteur_jrs+=1
#
#     #envoi de courriel d'alerte à l'adresse dans les paramètres
#     cur.execute("SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",(client_ident,))
#     for item in cur.fetchall():
#         email_a=item[0]
#         email_list=email_a.split(',')
#     mode_text=str()
#     cur.execute("SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s", (mode_de_paiement,client_ident))
#     for item in cur.fetchall():
#         mode_text = item[0]
#     cnx.close()
#     if facturable==1:
#         yahoo_mail_user = 'condofix.ca@yahoo.com'
#         yahoo_mail_password = 'spyvlumgfwscqfkc'
#
#         no_unite=request.form['no_unite']
#         date=request.form['date_rez']
#         heure=request.form['heure_rez']
#         duree=request.form['duree_rez']
#         jours=request.form['jrs_consecutifs']
#         courriel=request.form['courriel']
#         note=request.form['note']
#         mode_de_paiement=mode_text
#
#         msg = MIMEMultipart("related")
#         msg['Subject'] = "Réservation facturable"
#         msg['From'] = yahoo_mail_user
#         html = """
#             <html><body>
#             <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
#             <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
#             <b>Date:</b>&nbsp;{date}<br/>
#             <b>Heure:</b>&nbsp;{heure}<br/>
#             <b>Durée (h.):</b>&nbsp;{duree}<br/>
#             <b>Jours:</b>&nbsp;{jours}<br/>
#             <b>Courriel:</b>&nbsp;{courriel}<br/>
#             <b>Mode de paiement:</b>&nbsp;{mode_de_paiement}<br/>
#             <b>Note:</b>&nbsp;{note}</p>
#             </body></html>
#             """
#
#         html = html.format(desc_ress=desc_ress,no_unite=no_unite,date=date,heure=heure,duree=duree,jours=jours,courriel=courriel,
#                            mode_de_paiement=mode_de_paiement,note=note)
#
#         # enregistrer le MIME pour l'HTML
#         contenu = MIMEText(html, 'html')
#         # attacher le contenu au 'container' du message
#         msg.attach(contenu)
#         try:
#             server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
#             server.ehlo()
#             server.login(yahoo_mail_user, yahoo_mail_password)
#             # sendmail function takes 3 arguments: sender's address, recipient's address
#             # and message to send - here it is sent as one string.
#             for i in range(len(email_list)):
#                 server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
#             server.quit()
#
#         except:
#             print(traceback.format_exc())
#
#     return redirect(url_for('bp_reservations.reservations_table'))

#fonctions pour ajouter une réservations
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

    if facturable == 1 and email_list:
        yahoo_mail_user = 'condofix.ca@yahoo.com'
        yahoo_mail_password = 'spyvlumgfwscqfkc'

        if not yahoo_mail_password:
            print("YAHOO_MAIL_PASSWORD is missing; reservation email was not sent.")
        else:
            msg = MIMEMultipart("related")
            msg['Subject'] = "Réservation facturable"
            msg['From'] = yahoo_mail_user

            html = """
                <html><body>
                <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
                <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
                <b>Date:</b>&nbsp;{date}<br/>
                <b>Heure:</b>&nbsp;{heure}<br/>
                <b>Durée (h.):</b>&nbsp;{duree}<br/>
                <b>Jours:</b>&nbsp;{jours}<br/>
                <b>Courriel:</b>&nbsp;{courriel}<br/>
                <b>Mode de paiement:</b>&nbsp;{mode_de_paiement}<br/>
                <b>Note:</b>&nbsp;{note}</p>
                </body></html>
            """

            html = html.format(
                desc_ress=desc_ress,
                no_unite=no_unite,
                date=date_rez_raw,
                heure=heure_rez_raw,
                duree=str(duree_rez),
                jours=str(jrs_consecutifs),
                courriel=courriel,
                mode_de_paiement=mode_text,
                note=note
            )

            msg.attach(MIMEText(html, 'html'))

            try:
                server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
                server.ehlo()
                server.login(yahoo_mail_user, yahoo_mail_password)

                for email in email_list:
                    server.sendmail(yahoo_mail_user, email, msg.as_string())

                server.quit()

            except:
                print(traceback.format_exc())

    flash("La réservation a été enregistrée.", "success")
    return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))
# fonctions pour ajouter une réservation
# @bp_reservations.route("/reservation_ajout_proprio", methods=['POST'])
# def reservation_ajout_proprio():
#     """Ajout d'une réservation à la table de la bd par les copropriétaires. Si la réservation est facturable, un courriel
#      est expédié aux destinataires spécifiés dans les paramètres. Les réglages effectués par l'admin
#      dans la table des ressources appliquent des restrictions sur l'acceptation d'une réservation et
#      un message d'avertissement est affiché (flash message) dans la page reservation_ajout_proprio_mess expliquant la limitation."""
#
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#
#     profile_list = session.get('ProfilUsager')
#     client_ident = profile_list[0]
#     mode = profile_list[8]
#
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#
#     # assembler les deux valeurs date et heure selon le bon format 'datetime'
#     date_rez = request.form['date_rez']
#     time_rez = request.form['heure_rez']
#     rez_time = datetime(
#         int(date_rez[0:4]),
#         int(date_rez[5:7]),
#         int(date_rez[8:10]),
#         int(time_rez[0:2]),
#         int(time_rez[3:5])
#     )
#
#     # convertir du type timezone naive à timezone aware pour calcul du delta
#     rez_time_modif = rez_time.astimezone()
#
#     # pour respecter l'heure locale: le serveur PythonAnywhere est à Londres (heure utc)
#
#     # convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
#     utc_time = datetime.utcnow()
#     # tz = pytz.timezone('America/Montreal')
#     tz = pytz.timezone('Europe/London')
#     utc_time_1 = utc_time.replace(tzinfo=pytz.UTC)  # replace method
#     # local_time = utc_time_1.astimezone(tz)
#     # local_time = utc_time.astimezone(tz)
#     utcnow = timezone('utc').localize(datetime.utcnow())  # generic time
#     local_time = utcnow.astimezone(timezone('America/Montreal'))
#
#     utcnow = timezone('utc').localize(datetime.utcnow())  # generic time
#     here = utcnow.astimezone(timezone('America/Montreal')).replace(tzinfo=None)
#     there = utcnow.astimezone(timezone('utc')).replace(tzinfo=None)
#     offset = relativedelta(there, here)
#     time_diff_serv_pa = offset.hours
#     # print(offset, time_diff_serv_pa)
#
#     delta = rez_time_modif - local_time
#     # délai de rez en heures avec 1 décimale
#     delai_rez_hres = round(delta.total_seconds() / 3600, 3) + round(time_diff_serv_pa, 3)
#
#     # print('time diff pa:', time_diff_serv_pa)
#     # print('délai rez hres:', delai_rez_hres)
#
#     # définition des variables pour qu'elles ne soient pas hors contexte
#     desc_ress = str()
#     facturable = 0
#     duree_max = 0
#     delai_min_h = 0
#     delai_max_j = 0
#     date_debut_non_dispo = str()
#     duree_non_dispo = 0
#     jrs_consecutifs_permis = 0
#     interv_rez_hres = 0
#     hre_debut_permise = str()
#     hre_fin_permise = str()
#
#     # obtenir tous les paramètres pour cette ressource
#     cur.execute(
#         "SELECT Description, Facturable, DureeMaxHres, DelaiMinHres, DelaiMaxJrs, "
#         "DateDebutNonDispo, DureeNonDispoHres, JoursConsecutifsPermis, IntervalleRezHres, "
#         "HreDebutPermise, HreFinPermise "
#         "FROM ressources "
#         "WHERE IDRessource=%s AND IDClient=%s",
#         (request.form['ident_ress'], client_ident)
#     )
#     for item in cur.fetchall():
#         desc_ress = item[0]
#         facturable = item[1]
#         duree_max = float(item[2])
#         delai_min_h = float(item[3])
#         delai_max_j = float(item[4])
#         date_debut_non_dispo = str(item[5])
#         duree_non_dispo = item[6]
#         jrs_consecutifs_permis = float(item[7])
#         interv_rez_hres = item[8]
#         hre_debut_permise = item[9]
#         hre_fin_permise = item[10]
#
#     # pour afficher les messages d'avertissement où l'usager a dépassé un paramètre
#     # on affiche une page spéciale identique à 'nouvelle réservation' en utilisant le contenu des champs actuels dans une liste
#     liste_rez = [
#         request.form['ident_ress'],
#         desc_ress,
#         request.form['date_rez'],
#         request.form['heure_rez'],
#         request.form['duree_rez'],
#         request.form['jrs_consecutifs'],
#         request.form['no_unite'],
#         request.form['courriel'],
#         request.form['mode_paiement'],
#         request.form['note']
#     ]
#
#     avertissement = False  # permet d'envoyer l'usager à la page d'avertissement
#     message = str()        # on accumule le texte des messages pour l'utiliser à la fin du processus de vérif
#
#     fill_modes_paiement = []
#     # modes de paiement à retenir pour page ayant messages d'avertissement
#     cur.execute(
#         "SELECT IDPaiement, Description FROM modepaiement WHERE IDClient=%s",
#         (client_ident,)
#     )
#     for item in cur.fetchall():
#         fill_modes_paiement.append(item)
#
#     # pour s'assurer que l'usager saisisse son courriel et le mode de paiement (rez facturable)
#     if facturable == 1:
#         if request.form['courriel'] == '':
#             avertissement = True
#             message = Markup(
#                 "<b>Vous devez saisir votre courriel pour réserver une ressource facturable.</b><br>"
#             )
#
#         if request.form['mode_paiement'] == '':
#             avertissement = True
#             message = message + Markup(
#                 "<b>Vous devez saisir un mode de paiement pour réserver une ressource facturable.</b><br>"
#             )
#
#     # validation de base sur la durée et les jours consécutifs
#     try:
#         rez_duree = float(request.form['duree_rez'])
#         jrs_consecutifs = float(request.form['jrs_consecutifs'])
#     except (TypeError, ValueError):
#         avertissement = True
#         message = message + Markup(
#             "<b>La durée et le nombre de jours consécutifs doivent être des nombres valides.</b><br>"
#         )
#         flash(
#             message + Markup("Veuillez modifier les champs visés afin de compléter cette réservation."),
#             'warning'
#         )
#         return render_template(
#             'reservation_ajout_proprio_mess.html',
#             fill_rez=liste_rez,
#             fill_modes=fill_modes_paiement
#         )
#
#     if rez_duree <= 0:
#         avertissement = True
#         message = message + Markup(
#             "<b>La durée doit être supérieure à 0.</b><br>"
#         )
#
#     if jrs_consecutifs <= 0:
#         avertissement = True
#         message = message + Markup(
#             "<b>Le nombre de jours consécutifs doit être supérieur à 0.</b><br>"
#         )
#
#     # séquence de vérification pour accepter la réservation (rejet de la demande aussitôt qu'un critère n'est pas conforme):
#     # a) peu importe le nombre de jours consécutifs demandés:
#     # - voir si le nombre de jours consécutifs demandé dépasse le maximum permis
#     # - vérifier si durée demandée est au-delà du maximum
#     # - vérifier si le délai minimal est respecté (date de la première rez de la série consécutive)
#     # - vérifier si le délai maximal est respecté (date de la dernière rez de la série consécutive)
#     # - vérifier si l'heure demandée tombe entre l'heure début et de fin permise
#     # - vérifier si la ressource est temporairement indisponible (date début + durée non dispo)
#     #
#     # b) pour toute réservation :
#     # - vérifier si l'intervalle entre les rez est respecté selon l'heure demandée
#     # - voir s'il y a chevauchement avec une réservation actuelle
#
#     # a) peu importe le nombre de jours consécutifs demandés:
#     # 1- voir si le nombre de jours consécutifs demandé dépasse le maximum permis
#     if jrs_consecutifs > jrs_consecutifs_permis:
#         avertissement = True
#         message = message + Markup(
#             "<b>Le nombre de jours consécutifs demandés excède celui fixé par le syndicat pour cette ressource soit de "
#             + str(jrs_consecutifs_permis) + " jours.</b><br>"
#         )
#
#     # 2- vérifier si durée demandée est au-delà du maximum
#     if rez_duree > duree_max:
#         avertissement = True
#         message = message + Markup(
#             "<b>La durée demandée excède celle fixée par le syndicat pour cette ressource soit de "
#             + str(duree_max) + " heures.</b><br>"
#         )
#
#     # 3- vérifier si délai minimal en heures est respecté
#     if delai_rez_hres < delai_min_h:
#         avertissement = True
#         message = message + Markup(
#             "<b>La réservation demandée n'est pas conforme au délai minimal fixé par le syndicat pour cette ressource soit de "
#             + str(float(delai_min_h)) + " heures.</b><br>"
#         )
#
#     # 4- vérifier si délai maximal en jours est respecté
#     delai_rez_avec_jrs_consec = delai_rez_hres / 24 + jrs_consecutifs - 1
#     if delai_rez_avec_jrs_consec > delai_max_j:
#         avertissement = True
#         message = message + Markup(
#             "<b>Le délai maximal pour la demande de réservation est plus long que celui fixé par le syndicat pour cette ressource soit de "
#             + str(float(delai_max_j)) + " jours.</b><br>"
#         )
#
#     # 5- vérifier si l'heure demandée tombe entre l'heure début et de fin permise
#     # convertir heure de rez en datetime.datetime
#
#     # print('heure brut:', request.form['heure_rez'])
#     heure_brut = str(request.form['heure_rez'])
#     heure_net = heure_brut[0:5]
#     # print('heure net:', heure_net)
#     hre_rez_datetime = datetime.strptime(heure_net, '%H:%M')
#
#     # vérifier si critère exigé pour cette ressource:
#     if hre_debut_permise is not None:
#         if hre_debut_permise != timedelta(seconds=0):  # ='0:00:00' si remis à zéro par usager
#             hre_debut_modif = hre_debut_permise
#             # convertir heures permises de datetime.timedelta en str puis en datetime.datetime
#             hre_debut_str = str(hre_debut_modif)
#             hre_debut_datetime = datetime.strptime(hre_debut_str, '%H:%M:%S')
#             if hre_rez_datetime < hre_debut_datetime:
#                 avertissement = True
#                 message = message + Markup(
#                     "<b>L'heure de début demandée est plus tôt que celle fixée par le syndicat pour cette ressource soit "
#                     + str(hre_debut_permise) + ".</b><br>"
#                 )
#
#     if hre_fin_permise is not None:
#         if hre_fin_permise != timedelta(seconds=0):
#             # enlever la durée de la rez de l'heure de fin permise
#             min_duree = rez_duree * 60
#             duree = timedelta(minutes=min_duree)
#             hre_fin_modif = hre_fin_permise - duree
#
#             # si la durée demandée ne rentre pas dans la fenêtre permise,
#             # on affiche un avertissement au lieu de planter
#             if hre_fin_modif.total_seconds() <= 0:
#                 avertissement = True
#                 message = message + Markup(
#                     "<b>La combinaison de l'heure de début et de la durée demandée dépasse l'heure de fin permise pour cette ressource soit "
#                     + str(hre_fin_permise) + ".</b><br>"
#                 )
#             else:
#                 # convertir le timedelta positif en heure comparable à hre_rez_datetime
#                 total_seconds = int(hre_fin_modif.total_seconds())
#                 heures = total_seconds // 3600
#                 minutes = (total_seconds % 3600) // 60
#                 secondes = total_seconds % 60
#
#                 # même base de date implicite que hre_rez_datetime (1900-01-01)
#                 hre_fin_datetime = datetime(1900, 1, 1, heures, minutes, secondes)
#
#                 if hre_rez_datetime > hre_fin_datetime:
#                     avertissement = True
#                     message = message + Markup(
#                         "<b>L'heure de fin demandée (heure plus durée) tombe plus tard que celle fixée par le syndicat pour cette ressource soit "
#                         + str(hre_fin_permise) + ".</b><br>"
#                     )
#
#     # 6- vérifier si la ressource est temporairement indisponible (date début + durée non dispo)
#     # vérifier si ces critères sont exigés pour cette ressource:
#     if date_debut_non_dispo != '':
#         if duree_non_dispo is not None or duree_non_dispo != '':
#             # heure de réservation selon les jours consécutifs débutant à 0
#             # secondes depuis 1970-01-01
#             # période de réservation demandée
#             # on ajoute et on retranche des secondes à la réservation pour éviter que les limites des heures se touchent
#             secondes_rez_debut = rez_time.timestamp() + 1
#             # on ajoute la durée et les jours consécutifs (ajout de 0 jrs si jrs consécutifs=1)
#             secondes_rez_fin = (
#                 secondes_rez_debut
#                 + float(rez_duree * 3600)
#                 + ((jrs_consecutifs - 1) * 24 * 3600)
#                 - 2
#             )
#
#             print('Date non dispo:', date_debut_non_dispo)
#             datetime_non_dispo = datetime(
#                 int(date_debut_non_dispo[0:4]),
#                 int(date_debut_non_dispo[5:7]),
#                 int(date_debut_non_dispo[8:10])
#             )
#
#             secondes_nondispo_debut = datetime_non_dispo.timestamp()
#             secondes_nondispo_fin = secondes_nondispo_debut + float(duree_non_dispo * 3600)
#
#             # voir s'il y a chevauchement
#             if secondes_rez_debut <= secondes_nondispo_debut <= secondes_rez_fin:
#                 avertissement = True
#                 message = message + Markup(
#                     "<b>Cette ressource n'est pas disponible à partir du "
#                     + str(date_debut_non_dispo)
#                     + " pour "
#                     + str(duree_non_dispo)
#                     + " heures..</b><br>"
#                 )
#
#             elif secondes_nondispo_debut <= secondes_rez_debut <= secondes_nondispo_fin:
#                 avertissement = True
#                 message = message + Markup(
#                     "<b>Cette ressource n'est pas disponible à partir du "
#                     + str(date_debut_non_dispo)
#                     + " pour "
#                     + str(duree_non_dispo)
#                     + " heures.</b><br>"
#                 )
#
#     # si le système a trouvé un conflit avec les paramètres, on affiche le ou les messages cumulés:
#     if avertissement is True:
#         message = message + Markup("Veuillez modifier les champs visés afin de compléter cette réservation.")
#         flash(message, 'warning')
#         return render_template(
#             'reservation_ajout_proprio_mess.html',
#             fill_rez=liste_rez,
#             fill_modes=fill_modes_paiement
#         )
#     else:
#         print(avertissement)
#
#     # 7- vérification du chevauchement avec réservations existantes:
#     # on sauvegarde les réservations à venir dans une liste
#     # requête des enregistrements de réservation pour cette ressource avec date >= date demandée
#     liste_enreg = []
#     cur.execute(
#         "SELECT IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite "
#         "FROM reservations "
#         "WHERE IDRessource=%s AND Date>=%s AND IDClient=%s",
#         (request.form['ident_ress'], datetime.now(), client_ident)
#     )
#     for row in cur.fetchall():
#         liste_enreg.append(row)
#
#     # début de la boucle
#     compteur_jrs = 0
#     while compteur_jrs < jrs_consecutifs:
#         # heure de réservation selon les jours consécutifs débutant à 0
#         dr = rez_time + timedelta(days=compteur_jrs)
#
#         # 7- pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
#         # on retranche/ajoute l'intervalle exigé entre chaque réservation
#         # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
#         secondes_rez_debut = dr.timestamp() - (float(interv_rez_hres) * 3600) + 1
#         secondes_rez_fin = dr.timestamp() + float(rez_duree * 3600) + (float(interv_rez_hres) * 3600) - 2
#
#         # 8- voir s'il y a chevauchement avec une réservation actuelle
#         for item in liste_enreg:
#             date_1 = item[2]
#             time_delta = item[3]
#             date_str = str(date_1)
#             time_str = str(time_delta)
#
#             # régler problème avec heures ayant seulement 1 caractère (ex. 9:00 vs. 13:00)
#             if time_str.index(':') == 1:
#                 time_1 = time_str[0]
#                 time_2 = time_str[2:4]
#             else:
#                 time_1 = time_str[0:2]
#                 time_2 = time_str[3:5]
#
#             enreg_time = datetime(
#                 int(date_str[0:4]),
#                 int(date_str[5:7]),
#                 int(date_str[8:10]),
#                 int(time_1),
#                 int(time_2)
#             )
#
#             de = enreg_time
#             secondes_debut_enreg = float(de.timestamp())
#             plage = float(item[4] * 3600)
#             secondes_fin_enreg = float(secondes_debut_enreg) + plage
#
#             if secondes_rez_debut <= secondes_debut_enreg <= secondes_rez_fin:
#                 if interv_rez_hres == 0:
#                     avertissement = True
#                     message = message + Markup(
#                         "<b>Cette ressource est déjà réservée par l'unité "
#                         + str(item[5]) + ".</b><br>"
#                     )
#                 else:
#                     avertissement = True
#                     message = message + Markup(
#                         "<b>Cette réservation entre en conflit avec une autre réservation adjacente. Veuillez tenir compte de "
#                         + "l'intervalle de " + str(interv_rez_hres)
#                         + " heures exigé par le syndicat entre chaque réservation.</b><br>"
#                     )
#
#             elif secondes_debut_enreg <= secondes_rez_debut <= secondes_fin_enreg:
#                 if interv_rez_hres == 0:
#                     avertissement = True
#                     message = message + Markup(
#                         "<b>Cette ressource est déjà réservée par l'unité "
#                         + str(item[5]) + ".</b><br>"
#                     )
#                 else:
#                     avertissement = True
#                     message = message + Markup(
#                         "<b>Cette réservation entre en conflit avec une autre réservation adjacente. Veuillez tenir compte de "
#                         + "l'intervalle de " + str(interv_rez_hres)
#                         + " heures exigé par le syndicat entre chaque réservation.</b><br>"
#                     )
#
#             if avertissement is True:
#                 message = message + Markup(
#                     "Veuillez modifier les champs visés afin de compléter cette réservation."
#                 )
#                 flash(message, 'warning')
#                 return render_template(
#                     'reservation_ajout_proprio_mess.html',
#                     fill_rez=liste_rez,
#                     fill_modes=fill_modes_paiement
#                 )
#
#         compteur_jrs += 1
#
#     if avertissement is False:
#         compteur_jrs = 0
#         while compteur_jrs < jrs_consecutifs:
#             date_rez_courante = rez_time + timedelta(days=compteur_jrs)
#             heure_rez_courante = request.form['heure_rez']
#
#             # mode de paiement doit être un numérique
#             if request.form['mode_paiement'] == '':  # champ vide
#                 mode_paiement = 0
#             else:
#                 mode_paiement = request.form['mode_paiement']
#
#             # ajout de la réservation
#             cur.execute(
#                 'INSERT INTO reservations '
#                 '(DateHeureCreation, IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, Note, Courriel, ModePaiement) '
#                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
#                 [
#                     local_time,
#                     request.form['ident_ress'],
#                     client_ident,
#                     date_rez_courante,
#                     heure_rez_courante,
#                     request.form['duree_rez'],
#                     request.form['no_unite'],
#                     request.form['note'],
#                     request.form['courriel'],
#                     mode_paiement
#                 ]
#             )
#             cnx.commit()
#             compteur_jrs += 1
#
#     # envoi de courriel d'alerte à l'adresse dans les paramètres si rez facturable
#     email_list = []
#     cur.execute(
#         "SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",
#         (client_ident,)
#     )
#     for item in cur.fetchall():
#         email_a = item[0]
#         email_list = email_a.split(',')
#
#     if facturable == 1:
#         yahoo_mail_user = 'condofix.ca@yahoo.com'
#         yahoo_mail_password = 'spyvlumgfwscqfkc'
#
#         no_unite = request.form['no_unite']
#         date = request.form['date_rez']
#         heure = request.form['heure_rez']
#         duree = request.form['duree_rez']
#         jours = request.form['jrs_consecutifs']
#         courriel = request.form['courriel']
#         note = request.form['note']
#         mode = request.form['mode_paiement']
#
#         cur.execute(
#             "SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s",
#             (mode, client_ident)
#         )
#         for item in cur.fetchall():
#             mode_de_paiement = item[0]
#
#         msg = MIMEMultipart("related")
#         msg['Subject'] = "Réservation facturable"
#         msg['From'] = yahoo_mail_user
#         html = """
#             <html><body>
#             <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
#             <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
#             <b>Date:</b>&nbsp;{date}<br/>
#             <b>Heure:</b>&nbsp;{heure}<br/>
#             <b>Durée (h.):</b>&nbsp;{duree}<br/>
#             <b>Jours:</b>&nbsp;{jours}<br/>
#             <b>Courriel:</b>&nbsp;{courriel}<br/>
#             <b>Mode de paiement:</b>&nbsp;{mode_de_paiement}<br/>
#             <b>Note:</b>&nbsp;{note}</p>
#             </body></html>
#         """
#
#         html = html.format(
#             desc_ress=desc_ress,
#             no_unite=no_unite,
#             date=date,
#             heure=heure,
#             duree=duree,
#             jours=jours,
#             courriel=courriel,
#             mode_de_paiement=mode_de_paiement,
#             note=note
#         )
#
#         # enregistrer le MIME pour l'HTML
#         contenu = MIMEText(html, 'html')
#         # attacher le contenu au 'container' du message
#         msg.attach(contenu)
#
#         try:
#             server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
#             server.ehlo()
#             server.login(yahoo_mail_user, yahoo_mail_password)
#             # sendmail function takes 3 arguments: sender's address, recipient's address
#             # and message to send - here it is sent as one string.
#             for i in range(len(email_list)):
#                 server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
#             server.quit()
#         except:
#             print(traceback.format_exc())
#
#         cnx.close()
#         return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))
#     else:
#         # pas facturable
#         cnx.close()
#         return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))


# @bp_reservations.route("/reservation_ajout_proprio", methods=['POST'])
# def reservation_ajout_proprio():
#     """Ajout d'une réservation à la table de la bd par les copropriétaires. Si la réservation est facturable, un courriel
#      est expédié aux destinataires spécifiés dans les paramètres. Les réglages effectués par l'admin
#      dans la table des ressources appliquent des restrictions sur l'acceptation d'une réservation et
#      un message d'avertissement est affiché (flash message) dans la page reservation_ajout_proprio_mess expliquant la limitation."""
#
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#
#     # assembler les deux valeurs date et heure selon le bon format 'datetime'
#     date_rez=request.form['date_rez']
#     time_rez=request.form['heure_rez']
#     rez_time = datetime(int(date_rez[0:4]),int(date_rez[5:7]),int(date_rez[8:10]),int(time_rez[0:2]),int(time_rez[3:5]))
#     #convertir du type timezone naive à timezone aware pour calcul du delta
#     rez_time_modif=rez_time.astimezone()
#
#     # pour respecter l'heure locale: le serveur PythonAnywhere est a  Londres (heure utc)
#
#     # convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
#     utc_time = datetime.utcnow()
#     #tz = pytz.timezone('America/Montreal')
#     tz = pytz.timezone('Europe/London')
#     utc_time_1 =utc_time.replace(tzinfo=pytz.UTC) #replace method
#     #local_time=utc_time_1.astimezone(tz)
#     #local_time=utc_time.astimezone(tz)
#     utcnow = timezone('utc').localize(datetime.utcnow()) # generic time
#     local_time = utcnow.astimezone(timezone('America/Montreal'))
#
#
#
#
#     utcnow = timezone('utc').localize(datetime.utcnow()) # generic time
#     here = utcnow.astimezone(timezone('America/Montreal')).replace(tzinfo=None)
#     there = utcnow.astimezone(timezone('utc')).replace(tzinfo=None)
#     offset = relativedelta(there, here)
#     time_diff_serv_pa=offset.hours
#     #print(offset, time_diff)
#
#
#
#     delta = rez_time_modif-local_time
#     # délai de rez en heures avec 1 décimale
#     delai_rez_hres=round(delta.total_seconds()/3600,3)+ round(time_diff_serv_pa,3)
#
#     # print('time diff pa:',time_diff_serv_pa)
#     # print('délai rez hres:',delai_rez_hres)
#
#
#     # définition des variables pour qu'elles ne soient pas hors contexte
#     desc_ress=str()
#     facturable=0
#     duree_max=0
#     delai_min_h=0
#     delai_max_j=0
#     date_debut_non_dispo=str()
#     duree_non_dispo=0
#     jrs_consecutifs_permis=0
#     interv_rez_hres=0
#     hre_debut_permise=str()
#     hre_fin_permise=str()
#     # obtenir tous les paramètres pour cette ressource
#     cur.execute("SELECT Description, Facturable, DureeMaxHres, DelaiMinHres, DelaiMaxJrs, DateDebutNonDispo, DureeNonDispoHres,"
#                 "JoursConsecutifsPermis, IntervalleRezHres, HreDebutPermise, HreFinPermise FROM ressources WHERE IDRessource=%s AND IDClient=%s", (request.form['ident_ress'],client_ident))
#     for item in cur.fetchall():
#         desc_ress=item[0]
#         facturable=item[1]
#         duree_max=float(item[2])
#         delai_min_h=float(item[3])
#         delai_max_j=float(item[4])
#         date_debut_non_dispo=str(item[5])
#         duree_non_dispo=item[6]
#         jrs_consecutifs_permis=float(item[7])
#         interv_rez_hres=item[8]
#         hre_debut_permise=item[9]
#         hre_fin_permise=item[10]
#
#     # pour afficher les messages d'avertissement où l'usager a dépassé un paramètre
#     # on affiche une page spéciale identique à 'nouvelle réservation' en utilisant le contenu des champs actuels dans une liste
#     liste_rez=[request.form['ident_ress'], desc_ress, request.form['date_rez'],request.form['heure_rez'],request.form['duree_rez'],
#                request.form['jrs_consecutifs'],request.form['no_unite'],request.form['courriel'],
#                request.form['mode_paiement'],request.form['note']]
#     avertissement=False # permet d'envoyer l'usager à la page d'avertissement
#     message=str() # on accumule le texte des messages pour l'utiliser à la fin du processus de vérif
#     fill_modes_paiement=[]
#     # modes de paiement à retenir pour page ayant messages d'avertissement
#     cur.execute("SELECT IDPaiement,Description from modepaiement WHERE IDClient=%s",(client_ident,))
#     for item in cur.fetchall():
#         fill_modes_paiement.append(item)
#
#     # pour s'assurer que l'usager saisisse son courriel et le mode de paiement (rez facturable)
#     if facturable==1:
#         if request.form['courriel']=='':
#             avertissement=True
#             message=Markup("<b>Vous devez saisir votre courriel pour réserver une ressource facturable.</b><br>") \
#
#         if request.form['mode_paiement']=='':
#             avertissement=True
#             message=message+Markup("<b>Vous devez saisir un mode de paiement pour réserver une ressource facturable.</b><br>") \
#
#     # séquence de vérification pour accepter la réservation (rejet de la demande aussitôt qu'un critère n'est pas conforme):
#     # a) peu importe le nombre de jours consécutifs demandés:
#     # - voir si le nombre de jours consécutifs demandé dépasse le maximum permis
#     # - vérifier si durée demandée est au-delà du maximum
#     # - vérifier si le délai minimal est respecté (date de la première rez de la série consécutive)
#     # - vérifier si le délai maximal est respecté (date de la dernière rez de la série consécutive)
#     # - vérifier si l'heure demandée tombe entre l'heure début et de fin permise
#     # - vérifier si la ressource est temporairement indisponible (date début + durée non dispo)
#
#     # b) pour toute réservation :
#     # - vérifier si l'intervalle entre les rez est respecté selon l'heure demandée
#     # - voir s'il y a chevauchement avec une réservation actuelle
#
#     # a) peu importe le nombre de jours consécutifs demandés:
#     # 1- voir si le nombre de jours consécutifs demandé dépasse le maximum permis
#     if float(request.form['jrs_consecutifs'])>jrs_consecutifs_permis:
#         avertissement=True
#         message=message+Markup("<b>Le nombre de jours consécutifs demandés excède celui fixé par le syndicat pour cette ressource soit de "+str(jrs_consecutifs_permis)+" jours.</b><br>") \
#
#     # 2- vérifier si durée demandée est au-delà du maximum
#     rez_duree=float(request.form['duree_rez'])
#     if rez_duree>duree_max:
#         avertissement=True
#         message=message+Markup("<b>La durée demandée excède celle fixée par le syndicat pour cette ressource soit de "+str(duree_max)+" heures.</b><br>") \
#
#     # 3- vérifier si délai minimal en heures est respecté
#     if delai_rez_hres<delai_min_h:
#         avertissement=True
#         message=message+Markup("<b>La réservation demandée n'est pas conforme au délai minimal fixé par le syndicat pour cette ressource soit de "+str(float(delai_min_h))+" heures.</b><br>") \
#
#     # 4- vérifier si délai maximal en jours est respecté
#     delai_rez_avec_jrs_consec=delai_rez_hres/24+float(request.form['jrs_consecutifs'])-1
#     if delai_rez_avec_jrs_consec>delai_max_j:
#         avertissement=True
#         message=message+Markup("<b>Le délai maximal pour la demande de réservation est plus long que celui fixé par le syndicat pour cette ressource soit de "+str(float(delai_max_j))+" jours.</b><br>") \
#
#     # 5- vérifier si l'heure demandée tombe entre l'heure début et de fin permise
#     # convertir heure de rez en datetime.datetime
#
#     #print('heure brut:',request.form['heure_rez'])
#     heure_brut=str(request.form['heure_rez'])
#     heure_net=heure_brut[0:5]
#     #print('heure net:',heure_net)
#     hre_rez_datetime=datetime.strptime(heure_net, '%H:%M' )
#     # vérifier si critère exigé pour cette ressource:
#     if hre_debut_permise is not None:
#         if hre_debut_permise!= timedelta(seconds=0):#='0:00:00' si remis à zéro par usager
#             hre_debut_modif=hre_debut_permise
#             # convertir heures permises de datetime.timedelta en str puis en datetime.datetime
#             hre_debut_str=str(hre_debut_modif)
#             hre_debut_datetime=datetime.strptime(hre_debut_str, '%H:%M:%S')
#             if hre_rez_datetime<hre_debut_datetime:
#                 avertissement=True
#                 message=message+Markup("<b>L'heure de début demandée est plus tôt que celle fixée par le syndicat pour cette ressource soit "+str(hre_debut_permise)+".</b><br>") \
#
#     if hre_fin_permise!=None:
#         if hre_fin_permise!=timedelta(seconds=0):
#             # enlever la durée de la rez de la date de début permise
#             min_duree=rez_duree*60
#             duree=timedelta(minutes = min_duree)
#             hre_fin_modif=hre_fin_permise-duree
#             # convertir heures permises moins durée de datetime.timedelta en str puis en datetime.datetime
#             hre_fin_str=str(hre_fin_modif)
#             hre_fin_datetime=datetime.strptime(hre_fin_str, '%H:%M:%S')
#             if hre_rez_datetime>hre_fin_datetime:
#                 avertissement=True
#                 message=message+Markup("<b>L'heure de fin demandée (heure plus durée) tombe plus tard que celle fixée par le syndicat pour cette ressource soit "+str(hre_fin_permise)+".</b><br>") \
#
#     # 6- vérifier si la ressource est temporairement indisponible (date début + durée non dispo)
#     # vérifier si ces critères sont exigés pour cette ressource:
#     if date_debut_non_dispo!='':
#         if duree_non_dispo!=None or duree_non_dispo!='':
#             # heure de réservation selon les jours consécutifs débutant à 0
#             # secondes depuis 1970-01-01
#             # période de réservation demandée
#             # on ajoute et on retranche des secondes à la réservation pour éviter que les limites des heures se touchent
#             secondes_rez_debut=rez_time.timestamp()+1
#             # on ajoute la durée et les jours consécutifs (ajout de 0 jrs si jrs consécutifs=1)
#             secondes_rez_fin=secondes_rez_debut+float(rez_duree*3600)+((float(request.form['jrs_consecutifs'])-1)*24*3600)-2
#
#
#             print('Date non dispo:',date_debut_non_dispo)
#             datetime_non_dispo=datetime(int(date_debut_non_dispo[0:4]),int(date_debut_non_dispo[5:7]),int(date_debut_non_dispo[8:10]))#,int(time_rez[0:2]),int(time_rez[3:5]))
#
#             secondes_nondispo_debut=datetime_non_dispo.timestamp()
#             secondes_nondispo_fin=secondes_nondispo_debut+float(duree_non_dispo*3600)
#
#             # voir s'il y a chevauchement
#             if secondes_rez_debut<=secondes_nondispo_debut<=secondes_rez_fin:
#                 avertissement=True
#                 message=message+Markup("<b>Cette ressource n'est pas disponible à partir du "+str(date_debut_non_dispo)+" pour "+str(duree_non_dispo)+" heures..</b><br>") \
#
#             elif secondes_nondispo_debut<=secondes_rez_debut<=secondes_nondispo_fin:
#                 avertissement=True
#                 message=message+Markup("<b>Cette ressource n'est pas disponible à partir du "+str(date_debut_non_dispo)+" pour "+str(duree_non_dispo)+" heures.</b><br>") \
#
#
#     # si le système a trouvé un conflit avec les paramètres, on affiche le ou les messages cumulés:
#     if avertissement==True:
#         message=message+Markup("Veuillez modifier les champs visés afin de compléter cette réservation.")
#         flash(message,'warning')
#         return render_template('reservation_ajout_proprio_mess.html',fill_rez=liste_rez,fill_modes=fill_modes_paiement)
#     else:
#         print(avertissement)
#
#     # 7- vérification du chevauchement avec réservations existante:
#     # on sauvegarde les réservations à venir dans une liste
#     # requête des enregistrements de réservation pour cette ressource avec date >= date demandée
#     liste_enreg=[]
#     cur.execute("SELECT IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite FROM reservations WHERE IDRessource=%s AND Date>=%s AND IDClient=%s",
#                     (request.form['ident_ress'], datetime.now(), client_ident))
#     for row in cur.fetchall():
#         liste_enreg.append(row)
#     #print(liste_enreg)
#     # début de la boucle
#     compteur_jrs=0
#     while compteur_jrs<float(request.form['jrs_consecutifs']):
#         # heure de réservation selon les jours consécutifs débutant à 0
#         dr = rez_time+timedelta(days=compteur_jrs)
#         # secondes depuis 1970-01-01
#         #print('counter:',compteur_jrs)
#
#         # 7- pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
#         # on retranche/ajoute l'intervalle exigé entre chaque réservation
#         # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
#         secondes_rez_debut = dr.timestamp()-(float(interv_rez_hres)*3600)+1
#         secondes_rez_fin=dr.timestamp()+float(rez_duree*3600)+(float(interv_rez_hres)*3600)-2
#
#         # 8- voir s'il y a chevauchement avec une réservation actuelle
#
#         for item in liste_enreg:
#             date_1=item[2]
#             time_delta=item[3]
#             date=str(date_1)
#             time=str(time_delta)
#             # régler problème avec heures ayant seulement 1 caractère (ex. 9:00 vs. 13:00)
#             if time.index(':')==1:
#                 time_1=time[0]
#                 time_2=time[2:4]
#             else:
#                 time_1=time[0:2]
#                 time_2=time[3:5]
#
#             enreg_time = datetime(int(date[0:4]),int(date[5:7]), int(date[8:10]),int(time_1),int(time_2))
#
#             de= enreg_time
#             secondes_debut_enreg= float(de.timestamp())
#             plage=float(item[4]*3600)
#             secondes_fin_enreg=float(secondes_debut_enreg)+plage
#
#             if secondes_rez_debut<=secondes_debut_enreg<=secondes_rez_fin:
#                 if interv_rez_hres==0:
#                     avertissement=True
#                     message=message+Markup("<b>Cette ressource est déjà réservée par l'unité "+str(row[5])+".</b><br>") \
#
#                 else:
#                     avertissement=True
#                     message=message+Markup("<b>Cette réservation entre en conflit avec une autre réservation adjacente. Veuillez tenir compte de " \
#                                    "l'intervalle de "+str(interv_rez_hres)+" heures exigé par le syndicat entre chaque réservation.</b><br>") \
#
#             elif secondes_debut_enreg<=secondes_rez_debut<=secondes_fin_enreg:
#                 if interv_rez_hres==0:
#                     avertissement=True
#                     message=message+Markup("<b>Cette ressource est déjà réservée par l'unité "+str(row[5])+".</b><br>") \
#
#                 else:
#                     avertissement=True
#                     message=message+Markup("<b>Cette réservation entre en conflit avec une autre réservation adjacente. Veuillez tenir compte de " \
#                                    "l'intervalle de "+str(interv_rez_hres)+" heures exigé par le syndicat entre chaque réservation.</b><br>")
#
#             if avertissement==True:
#                 message=message+Markup("Veuillez modifier les champs visés afin de compléter cette réservation.")
#                 flash(message,'warning')
#                 return render_template('reservation_ajout_proprio_mess.html',fill_rez=liste_rez,fill_modes=fill_modes_paiement)
#
#         compteur_jrs+=1
#
#     if avertissement==False:
#         compteur_jrs=0
#         while compteur_jrs<float(request.form['jrs_consecutifs']):
#             date_rez_courante=rez_time+timedelta(days=compteur_jrs)
#             heure_rez_courante=request.form['heure_rez']
#
#             # mode de paiement doit être un numérique
#             if request.form['mode_paiement']=='':#champ vide
#                 mode_paiement=0
#             else:
#                 mode_paiement=request.form['mode_paiement']
#             # ajout de la réservation
#             cur.execute('INSERT INTO reservations (DateHeureCreation,IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, Note, Courriel, ModePaiement) '
#                         'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
#                         [ local_time, request.form['ident_ress'], client_ident, date_rez_courante,heure_rez_courante,
#                           request.form['duree_rez'],request.form['no_unite'],request.form['note'],request.form['courriel'],mode_paiement])
#             cnx.commit()
#             compteur_jrs+=1
#
#     #envoi de courriel d'alerte à l'adresse dans les paramètres si rez facturable
#     email_list=[]
#     cur.execute("SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",(client_ident,))
#     for item in cur.fetchall():
#         email_a=item[0]
#         email_list=email_a.split(',')
#
#     if facturable==1:
#         yahoo_mail_user = 'condofix.ca@yahoo.com'
#         yahoo_mail_password = 'spyvlumgfwscqfkc'
#
#         no_unite = request.form['no_unite']
#         date = request.form['date_rez']
#         heure = request.form['heure_rez']
#         duree = request.form['duree_rez']
#         jours = request.form['jrs_consecutifs']
#         courriel = request.form['courriel']
#         note = request.form['note']
#         mode=request.form['mode_paiement']
#         cur.execute("SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s",
#                     (mode, client_ident))
#         for item in cur.fetchall():
#             mode_de_paiement = item[0]
#
#         msg = MIMEMultipart("related")
#         msg['Subject'] = "Réservation facturable"
#         msg['From'] = yahoo_mail_user
#         html = """
#             <html><body>
#             <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
#             <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
#             <b>Date:</b>&nbsp;{date}<br/>
#             <b>Heure:</b>&nbsp;{heure}<br/>
#             <b>Durée (h.):</b>&nbsp;{duree}<br/>
#             <b>Jours:</b>&nbsp;{jours}<br/>
#             <b>Courriel:</b>&nbsp;{courriel}<br/>
#             <b>Mode de paiement:</b>&nbsp;{mode_de_paiement}<br/>
#             <b>Note:</b>&nbsp;{note}</p>
#             </body></html>
#             """
#
#         html = html.format(desc_ress=desc_ress, no_unite=no_unite, date=date, heure=heure, duree=duree, jours=jours,
#                            courriel=courriel, mode_de_paiement=mode_de_paiement, note=note)
#
#         # enregistrer le MIME pour l'HTML
#         contenu = MIMEText(html, 'html')
#         # attacher le contenu au 'container' du message
#         msg.attach(contenu)
#         try:
#             server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
#             server.ehlo()
#             server.login(yahoo_mail_user, yahoo_mail_password)
#             # sendmail function takes 3 arguments: sender's address, recipient's address
#             # and message to send - here it is sent as one string.
#             for i in range(len(email_list)):
#                 server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
#             server.quit()
#
#         except:
#                 print(traceback.format_exc())
#         cnx.close()
#         return redirect(url_for('bp_reservations.calendrier_rez',usager='proprio'))
#     else:
#         # pas facturable
#         return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))


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

    if facturable == 1 and email_list:
        yahoo_mail_user = 'condofix.ca@yahoo.com'

        # TODO PBI sécurité:
        # déplacer ce mot de passe dans une variable d'environnement.
        yahoo_mail_password = 'spyvlumgfwscqfkc'

        msg = MIMEMultipart("related")
        msg['Subject'] = "Annulation d'une réservation facturable"
        msg['From'] = yahoo_mail_user

        html = """
            <html><body>
            <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
            <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
            <b>Date:</b>&nbsp;{date}<br/>
            <b>Heure:</b>&nbsp;{heure}<br/>
            <b>Durée (h.):</b>&nbsp;{duree}<br/>
            <b>Note:</b>&nbsp;{note}</p>
            </body></html>
        """

        html = html.format(
            desc_ress=desc_ress,
            no_unite=no_unite,
            date=date,
            heure=heure,
            duree=duree,
            note=note
        )

        msg.attach(MIMEText(html, 'html'))

        try:
            server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
            server.ehlo()
            server.login(yahoo_mail_user, yahoo_mail_password)

            for email in email_list:
                server.sendmail(yahoo_mail_user, email, msg.as_string())

            server.quit()

        except:
            print(traceback.format_exc())

    flash("La réservation a été annulée.", "success")
    return redirect(url_for('bp_reservations.mes_rez'))
# # affichage de la page de 'mes reservations'
# @bp_reservations.route("/mes_rez")
# def mes_rez():
#     """Afficher la page des réservations d'un copropriétaire selon leur numéro d'unité. Permet de supprimer
#     une réservation."""
#     return render_template('reservations_mon_unite.html')
#
#
# #fonctions pour afficher les réservations d'une unité
# @bp_reservations.route("/reservations_unite", methods=['POST','GET'])
# def reservations_unite():
#     """Afficher la page des réservations d'un copropriétaire selon leur numéro d'unité. Permet de supprimer
#     une réservation."""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#     no_unite_rez=request.form['unite_no']
#     liste_rez_unite=[]
#     cur.execute("SELECT IDReservation, IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, Note FROM reservations "
#                 "WHERE Date>=%s AND NoUnite=%s AND IDClient=%s",(datetime.now().strftime('%Y-%m-%d'),no_unite_rez,client_ident))
#     for row in cur.fetchall():
#         cur.execute('SELECT Description FROM ressources WHERE IDRessource=%s AND IDClient=%s',(row[1],client_ident))
#         for item in cur.fetchall():
#             row+=(item)
#         liste_rez_unite.append(row)
#     cnx.close()
#     # trier les réservations selon la date ascendante
#     liste_rez_unite.sort( key=lambda tup: tup[3])
#     return render_template('reservations_mon_unite.html',liste_rez_unite=liste_rez_unite)
#
#
# #fonctions pour supprimer une réservations
# @bp_reservations.route("/rez_unite_supprime/<id_rez>")
# def rez_unite_supprime(id_rez):
#     """À partir de la page 'mes réservations' supprimer un enregistrement affiché par un copropriétaire."""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#
#     id_ressource=0
#     facturable=0
#     date=''
#     heure=''
#     duree=0
#     note=str()
#     no_unite=0
#     email=str()
#     desc_ress=str()
#
#     #trouver ressource de la réservation (premier élément des paramètres)
#     cur.execute("SELECT IDRessource, Date, HeureDebut, DureeHres, NoUnite, Note from reservations WHERE IDReservation=%s AND IDClient=%s",(int(id_rez),client_ident))
#     for item in cur.fetchall():
#         id_ressource=item[0]
#         date=str(item[1])
#         heure=str(item[2])
#         duree=str(item[3])
#         note=item[5]
#         no_unite=item[4]
#     #trouver type de réservation (facturable)
#     cur.execute("SELECT Facturable,Description from ressources WHERE IDRessource=%s AND IDClient=%s",(id_ressource,client_ident))
#     for item_1 in cur.fetchall():
#         facturable=item_1[0]
#         desc_ress=item_1[1]
#     # supprimer la réservation
#     cur.execute("DELETE FROM reservations WHERE IDReservation=%s AND IDClient=%s",(int(id_rez),client_ident))
#     cnx.commit()
#     email_list=[]
#     # si réservation est facturable, aviser de la suppression par email
#     if facturable==1:
#         # trouver email admin
#         cur.execute("SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",(client_ident,))
#         for item_2 in cur.fetchall():
#             email_a=item_2[0]
#             email_list=email_a.split(',')
#         yahoo_mail_user = 'condofix.ca@yahoo.com'
#         yahoo_mail_password = 'spyvlumgfwscqfkc'
#
#         msg = MIMEMultipart("related")
#         msg['Subject'] = "Annulation d'une réservation facturable"
#         msg['From'] = yahoo_mail_user
#         html = """
#                     <html><body>
#                     <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
#                     <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
#                     <b>Date:</b>&nbsp;{date}<br/>
#                     <b>Heure:</b>&nbsp;{heure}<br/>
#                     <b>Durée (h.):</b>&nbsp;{duree}<br/>
#                     <b>Note:</b>&nbsp;{note}</p>
#                     </body></html>
#                     """
#
#         html = html.format(desc_ress=desc_ress, no_unite=no_unite, date=date, heure=heure, duree=duree, note=note)
#
#         # enregistrer le MIME pour l'HTML
#         contenu = MIMEText(html, 'html')
#         # attacher le contenu au 'container' du message
#         msg.attach(contenu)
#         try:
#             server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
#             server.ehlo()
#             server.login(yahoo_mail_user, yahoo_mail_password)
#             # sendmail function takes 3 arguments: sender's address, recipient's address
#             # and message to send - here it is sent as one string.
#             for i in range(len(email_list)):
#                 server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
#             server.quit()
#         except:
#             print(traceback.format_exc())
#     cnx.close()
#     return redirect(url_for('bp_reservations.calendrier_rez',usager='proprio'))
#

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
    if facturable==1 and futur==1:
        # trouver email admin
        cur.execute("SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",(client_ident,))
        for item_2 in cur.fetchall():
            email_a=item_2[0]
            email_list=email_a.split(',')
        yahoo_mail_user = 'condofix.ca@yahoo.com'
        yahoo_mail_password = 'spyvlumgfwscqfkc'

        msg = MIMEMultipart("related")
        msg['Subject'] = "Annulation d'une réservation facturable"
        msg['From'] = yahoo_mail_user
        html = """
                            <html><body>
                            <p><b>Ressource:</b>&nbsp;{desc_ress}<br/>
                            <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
                            <b>Date:</b>&nbsp;{date}<br/>
                            <b>Heure:</b>&nbsp;{heure}<br/>
                            <b>Durée (h.):</b>&nbsp;{duree}<br/>
                            <b>Note:</b>&nbsp;{note}</p>
                            </body></html>
                            """

        html = html.format(desc_ress=desc_ress, no_unite=no_unite, date=date, heure=heure, duree=duree, note=note)

        # enregistrer le MIME pour l'HTML
        contenu = MIMEText(html, 'html')
        # attacher le contenu au 'container' du message
        msg.attach(contenu)
        try:
            server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
            server.ehlo()
            server.login(yahoo_mail_user, yahoo_mail_password)
            # sendmail function takes 3 arguments: sender's address, recipient's address
            # and message to send - here it is sent as one string.
            for i in range(len(email_list)):
                server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
            server.quit()
        except:
            print(traceback.format_exc())

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
