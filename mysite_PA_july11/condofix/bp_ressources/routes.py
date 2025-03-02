from flask import Blueprint, render_template,g,session,url_for,redirect,request,flash
import mysql.connector
from datetime import datetime
from mysite_PA_july11.utils import connect_db

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
    if request.form.get('facturable')==None:
        val_facturable=0
    else:
        val_facturable=1
    cur.execute("INSERT INTO ressources (IDClient, Description,DureeMaxHres, DelaiMinHres, DelaiMaxJrs, JoursConsecutifsPermis, HreDebutPermise, "
                "HreFinPermise, DateDebutNonDispo, DureeNonDispoHres, IntervalleRezHres ,Facturable, Actif) "
                "VALUES (%s, %s, %s, %s, %s, %s,  %s, %s, %s, %s, %s, %s, %s)",
                [client_ident,request.form['ress_desc'],float(request.form['duree_max']),int(request.form['delai_min']),int(request.form['delai_max']),
                 int(request.form['jrs_consecutifs']),request.form['heure_debut'],request.form['heure_fin'],request.form['date_debut_non_dispo'],
                 int(request.form['duree_non_dispo']),float(request.form['intervalle']), val_facturable, 1])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_ressources.ressources_table'))

@bp_ressources.route('/ressource_modif/<ident_ress>', methods=['POST'])
def ressource_modif(ident_ress):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    if request.form.get('facturable')==None:
        val_facturable=0
    else:
        val_facturable=1
    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    # étant donné champ non obligatoire dans formulaire
    if request.form['duree_non_dispo']=='':
        duree_non_dispo=0
    else:
        duree_non_dispo=request.form['duree_non_dispo']
    cur.execute("UPDATE ressources SET Description= %s, DureeMaxHres= %s, DelaiMinHres= %s, DelaiMaxJrs= %s, JoursConsecutifsPermis= %s, "
                "HreDebutPermise= %s, HreFinPermise= %s, DateDebutNonDispo= %s, DureeNonDispoHres= %s, IntervalleRezHres= %s,"
                "Facturable=%s, Actif= %s WHERE IDRessource = %s AND IDClient=%s",
                 [request.form['ress_desc'],float(request.form['duree_max']),int(request.form['delai_min']),int(request.form['delai_max']),
                  int(request.form['jrs_consecutifs']),request.form['heure_debut'],request.form['heure_fin'],request.form['date_debut_non_dispo'],
                  duree_non_dispo,float(request.form['intervalle']),val_facturable,val_actif,ident_ress,client_ident])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_ressources.ressources_table'))

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