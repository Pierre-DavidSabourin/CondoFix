from flask import Blueprint, render_template,redirect,url_for,g,session,flash,request,redirect, json
import sqlite3
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import time
import mysql.connector
import traceback
from pathlib import Path
from utils import connect_db

bp_admin = Blueprint('bp_admin', __name__)

@bp_admin.route('/login', methods=['GET', 'POST'])
def login():
    """
    * Rechercher les données de login pour l'usager dans la BD SQLite 'Central'
    * Vérifier le mot de passe et enregistrer les infos d'usager dans 'session'
    * Vérifier si la mise à jour des entretiens préventifs est requise
    * Vérifier si un rapport d'activité doit être envoyé (selon la fréquence configurée)
    * Ouvrir l'application sur la page appropriée ('tickets en cours' ou proprios)
    """

    # -------------------------------------------------------------------------
    # Fonctions utilitaires
    # -------------------------------------------------------------------------

    def get_tentatives():
        """Retourne les tentatives restantes, initialise à 3 si manquant."""
        if 'solde_tentatives' not in session or session['solde_tentatives'] is None:
            session['solde_tentatives'] = 3
        return session['solde_tentatives']

    def safe_decrement_attempts():
        """Décrémente les tentatives en sécurité et redirige si session expirée."""
        nbr = get_tentatives()

        if nbr not in (3, 0):
            flash(
                f"Il vous reste encore {nbr} tentatives de saisie de code d'accès avant que la session se termine.",
                "warning",
            )

        if nbr == 0:
            session.clear()
            return redirect(url_for('bp_public.home'))

        session['solde_tentatives'] = nbr - 1
        return None

    # GET → simple affichage
    if request.method == 'GET':
        return render_template('login_page.html')

    # -------------------------------------------------------------------------
    # POST — Vérification des identifiants
    # -------------------------------------------------------------------------

    matches = ["--", "#", "/", "*", "%", ";", "+", "=", "<", ">", "|"]
    if any(x in request.form['password'] for x in matches) or any(x in request.form['usager'] for x in matches):
        flash("Caractères non valides. Veuillez saisir de nouveau.", "warning")
        return render_template('login_page.html')

    login_usager = str(request.form['usager'])


    # -------------------------------------------------------------------------
    # Détection de l'environnement + chemin SQLite
    # -------------------------------------------------------------------------
    env_path = str(Path.cwd())
    if 'home/CondoFix/QA' in env_path:
        env = 'QA';    dbpath = '/home/CondoFix/mysite/condofix/Central.db'
    elif 'home/CondoFix/mysite' in env_path:
        env = 'APP';   dbpath = '/home/CondoFix/mysite/condofix/Central.db'
    elif 'mysite_PA_july11' in env_path:
        env = 'DEV';   dbpath = 'Central.db'
    elif 'CondoFixBeta' in env_path:
        env = 'BETA';  dbpath = '/home/CondoFix/CondoFixBeta/mysite_PA_july11/condofix/Central.db'
    else:
        env = 'APP';   dbpath = '/home/CondoFix/mysite/condofix/Central.db'


    # -------------------------------------------------------------------------
    # Récupération de l'usager
    # -------------------------------------------------------------------------
    g.db = sqlite3.connect(dbpath)
    cur = g.db.execute(
        "SELECT IDUsager, IDClient, NomUsager, IDTypeUsager, EMail, MotPasse, Actif "
        "FROM Usagers WHERE NomUsager=?",
        (login_usager,)
    )

    try:
        row = cur.fetchone()
        if row is None:
            raise ValueError("Usager inexistant")

        user_ident, client_ident, user_nom, type_ident, user_email, password, actif = row

        if actif == 0:
            flash("Usager non actif", "warning")
            result = safe_decrement_attempts()
            if result: return result
            return redirect(url_for('bp_admin.login'))

        # ---------------------------------------------------------------------
        # Récupération du client
        # ---------------------------------------------------------------------
        cur = g.db.execute(
            "SELECT Nom, Actif, ModuleRez, CarnetPlus, Database FROM Clients WHERE IDClient=?",
            (client_ident,)
        )
        row_client = cur.fetchone()
        if row_client is None:
            raise ValueError("Client inexistant")

        client_name, client_actif, module_rez, carnet_plus, dbase = row_client

        if client_actif == 0:
            flash("Client non actif", "warning")
            result = safe_decrement_attempts()
            if result: return result
            return redirect(url_for('bp_admin.login'))

        g.db.close()

        # ---------------------------------------------------------------------
        # Vérification du mot de passe
        # ---------------------------------------------------------------------
        if request.form['password'] != password:
            flash("Mot de passe invalide.", "warning")
            result = safe_decrement_attempts()
            if result: return result
            return render_template('login_page.html')

        # ---------------------------------------------------------------------
        # Création de la session de l'usager
        #   0 → client_ident   : Usagers.IDClient (FK → Clients.IDClient)
        #   1 → user_ident     : Usagers.IDUsager (primary key of the user)
        #   2 → type_ident     : Usagers.IDTypeUsager (role / permission type)
        #   3 → client_name    : Clients.Nom (display name of the client)
        #   4 → user_nom       : Usagers.NomUsager (username)
        #   5 → module_rez     : Clients.ModuleRez (feature flag)
        #   6 → carnet_plus    : Clients.CarnetPlus (feature flag)
        #   7 → dbase          : Clients.Database (database name for this client)
        #   8 → env            : Environment indicator (dev/test/prod)

        # ---------------------------------------------------------------------
        ident_list = [
            client_ident, user_ident, type_ident,
            client_name, user_nom, module_rez,
            carnet_plus, dbase, env
        ]

        session['logged_in'] = True       # Usager authentifié
        session.permanent = True          # Timeout selon l'inactivité (voir flask_app.py)
        session['ProfilUsager'] = ident_list  # Profil complet pour permissions

        # ---------------------------------------------------------------------
        # 1. ACHALANDAGE — Mise à jour du trafic mensuel
        # ---------------------------------------------------------------------
        cnx = connect_db(env)
        cur = cnx.cursor()

        mois_encours = datetime.now().month  # 1–12
        # ------------------------------------------------------------
        # ASSURER QUE LA LIGNE D'ACHALANDAGE EXISTE POUR (Client, TypeUsager)
        # ------------------------------------------------------------
        cur.execute(
            "SELECT 1 FROM achalandage WHERE IDClient=%s AND TypeUsager=%s",
            (client_ident, type_ident)
        )
        exists = cur.fetchone()

        if not exists:
            # Insérer une nouvelle ligne avec les valeurs initiales
            cur.execute(
                "INSERT INTO achalandage (IDClient, TypeUsager, Jan, Fev, Mars, Avril, Mai, Juin, "
                "Juil, Aout, Sept, Oct, Nov, `Dec`, DateDebut, CumLogins) "
                "VALUES (%s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, %s, 0)",
                (client_ident, type_ident, datetime.now().date())
            )
            cnx.commit()

        cur.execute(
            "SELECT `Jan`, `Fev`, `Mars`, `Avril`, `Mai`, `Juin`, `Juil`, `Aout`, "
            "`Sept`, `Oct`, `Nov`, `Dec`, `DateDebut`, `CumLogins` "
            "FROM achalandage WHERE IDClient=%s AND TypeUsager=%s",
            (client_ident, type_ident)
        )
        row = cur.fetchone()

        if row:
            months = list(row[:12])
            date_debut = row[12]
            cum_logins_total = row[13] or 0

            # Incrément du mois courant
            cur_value = months[mois_encours - 1]
            months[mois_encours - 1] = 1 if cur_value is None else cur_value + 1

            # Remise à zéro du mois suivant
            next_month = 1 if mois_encours == 12 else mois_encours + 1
            months[next_month - 1] = 0

            cum_logins_total += 1

            update_sql = (
                "UPDATE achalandage SET "
                "`Jan`=%s, `Fev`=%s, `Mars`=%s, `Avril`=%s, `Mai`=%s, `Juin`=%s, "
                "`Juil`=%s, `Aout`=%s, `Sept`=%s, `Oct`=%s, `Nov`=%s, `Dec`=%s, "
                "`CumLogins`=%s "
                "WHERE IDClient=%s AND TypeUsager=%s"
            )
            cur.execute(update_sql, (*months, cum_logins_total, client_ident, type_ident))
            cnx.commit()

        # ---------------------------------------------------------------------
        # 2. REDIRECTION DES COPROPRIÉTAIRES
        # ---------------------------------------------------------------------
        # Important:
        # Les copropriétaires ne doivent pas déclencher les traitements administratifs
        # au login, comme la MAJ du calendrier préventif ou l'envoi du rapport d'activité.
        # Ces traitements peuvent rediriger vers des pages protégées et produire
        # l'écran "Vous n'avez pas accès à cette fonctionnalité!".
        # ---------------------------------------------------------------------
        if type_ident == 5:
            print("LOGIN FINAL REDIRECT - COPROPRIETAIRE", {
                "user_ident": user_ident,
                "type_ident": type_ident,
                "client_ident": client_ident,
                "module_rez": module_rez,
                "carnet_plus": carnet_plus,
                "target": "bp_documentation.docs_table_proprios"
            })

            cnx.close()
            return redirect(url_for('bp_documentation.docs_table_proprios'))

        # ---------------------------------------------------------------------
        # 3. VÉRIFICATION DU BUDGET — Renouvellement annuel
        # ---------------------------------------------------------------------
        cur.execute(
            "SELECT DateDebutBudget FROM parametres WHERE IDClient=%s",
            (client_ident,)
        )
        row_budget = cur.fetchone()

        if row_budget:
            date_debut_budget = row_budget[0]
            date_today = datetime.now().date()
            end_date = date_debut_budget + relativedelta(years=1)

            if date_today >= end_date:
                cur.execute(
                    "UPDATE parametres SET DateDebutBudget=%s WHERE IDClient=%s",
                    (end_date, client_ident)
                )
                cnx.commit()

        # ---------------------------------------------------------------------
        # 4. PRÉVENTIF + RAPPORT D'ACTIVITÉ
        # ---------------------------------------------------------------------
        # Ces traitements restent réservés aux profils administratifs.
        # ---------------------------------------------------------------------
        cur.execute(
            "SELECT Date_MAJ_Preventif, DateRapportActivite, FreqRapportActivite "
            "FROM parametres WHERE IDClient=%s",
            (client_ident,)
        )
        row_prev = cur.fetchone()

        if row_prev:
            date_preventif, date_rapport, freq_rapport = row_prev
            today = datetime.today().date()

            # MAJ du calendrier d'entretien ?
            if date_preventif and today >= date_preventif:
                print("LOGIN ADMIN REDIRECT - MAJ CALENDRIERS", {
                    "user_ident": user_ident,
                    "type_ident": type_ident,
                    "client_ident": client_ident,
                    "target": "bp_admin.maj_calendriers",
                    "date_preventif": str(date_preventif)
                })

                cnx.close()
                return redirect(url_for('bp_admin.maj_calendriers', date_maj=str(date_preventif)))

            if date_rapport and freq_rapport and (today - date_rapport).days >= freq_rapport:
                print("LOGIN ADMIN REDIRECT - RAPPORT ACTIVITE", {
                    "user_ident": user_ident,
                    "type_ident": type_ident,
                    "client_ident": client_ident,
                    "target": "bp_rapports.envoi_rapport_activite",
                    "dernier_envoi": str(date_rapport),
                    "freq_rapport": freq_rapport
                })

                cnx.close()
                return redirect(url_for(
                    'bp_rapports.envoi_rapport_activite',
                    dernier_envoi=str(date_rapport),
                    type_usager=type_ident
                ))

        print("LOGIN FINAL REDIRECT - ADMIN/OTHER", {
            "user_ident": user_ident,
            "type_ident": type_ident,
            "client_ident": client_ident,
            "module_rez": module_rez,
            "carnet_plus": carnet_plus,
            "target": "bp_tickets.en_cours"
        })

        cnx.close()
        return redirect(url_for('bp_tickets.en_cours'))

    except Exception as e:
        print(traceback.format_exc())
        flash("Usager non valide", "warning")
        result = safe_decrement_attempts()
        if result: return result
        return render_template('login_page.html')

