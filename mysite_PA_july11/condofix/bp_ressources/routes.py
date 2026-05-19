from flask import Blueprint, render_template,g,session,url_for,redirect,request,flash
import mysql.connector
from datetime import datetime
from utils import connect_db

bp_ressources = Blueprint('bp_ressources', __name__)

#***************Gestion des catégories (paramétrables) ******************************
@bp_ressources.route("/ressources_table")
def ressources_table():
    """afficher la page de la table d'enregistrements avec fonction ajout et modif
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion=profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fill_ressources=[]
    cur.execute("SELECT IDRessource, Description, DureeMaxHres, DelaiMinHres, DelaiMaxJrs, JoursConsecutifsPermis, HreDebutPermise, HreFinPermise,"
                " DateDebutNonDispo, DureeNonDispoHres, IntervalleRezHres, Facturable, Actif FROM ressources WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        # modifier format des heures de '00:00:00' à '00:00'
        hre_debut=str(row[6])
        if len(hre_debut)==8: #heure avec 2 premiers caractères ex. 19:00:00
            hre_start=hre_debut[0:5]
        else:                   #heure avec 1 premier caractère ex. 9:00:00
            hre_start=hre_debut[0:4]
        row+=(hre_start,)
        hre_fin=str(row[7])
        if len(hre_fin)==8: #heure avec 2 premiers caractères ex. 19:00:00
            hre_end=hre_fin[0:5]
        else:                   #heure avec 1 premier caractère ex. 9:00:00
            hre_end=hre_fin[0:4]
        row+=(hre_end,)
        # créer statut des champs cochés
        if row[11]==1:
            facturable='oui'
        else:
            facturable='non'
        row+=(facturable,)

        if row[12]==1:
            actif='oui'
        else:
            actif='non'
        row+=(actif,)

        fill_ressources.append(row)
    cnx.close()
    return render_template('ressources_table.html', fill_ressources=fill_ressources,bd=profile_list[3])

@bp_ressources.route('/ressource_enreg/<parametre>')
def ressource_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fill_ressource=[]
    nbre_actifs=0
    if parametre=='0':#ajout
        # vérifier le nombre de ressources actives
        cur.execute("SELECT IDRessource, Description, DureeMaxHres, DelaiMinHres, Facturable, Actif FROM ressources "
                    "WHERE IDClient=%s",(client_ident,))
        for row in cur.fetchall():
            if row[5]==1:
                nbre_actifs+=1
        if nbre_actifs>=10:
            flash('Le nombre de ressources actives ne peut dépasser 10. Veuillez désactiver une ressource avant un ajout.','warning')
            return redirect(url_for('bp_ressources.ressources_table'))
        else:
            return render_template('ressource_ajout.html', bd=profile_list[3])
    else: #modif
        cur.execute("SELECT IDRessource, Description,DureeMaxHres, DelaiMinHres, DelaiMaxJrs, JoursConsecutifsPermis, HreDebutPermise, "
                    "HreFinPermise, DateDebutNonDispo, DureeNonDispoHres, IntervalleRezHres ,Facturable, Actif FROM ressources WHERE IDRessource=%s AND IDClient=%s",(parametre,client_ident))
        for row in cur.fetchall():
            # pour s'assurer que les heures avant 12:00 (ex. 08:00) s'affichent correetement
            # convertit en format 1900-01-01 07:00:00
            if row[6] is not None:
                hre_debut_datetime=datetime.strptime(str(row[6]), '%H:%M:%S' )
                # extraire l'heure seulement
                hre_permise_debut=hre_debut_datetime.time()
                # ajouter à la liste
                row+=(hre_permise_debut,)
            if row[7] is not None:
                hre_fin_datetime=datetime.strptime(str(row[7]), '%H:%M:%S' )
                hre_permise_fin=hre_fin_datetime.time()
                row+=(hre_permise_fin,)
            fill_ressource.append(row)
            return render_template('ressource_modif.html',fill_ressource=fill_ressource, bd=profile_list[3])

#fonctions pour ajouter ou modifier une ressource
@bp_ressources.route("/ressource_ajout", methods=['POST'])
def ressource_ajout():
    """Ajouter une ressource réservable.

    Notes fonctionnelles:
    - DureeMaxHres: durée maximale d'une réservation, en heures.
    - DelaiMinHres: délai minimal avant le début de la réservation, en heures.
    - DelaiMaxJrs: délai maximal pour réserver à l'avance, en jours.
    - IntervalleRezHres: pause obligatoire entre deux réservations, stockée en heures décimales.
      Le formulaire expose cette valeur en heures + minutes pour éviter que l'utilisateur doive saisir
      des décimales comme 0.5 pour 30 minutes.
    - DateDebutNonDispo / DureeNonDispoHres: ancienne logique de non-disponibilité unique.
      Si la section n'est pas activée, on conserve une valeur neutre avec durée 0.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Admin système / gestionnaire seulement.
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode_connexion = profile_list[8]

    def parse_float(field_name, default=None):
        raw_value = request.form.get(field_name)

        if raw_value is None or str(raw_value).strip() == '':
            if default is not None:
                return default
            raise ValueError(field_name)

        return float(str(raw_value).replace(',', '.'))

    def parse_int(field_name, default=None):
        raw_value = request.form.get(field_name)

        if raw_value is None or str(raw_value).strip() == '':
            if default is not None:
                return default
            raise ValueError(field_name)

        return int(float(str(raw_value).replace(',', '.')))

    try:
        ress_desc = request.form.get('ress_desc', '').strip()
        if not ress_desc:
            flash("La description de la ressource est obligatoire.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

        duree_max = parse_float('duree_max')
        delai_min = parse_int('delai_min')
        delai_max = parse_int('delai_max')
        jrs_consecutifs = parse_int('jrs_consecutifs', 1)

        heure_debut = request.form.get('heure_debut', '00:00')
        heure_fin = request.form.get('heure_fin', '00:00')

        intervalle_heures = parse_int('intervalle_heures', 0)
        intervalle_minutes = parse_int('intervalle_minutes', 0)
        intervalle = round(intervalle_heures + (intervalle_minutes / 60), 2)

        val_facturable = 1 if request.form.get('facturable') is not None else 0
        val_actif = 1 if request.form.get('actif') is not None else 0

        non_dispo_active = request.form.get('non_dispo_active') is not None

        if non_dispo_active:
            date_debut_non_dispo = request.form.get('date_debut_non_dispo', '').strip()
            duree_non_dispo = parse_int('duree_non_dispo')

            if not date_debut_non_dispo:
                flash("La date de début de non-disponibilité est obligatoire si la section est activée.", "warning")
                return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

            if duree_non_dispo < 1:
                flash("La durée de non-disponibilité doit être d'au moins 1 heure.", "warning")
                return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))
        else:
            # Valeurs neutres pour l'ancienne logique de non-disponibilité.
            date_debut_non_dispo = '2021-01-01'
            duree_non_dispo = 0

        if duree_max < 0.5:
            flash("La durée maximale de réservation doit être d'au moins 0.5 heure.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

        if delai_min < 0:
            flash("Le délai minimal ne peut pas être négatif.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

        if delai_max < 1:
            flash("Le délai maximal doit être d'au moins 1 jour.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

        if delai_max * 24 < delai_min:
            flash("Le délai maximal en jours doit être supérieur ou égal au délai minimal en heures.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

        if jrs_consecutifs < 1:
            flash("Le nombre de jours consécutifs doit être d'au moins 1.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

        if intervalle < 0:
            flash("L'intervalle entre les réservations ne peut pas être négatif.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

    except ValueError:
        flash("Veuillez vérifier les valeurs numériques du formulaire.", "warning")
        return redirect(url_for('bp_ressources.ressource_enreg', parametre=0))

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # Protection serveur: si la nouvelle ressource est active, on valide encore la limite de 10 ressources actives.
    if val_actif == 1:
        cur.execute(
            "SELECT COUNT(*) FROM ressources WHERE IDClient = %s AND Actif = 1",
            (client_ident,)
        )
        nbre_actifs = cur.fetchone()[0]

        if nbre_actifs >= 10:
            cnx.close()
            flash("Le nombre de ressources actives ne peut dépasser 10. Veuillez désactiver une ressource avant un ajout.", "warning")
            return redirect(url_for('bp_ressources.ressources_table'))

    cur.execute(
        "INSERT INTO ressources "
        "(IDClient, Description, DureeMaxHres, DelaiMinHres, DelaiMaxJrs, JoursConsecutifsPermis, "
        "HreDebutPermise, HreFinPermise, DateDebutNonDispo, DureeNonDispoHres, IntervalleRezHres, Facturable, Actif) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            client_ident,
            ress_desc,
            duree_max,
            delai_min,
            delai_max,
            jrs_consecutifs,
            heure_debut,
            heure_fin,
            date_debut_non_dispo,
            duree_non_dispo,
            intervalle,
            val_facturable,
            val_actif
        ]
    )

    cnx.commit()
    cnx.close()

    return redirect(url_for('bp_ressources.ressources_table'))
# @bp_ressources.route("/ressource_ajout", methods=['POST'])
# def ressource_ajout():
#     """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""
#
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
#     if profile_list[2] >2:
#         return redirect(url_for('permission'))
#     client_ident=profile_list[0]
#     mode_connexion = profile_list[8]
#     cnx = connect_db(mode_connexion)
#     cur = cnx.cursor()
#     if request.form.get('facturable')==None:
#         val_facturable=0
#     else:
#         val_facturable=1
#     cur.execute("INSERT INTO ressources (IDClient, Description,DureeMaxHres, DelaiMinHres, DelaiMaxJrs, JoursConsecutifsPermis, HreDebutPermise, "
#                 "HreFinPermise, DateDebutNonDispo, DureeNonDispoHres, IntervalleRezHres ,Facturable, Actif) "
#                 "VALUES (%s, %s, %s, %s, %s, %s,  %s, %s, %s, %s, %s, %s, %s)",
#                 [client_ident,request.form['ress_desc'],float(request.form['duree_max']),int(request.form['delai_min']),int(request.form['delai_max']),
#                  int(request.form['jrs_consecutifs']),request.form['heure_debut'],request.form['heure_fin'],request.form['date_debut_non_dispo'],
#                  int(request.form['duree_non_dispo']),float(request.form['intervalle']), val_facturable, 1])
#     cnx.commit()
#     cnx.close()
#     return redirect(url_for('bp_ressources.ressources_table'))


@bp_ressources.route('/ressource_modif/<ident_ress>', methods=['POST'])
def ressource_modif(ident_ress):
    """Modifier une ressource réservable.

    Cette version est alignée avec le nouveau formulaire:
    - l'intervalle entre réservations est reçu en heures + minutes;
    - la non-disponibilité temporaire est optionnelle;
    - les validations serveur protègent l'intégrité même si la validation HTML est contournée.
    """

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Admin système / gestionnaire seulement.
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))

    client_ident = profile_list[0]
    mode_connexion = profile_list[8]

    def parse_float(field_name, default=None):
        raw_value = request.form.get(field_name)

        if raw_value is None or str(raw_value).strip() == '':
            if default is not None:
                return default
            raise ValueError(field_name)

        return float(str(raw_value).replace(',', '.'))

    def parse_int(field_name, default=None):
        raw_value = request.form.get(field_name)

        if raw_value is None or str(raw_value).strip() == '':
            if default is not None:
                return default
            raise ValueError(field_name)

        return int(float(str(raw_value).replace(',', '.')))

    try:
        ress_desc = request.form.get('ress_desc', '').strip()
        if not ress_desc:
            flash("La description de la ressource est obligatoire.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        duree_max = parse_float('duree_max')
        delai_min = parse_int('delai_min')
        delai_max = parse_int('delai_max')
        jrs_consecutifs = parse_int('jrs_consecutifs', 1)

        heure_debut = request.form.get('heure_debut', '00:00')
        heure_fin = request.form.get('heure_fin', '00:00')

        intervalle_heures = parse_int('intervalle_heures', 0)
        intervalle_minutes = parse_int('intervalle_minutes', 0)
        intervalle = round(intervalle_heures + (intervalle_minutes / 60), 2)

        val_facturable = 1 if request.form.get('facturable') is not None else 0
        val_actif = 1 if request.form.get('actif') is not None else 0

        non_dispo_active = request.form.get('non_dispo_active') is not None

        if non_dispo_active:
            date_debut_non_dispo = request.form.get('date_debut_non_dispo', '').strip()
            duree_non_dispo = parse_int('duree_non_dispo')

            if not date_debut_non_dispo:
                flash("La date de début de non-disponibilité est obligatoire si la section est activée.", "warning")
                return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

            if duree_non_dispo < 1:
                flash("La durée de non-disponibilité doit être d'au moins 1 heure.", "warning")
                return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))
        else:
            # Valeurs neutres pour l'ancienne logique de non-disponibilité.
            date_debut_non_dispo = '2021-01-01'
            duree_non_dispo = 0

        if duree_max < 0.5:
            flash("La durée maximale de réservation doit être d'au moins 0.5 heure.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        if delai_min < 0:
            flash("Le délai minimal ne peut pas être négatif.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        if delai_max < 1:
            flash("Le délai maximal doit être d'au moins 1 jour.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        if delai_max * 24 < delai_min:
            flash("Le délai maximal en jours doit être supérieur ou égal au délai minimal en heures.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        if jrs_consecutifs < 1:
            flash("Le nombre de jours consécutifs doit être d'au moins 1.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        if intervalle < 0:
            flash("L'intervalle entre les réservations ne peut pas être négatif.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

        if intervalle_minutes < 0 or intervalle_minutes > 59:
            flash("Les minutes de l'intervalle doivent être entre 0 et 59.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

    except ValueError:
        flash("Veuillez vérifier les valeurs numériques du formulaire.", "warning")
        return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # Protection serveur: si on active cette ressource, vérifier la limite de 10 ressources actives.
    # On exclut la ressource courante du décompte.
    if val_actif == 1:
        cur.execute(
            "SELECT COUNT(*) FROM ressources "
            "WHERE IDClient = %s AND Actif = 1 AND IDRessource <> %s",
            (client_ident, ident_ress)
        )
        nbre_autres_actifs = cur.fetchone()[0]

        if nbre_autres_actifs >= 10:
            cnx.close()
            flash("Le nombre de ressources actives ne peut dépasser 10. Veuillez désactiver une ressource avant d'activer celle-ci.", "warning")
            return redirect(url_for('bp_ressources.ressource_enreg', parametre=ident_ress))

    cur.execute(
        "UPDATE ressources SET "
        "Description = %s, "
        "DureeMaxHres = %s, "
        "DelaiMinHres = %s, "
        "DelaiMaxJrs = %s, "
        "JoursConsecutifsPermis = %s, "
        "HreDebutPermise = %s, "
        "HreFinPermise = %s, "
        "DateDebutNonDispo = %s, "
        "DureeNonDispoHres = %s, "
        "IntervalleRezHres = %s, "
        "Facturable = %s, "
        "Actif = %s "
        "WHERE IDRessource = %s AND IDClient = %s",
        [
            ress_desc,
            duree_max,
            delai_min,
            delai_max,
            jrs_consecutifs,
            heure_debut,
            heure_fin,
            date_debut_non_dispo,
            duree_non_dispo,
            intervalle,
            val_facturable,
            val_actif,
            ident_ress,
            client_ident
        ]
    )

    cnx.commit()
    cnx.close()

    return redirect(url_for('bp_ressources.ressources_table'))

# @bp_ressources.route('/ressource_modif/<ident_ress>', methods=['POST'])
# def ressource_modif(ident_ress):
#     """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""
#
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
#     if profile_list[2] > 2:
#         return redirect(url_for('bp_admin.permission'))
#     if request.form.get('facturable')==None:
#         val_facturable=0
#     else:
#         val_facturable=1
#     if request.form.get('actif')==None:
#         val_actif=0
#     else:
#         val_actif=1
#     client_ident=profile_list[0]
#     mode_connexion = profile_list[8]
#     cnx = connect_db(mode_connexion)
#     cur = cnx.cursor()
#     # étant donné champ non obligatoire dans formulaire
#     if request.form['duree_non_dispo']=='':
#         duree_non_dispo=0
#     else:
#         duree_non_dispo=request.form['duree_non_dispo']
#     cur.execute("UPDATE ressources SET Description= %s, DureeMaxHres= %s, DelaiMinHres= %s, DelaiMaxJrs= %s, JoursConsecutifsPermis= %s, "
#                 "HreDebutPermise= %s, HreFinPermise= %s, DateDebutNonDispo= %s, DureeNonDispoHres= %s, IntervalleRezHres= %s,"
#                 "Facturable=%s, Actif= %s WHERE IDRessource = %s AND IDClient=%s",
#                  [request.form['ress_desc'],float(request.form['duree_max']),int(request.form['delai_min']),int(request.form['delai_max']),
#                   int(request.form['jrs_consecutifs']),request.form['heure_debut'],request.form['heure_fin'],request.form['date_debut_non_dispo'],
#                   duree_non_dispo,float(request.form['intervalle']),val_facturable,val_actif,ident_ress,client_ident])
#     cnx.commit()
#     cnx.close()
#     return redirect(url_for('bp_ressources.ressources_table'))

#***************Gestion des modes de paiement pour les ressources facturables ******************************
@bp_ressources.route("/modes_paiement_table")
def modes_paiement_table():
    """afficher la page de la table d'enregistrements avec fonction ajout et modif
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    # vérifier si le client a acheté le module réservations
    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fill_modes_paiement=[]
    cur.execute("SELECT IDPaiement, Description FROM modepaiement WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        fill_modes_paiement.append(row)
    cnx.close()
    return render_template('mode_paiement_table.html', fill_paiements=fill_modes_paiement,bd=profile_list[3])

@bp_ressources.route('/mode_paiement_enreg/<parametre>')
def mode_paiement_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fill_mode_paiement=[]
    nbre_actifs=0
    if parametre=='0':#ajout
        return render_template('mode_paiement_ajout.html', bd=profile_list[3])
    else: #modif
        cur.execute("SELECT IDPaiement,Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s",(parametre,client_ident))
        for row in cur.fetchall():
            fill_mode_paiement.append(row)
    return render_template('mode_paiement_modif.html',fill_paiement=fill_mode_paiement, bd=profile_list[3])

#fonctions pour ajouter ou modifier une ressource
@bp_ressources.route("/mode_paiement_ajout", methods=['POST'])
def mode_paiement_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] >2:
        return redirect(url_for('permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("INSERT INTO modepaiement (IDClient,Description) VALUES (%s, %s)", [client_ident,request.form['desc_mode']])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_ressources.modes_paiement_table'))

@bp_ressources.route('/mode_paiement_modif/<ident_mode>', methods=['POST'])
def mode_paiement_modif(ident_mode):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("UPDATE modepaiement SET Description= %s WHERE IDPaiement = %s AND IDClient=%s",
                [request.form['desc_mode'],ident_mode,client_ident])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_ressources.modes_paiement_table'))

@bp_ressources.route('/mode_paiement_supprime/<ident_mode>', methods=['POST','GET'])
def mode_paiement_supprime(ident_mode):
    """Supprimer un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("DELETE FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s",(ident_mode,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_ressources.modes_paiement_table'))