# @bp_admin.route('/login', methods=['GET', 'POST'])
# def login():
#     """ * Rechercher les données de login pour l'usager dans la bd sqlite 'Central'
#      * Vérification du mot de passe et capture des infos d'usager dans 'session'
#      * Vérifier si on doit mettre à jour les entretiens préventifs (si date actuelle est premier du mois)
#      * Vérifier si envoi du rapport d'activité requis (selon intervalle en jours saisis dans paramètres)
#      * Ouverture de l'application en privé sur la page des 'tickets en cours'
#     """
#     # vérifier s'il y a des caractères 'dangereux' dans le nom d'usager ou le mot de passe
#     if request.method == 'POST':
#         matches = ["--", "#", "/", "*", "%", ";", "+", "=", "<", ">", "|"]
#         if any(x in request.form['password'] for x in matches) or any(x in request.form['usager'] for x in matches):
#             flash('Caractères non valides. Veuillez saisir de nouveau.', "warning")
#             return render_template('login_page.html')
#
#     user_list = []
#     ident_list = []
#     error = None
#     env = str()
#     if request.method == 'POST':
#         # vérifier s'il y a des caractères 'dangereux' dans le nom d'usager ou le mot de passe
#         matches = ["--", "#", "/", "*", "%", ";", "+", "=", "<", ">", "|"]
#         if any(x in request.form['password'] for x in matches) or any(x in request.form['usager'] for x in matches):
#             flash('Caractères non valides. Veuillez saisir de nouveau.', "warning")
#             return redirect(url_for('bp_admin.login'))
#         login_usager = str(request.form['usager'])
#         # vérifier si l'app est utilisé en dev (pycharm) ou en prod (QA,demo ou app chez PythonAnywhere (PA))
#         environnement = Path.cwd()
#         if 'home/CondoFix/QA' in str(environnement):
#             env = 'QA'
#         if 'home/CondoFix/mysite' in str(environnement):
#             env = 'APP'
#         if 'mysite_PA_july11' in str(environnement):
#             env = 'DEV'
#         if 'CondoFixBeta' in str(environnement):
#             env = 'BETA'
#
#         if env == 'DEV':
#             g.db = sqlite3.connect(str('Central.db'))
#         if env == 'QA' or env == 'APP':
#             g.db = sqlite3.connect(str('/home/CondoFix/mysite/condofix/Central.db'))
#         if env == 'BETA':
#             g.db = sqlite3.connect('/home/CondoFix/CondoFixBeta/mysite_PA_july11/condofix/Central.db')
#
#         # pour environnement demo, on utilise la liste de prospects pour 'matcher' le code d'accès
#         # utiliser le bp_admin de 'demos' pour celui-ci car beaucoup moins de code
#         cur = g.db.execute(
#             "SELECT IDUsager,IDClient, NomUsager, IDTypeUsager,EMail,MotPasse,Actif FROM Usagers WHERE NomUsager=?",
#             (login_usager,))
#         try:
#             for row in cur.fetchone():
#                 user_list.append(row)
#             password = user_list[5]
#             user_ident = user_list[0]
#             user_nom = user_list[2]
#             client_ident = user_list[1]
#             type_ident = user_list[3]
#             actif = user_list[6]
#             module_rez = int()
#             if actif == 0:
#                 flash('Usager non actif', "warning")
#                 # pour permettre un maximum de 3 tentatives de saisie de code d'accès par session
#                 nbr_essais = session.get('solde_tentatives')
#                 if nbr_essais != 3 and nbr_essais != 0:
#                     flash("Il vous reste encore " + str(
#                         nbr_essais) + " tentatives de saisie de code d'accès avant que la session se termine.",
#                           "warning")
#                 if nbr_essais == 0:
#                     session.clear()
#                     return redirect(url_for('bp_public.home'))
#                 nbr_essais -= 1
#                 session['solde_tentatives'] = nbr_essais
#                 return redirect(url_for('bp_admin.login'))
#             ident_list.append(client_ident)
#             ident_list.append(user_ident)
#             ident_list.append(type_ident)
#             client_name = str()
#             carnet_plus = str()
#             cur = g.db.execute("SELECT Nom, Actif, ModuleRez, CarnetPlus, Database FROM Clients WHERE IDClient=?",
#                                (client_ident,))
#             for row_1 in cur.fetchall():
#                 if row_1[1] == 0:
#                     flash('Client non actif', "warning")
#                     # pour permettre un maximum de 3 tentatives de saisie de code d'accès par session
#                     nbr_essais = session.get('solde_tentatives')
#                     if nbr_essais != 3 and nbr_essais != 0:
#                         flash("Il vous reste encore " + str(
#                             nbr_essais) + " tentatives de saisie de code d'accès avant que la session se termine.",
#                               "warning")
#                     if nbr_essais == 0:
#                         session.clear()
#                         return redirect(url_for('bp_public.home'))
#                     nbr_essais -= 1
#                     session['solde_tentatives'] = nbr_essais
#                     return redirect(url_for('bp_admin.login'))
#                 client_name = row_1[0]
#                 module_rez = row_1[2]
#                 carnet_plus = row_1[3]
#                 dbase = row_1[4]
#             ident_list.append(client_name)
#             ident_list.append(user_nom)
#             ident_list.append(module_rez)
#             ident_list.append(carnet_plus)
#             ident_list.append(dbase)
#             g.db.close()
#             if request.form['password'] != password:
#                 flash('Mot de passe invalide.', "warning")
#                 # pour permettre un maximum de 3 tentatives de saisie de code d'accès par session
#                 nbr_essais = session.get('solde_tentatives')
#                 if nbr_essais != 3 and nbr_essais != 0:
#                     flash("Il vous reste encore " + str(
#                         nbr_essais) + " tentatives de saisie de code d'accès avant que la session se termine.",
#                           "warning")
#                 if nbr_essais == 0:
#                     session.clear()
#                     return redirect(url_for('bp_public.home'))
#                 nbr_essais -= 1
#                 session['solde_tentatives'] = nbr_essais
#                 return render_template('login_page.html')
#             else:
#
#                 ident_list.append(env)
#
#                 session['logged_in'] = True
#                 # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
#                 session.permanent = True
#                 # profil d'usager pour permissions et IDs pour enregistrements
#
#                 session['ProfilUsager'] = ident_list
#                 # trouver le mode de connexion (Dev ou PA)
#                 profile_list = session.get('ProfilUsager')
#                 mode_connexion = profile_list[8]
#
#                 # enregistrer le login pour l'achalandage
#                 cnx = connect_db(mode_connexion)
#                 cur = cnx.cursor()
#                 mois = int()
#                 mois_suivant = int()
#                 mois_encours = int(datetime.now().month)
#
#                 cur.execute("SELECT * from achalandage WHERE IDClient=%s AND TypeUsager=%s", (client_ident, type_ident))
#                 for row in cur.fetchall():
#                     index = mois_encours + 2  # on ajoute 2 pour tomber sur le mois en cours dans la liste de rubriques
#                     cum_logins_mois = row[index]
#                     if cum_logins_mois == None:
#                         cum_logins_mois = 1
#                     else:
#                         cum_logins_mois += 1
#                     cum_logins_debut = row[16]
#                     if mois_encours == 1:
#                         mois = 'Jan'
#                         mois_suivant = 'Fev'
#                     elif mois_encours == 2:
#                         mois = 'Fev'
#                         mois_suivant = 'Mars'
#                     elif mois_encours == 3:
#                         mois = 'Mars'
#                         mois_suivant = 'Avril'
#                     elif mois_encours == 4:
#                         mois = 'Avril'
#                         mois_suivant = 'Mai'
#                     elif mois_encours == 5:
#                         mois = 'Mai'
#                         mois_suivant = 'Juin'
#                     elif mois_encours == 6:
#                         mois = 'Juin'
#                         mois_suivant = 'Juil'
#                     elif mois_encours == 7:
#                         mois = 'Juil'
#                         mois_suivant = 'Aout'
#                     elif mois_encours == 8:
#                         mois = 'Aout'
#                         mois_suivant = 'Sept'
#                     elif mois_encours == 9:
#                         mois = 'Sept'
#                         mois_suivant = 'Oct'
#                     elif mois_encours == 10:
#                         mois = 'Oct'
#                         mois_suivant = 'Nov'
#                     elif mois_encours == 11:
#                         mois = 'Nov'
#                         mois_suivant = 'Dec'
#                     elif mois_encours == 12:
#                         mois = 'Dec'
#                         mois_suivant = 'Jan'
#                     # print('mois sélectionné:', mois_encours)
#                     # print('row:',row)
#                     # print('mois actuel:',mois)
#                     cum_logins_debut += 1
#                     cur.reset()
#                     cur.execute(
#                         "UPDATE achalandage SET `{}`=%s, CumLogins=%s WHERE IDClient = %s AND TypeUsager=%s".format(
#                             mois),
#                         (cum_logins_mois, cum_logins_debut, client_ident, type_ident))
#                     cnx.commit()
#                     # mettre mois suivant à zéro
#                     cur.execute(
#                         "UPDATE achalandage SET `{}`=%s WHERE IDClient = %s AND TypeUsager=%s".format(mois_suivant),
#                         (0, client_ident, type_ident))
#                     cnx.commit()
#
#                 # vérifier si date de fin de budget est atteinte
#                 cur.execute("SELECT DateDebutBudget FROM parametres WHERE IDClient=%s", (client_ident,))
#                 for item in cur.fetchall():
#                     date_debut = item[0]
#                     date_today = datetime.now().date()
#                     end_date = date_debut + relativedelta(years=1)
#                     if date_today >= end_date:
#                         # on met à jour la date de début un an plus tard
#                         cur.execute("UPDATE parametres SET DateDebutBudget=%s WHERE IDClient=%s",
#                                     (end_date, client_ident))
#                         cnx.commit()
#
#                 # vérifier si on doit mettre à jour les entretiens préventifs ou si envoi du rapport d'activité requis
#
#                 cur.execute(
#                     "SELECT Date_MAJ_Preventif, DateRapportActivite, FreqRapportActivite  FROM parametres WHERE IDClient=%s",
#                     (client_ident,))
#                 date_rapport_activite = str()
#                 for row_2 in cur.fetchall():
#                     freq_rapport = int(row_2[2])  # jours entre chaque rapport
#
#                     # on vérifie si la maj du calendrier d'entretien est requise
#                     date_format = "%Y-%m-%d"
#                     date_visee = row_2[0]
#                     date_maj = str(date_visee)
#                     date_now = str(date.today())
#                     a = datetime.strptime(date_maj, date_format)
#                     b = datetime.strptime(date_now, date_format)
#                     delta = b - a
#                     if delta.days >= 0:  # on est rendu à la date de MAJ du calendrier d'entretien et du fonds de prévoyance
#                         cnx.close()
#                         return redirect(url_for('bp_admin.maj_calendriers', date_maj=date_maj))
#                     else:  # MAJ du calendrier non requise
#
#                         # on vérifie si un rapport d'activité doit être envoyé
#                         date_format = "%Y-%m-%d"
#                         date_rapport_activite = str(row_2[1])
#                         date_now = str(date.today())
#                         a = datetime.strptime(date_rapport_activite, date_format)
#                         b = datetime.strptime(date_now, date_format)
#                         delta = b - a
#                         cnx.close()
#
#                         # return redirect(
#                         #     url_for('bp_rapports.envoi_rapport_activite', dernier_envoi=date_rapport_activite,
#                         #             type_usager=type_ident))
#                         # print('delta:',delta.days, 'fréquence rapport:',freq_rapport)
#                         if delta.days > (freq_rapport - 1):  # on est rendu à la date d'envoi d'un nouveau rapport
#                             return redirect(
#                                 url_for('bp_rapports.envoi_rapport_activite', dernier_envoi=date_rapport_activite,
#                                         type_usager=type_ident))
#                         else:  # pas de rapport envoyé
#                             if type_ident == 5:
#                                 return redirect(url_for('bp_documentation.docs_table_proprios'))
#                                 # return 'Page proprios'
#
#                             return redirect(url_for('bp_tickets.en_cours'))
#         except:
#             print(traceback.format_exc())
#             flash('Usager non valide', "warning")
#             # pour permettre un maximum de 3 tentatives de saisie de code d'accès par session
#             nbr_essais = session.get('solde_tentatives')
#             if nbr_essais != 3 and nbr_essais != 0:
#                 flash("Il vous reste encore " + str(
#                     nbr_essais) + " tentatives de saisie de code d'accès avant que la session se termine.", "warning")
#             if nbr_essais == 0:
#                 session.clear()
#                 return redirect(url_for('bp_public.home'))
#             nbr_essais -= 1
#             session['solde_tentatives'] = nbr_essais
#             return render_template('login_page.html')
#     return render_template('login_page.html')


# MAJ de la date du calendrier d'entretien et du fonds de prévoyance lors du premier jour de chaque mois
@bp_admin.route("/maj_calendriers/<date_maj>")
def maj_calendriers(date_maj):
    """MAJ de la date des prochaines interventions du calendrier d'entretien et du FDP lors du premier jour de chaque mois.
    1- obtenir profil d'usager à partir de session créée lors du login (IDs client, usager, etc)
    2- si premier du mois: recherche de tous les entretiens actifs dans mysql
    3- si date prochaine due: création d'un ticket"""

    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    usager_id = profile_list[1]

    # trouver le mode de connexion (Dev ou PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    mois_courant = 0
    annee_courant = 0

    # ***************** 1- maj calendrier d'entretien ********************************************************
    # recherche de tous les entretiens préventifs actifs
    cur.execute(
        "SELECT IDPreventif, Description, Emplacement, HresEstimees, IDIntervenant, IDEquipement, IDCategorie, FreqAns, DateProchain, "
        "Janv, Fev, Mars, Avril, Mai, Juin, Juil, Aout, Sept, Oct, Nov, `Dec` FROM preventif WHERE IDClient=%s",
        (client_ident,)
    )
    date_format = "%Y-%m-%d"
    for row in cur.fetchall():
        a = datetime.strptime(str(row[8]), date_format)
        b = datetime.strptime(date_maj, date_format)
        delta = b - a
        if delta.days >= 0:  # la date prochaine de l'enregistrement est égale ou inférieure à la date de MAJ
            # calcul de prochaine date de cet entretien préventif
            date_cour = datetime.strptime(date_maj, "%Y-%m-%d")
            mois_courant = date_cour.month
            annee_courant = date_cour.year
            freq_annuelle = row[7]
            mois_trouve = False

            # créer liste de la valeur de chaque mois de l'enregistrement
            liste_calendar = row[9:21]

            # valider si mois suivant prévu est dans liste_calendar
            i = 0
            while i < 12:
                if liste_calendar[i] == 1:
                    if i + 1 > mois_courant:
                        d = datetime(annee_courant + (freq_annuelle - 1), i + 1, 1)
                        date_suivante = d.date()
                        mois_trouve = True
                if mois_trouve is True:
                    # on passe à l'autre enregistrement
                    break
                else:
                    i += 1

            # le mois suivant prévu n'est pas dans la même année
            if mois_trouve is False:
                date_suivante = str()
                j = 0
                annee_courant = annee_courant + 1
                while j < 12:
                    if liste_calendar[j] == 1:
                        d = datetime(annee_courant + (freq_annuelle - 1), j + 1, 1)
                        date_suivante = d.date()
                        break
                    else:
                        j = j + 1

            # on met à jour l'enregistrement en cours
            cur.execute(
                "UPDATE preventif SET DateProchain=%s WHERE IDPreventif = %s AND IDClient=%s",
                (date_suivante, row[0], client_ident,)
            )
            cnx.commit()

            # création d'un nouveau ticket
            cur.execute(
                'INSERT INTO tickets (IDClient, IDUsager, IDIntervenant, DateCreation, Emplacement, Statut, Priorite, TypeTravail, '
                'Description_travail, IDCategorie, IDEquipement, DatePrevue, HeuresEstimees, CoutTotalTTC, CoutMainOeuvre, CoutMateriel) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                [client_ident, usager_id, row[4], time.strftime('%Y-%m-%d %H:%M'), row[2], "2", "4", "3",
                 row[1], row[6], row[5], row[8], row[3], 0, 0, 0]
            )
            cnx.commit()

    # ***************** 2- maj fonds de prévoyance ********************************************************

    date_cour = datetime.now()
    mois_courant = date_cour.month
    annee_courant = date_cour.year
    usager_id = profile_list[1]

    # recherche de tous les entretiens dûs selon le groupe Uniformat II
    cur.execute(
        "SELECT IDFondsPrevoyance,IDIntervenant,IDCategorie,DescriptionDepense,TypeMtceRempl,RefGroupeUniformat,RefAnalyse,"
        "ValeurActuelleInterv,IDEquipement,PartSyndicat,AnProchain,Actif from fondsprevoyance WHERE IDClient=%s and Actif=1",
        (client_ident,)
    )

    for row in cur.fetchall():
        # --- Robust parsing / null guards (hotfix) ---
        try:
            an_prochain = int(row[10])  # AnProchain
            ref_groupe = int(row[5])    # RefGroupeUniformat
        except (TypeError, ValueError):
            # junk/incomplete record -> skip
            continue

        if an_prochain != annee_courant:
            continue

        # traitement selon IDGroupeUniformat et mois courant
        # nouveau code Uniformat 'Z' (ID=9) pour Parties communes à usage restreint avec création de ticket en mai
        if ((ref_groupe < 3 and mois_courant == 4) or
            (ref_groupe == 3 and mois_courant == 1) or
            (3 < ref_groupe < 6 and mois_courant == 10) or
            (5 < ref_groupe < 9 and mois_courant == 7) or
            (ref_groupe == 9 and mois_courant == 5)):

            # création d'un nouveau ticket
            # modification de la description pour ajouter la valeur et le numéro d'item de l'étude du FDP (MAX 200 cars.)
            desc_trav = str(row[3] or "")

            valeur = row[7]
            try:
                valeur = float(valeur) if valeur is not None else 0.0
            except (TypeError, ValueError):
                valeur = 0.0

            item = "" if row[6] is None else str(row[6])

            part = row[9]
            try:
                part = float(part) if part is not None else 0.0
            except (TypeError, ValueError):
                part = 0.0

            pct = int(round(part * 100))
            add_text = f" Valeur: {valeur}$ Item {item} à {pct}%"

            # enforce max length 200 chars
            desc_trav = (desc_trav + add_text)[:200]

            cur.execute(
                'INSERT INTO tickets (IDClient, IDUsager, IDIntervenant, DateCreation, Statut, Priorite, '
                'TypeTravail, Description_travail, IDCategorie, IDEquipement, DatePrevue, HeuresEstimees,'
                'CoutTotalTTC, CoutMainOeuvre, CoutMateriel) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                [client_ident, usager_id, row[1], date_cour, "2", "4", "2",
                 desc_trav, row[2], row[8], date_cour, 0, 0, 0, 0]
            )
            cnx.commit()

    # mettre à jour la date de prochaine MAJ dans les paramètres
    date_cour = datetime.strptime(date_maj, "%Y-%m-%d")
    date_res = date_cour + relativedelta(months=1)
    date_prochaine_maj = date_res.date()
    cur.execute("UPDATE parametres SET Date_MAJ_Preventif=%s WHERE IDClient=%s", (date_prochaine_maj, client_ident,))
    cnx.commit()
    # g.db.close()

    # ouverture de l'application selon le type d'usager
    if profile_list[2] == 5:  # proprios
        return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))
    else:
        return redirect(url_for('bp_tickets.en_cours'))


@bp_admin.route('/logout')
def logout():
    """retour à la page publique de bienvenue"""
    session.clear()
    session.pop('logged_in', None)
    return redirect (url_for('bp_public.home'))

#page d'avis d'accès non permis'
@bp_admin.route("/permission")
def permission():
    """page affichée si l'usager n'a pas la permission d'afficher des infos"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    return render_template('permission_admin.html')


#pages d'aides produites avec Sphinx
# ouvrir page d'aide principale
#@bp_admin.route('/aide')
#def aide():
#    return render_template('index_1.html')

@bp_admin.route('/aide')
def aide():
    """ouverture de la section d'aide"""
#    return send_from_directory('/help', 'index_1.html')
    return redirect (url_for('static', filename='index.html'))

@bp_admin.route('/videos')
def videos():
    """ouverture de la section de vidéos"""
    return render_template('video_formation_OCR.html')

