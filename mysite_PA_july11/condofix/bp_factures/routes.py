import sys

from flask import Blueprint, render_template, g, session, request, redirect, url_for, flash, send_file
from markupsafe import Markup  # Import Markup separately
import mysql.connector
import os
import time
from datetime import datetime,timedelta
from mysite_PA_july11.utils import connect_db, chemin_rep

bp_factures = Blueprint('bp_factures', __name__)

#page des bp_tickets en attente de facture
@bp_factures.route('/attente_facture')
def attente_facture():
    """Affichage de la table des tickets en attente de facture"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    nom_client=profile_list[7]
    # vérifier type d'usager
    if profile_list[2]==3 or profile_list[2]==5 :# pas accessible par l'employé ou le proprio
        return redirect(url_for('bp_admin.permission'))
    ticket_list=[]
    client_ident=profile_list[0]
    mode_connexion=profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT IDTicket, IDClient,IDUsager,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, DateComplet, "
                "HeuresEstimees, HeuresRequises, Nbre_visites, NoFacture, CoutMainOeuvre, CoutMateriel,Evaluation,CoutTotalTTC, IntervenantAutre FROM tickets WHERE Statut=3 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s", (row[3],client_ident))
        for item in cur.fetchall():
            IntervenantNom=item
            row+=(IntervenantNom)#18
        cur.execute("SELECT Description FROM priorite WHERE IDPriorite=%s", (row[5],))
        for item_x in cur.fetchall():
            Desc_priorite=item_x
            row+=(Desc_priorite)#19
        # ajout de montants en $ de main d'oeuvre et matériel sans taxes
        tot_mdo=int((0 if row[13] == None or row[13] == '' else row[13]))
        row+=(tot_mdo,)#20
        tot_mat=int((0 if row[14] == None or row[14] == '' else row[14]))
        row+=(tot_mat,)#21
        ticket_list.append(row)

    cnx.close()

    ticket_list.sort(key = lambda x: x[7])
    return render_template('attente_facture_table.html', ticket_list=ticket_list,bd=profile_list[3])

#fonction d'ajout de facture et/ou fermeture de ticket une fois facture saisie
@bp_factures.route('/creation_facture/<id_ticket>', methods=['POST','GET'])
def creation_facture(id_ticket):
    """Afficher les données du ticket pour l'ajout d'une facture"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    ticket_list=[]
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_ticket=[]
    cur.execute("SELECT IDTicket, IDIntervenant, Description_travail, DateComplet, HeuresEstimees, HeuresRequises, "
                      "Nbre_visites,Multitags, IntervenantAutre FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row in cur.fetchall():
        #vérifier si rubrique 'IntervenantAutre' est remplie
        if row[8]=='' or row[8]=='None':
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
                        (row[1], client_ident))
            for item in cur.fetchall():
                IntervenantNom = item
                row += IntervenantNom
        else:
            row += (row[8],)

        ticket_list.append(row)
        liste_ticket=[list(row) for row in ticket_list]
        # vérifier si c'est un multitags
        if row[7]==1:
            message=Markup("<b>Ce ticket no."+id_ticket+" est de type 'Multitags' car il s'applique à de multiples équipements.</b><br>") \
                    +Markup("Vous pouvez ainsi partager le montant de la facture avec un ticket dupliqué selon le travail effectué sur chaque équipement.<br>") \
                    +Markup("Un duplicata de ce ticket s'affichera à la fin de cette table dès que vous cliquerez sur 'Dupliquer'.<br>") \
                    +Markup("Lors de l'attribution du numéro de tag et des dépenses sur ces tickets, ne pas oublier de: <br>") \
                    +Markup("- modifier la description <br>") \
                    +Markup("- ajuster les heures requises <br>") \
                    +Markup("- décocher 'multi-tags'")
            flash(message, "warning")
            return redirect(url_for('bp_factures.attente_facture'))

    return render_template('facture_ajout.html', liste_ticket=liste_ticket[0],bd=profile_list[3])

#fonction d'ajout de facture et/ou fermeture de ticket une fois facture saisie
@bp_factures.route('/creation_facture_non_ocr/<id_ticket>', methods=['POST','GET'])
def creation_facture_non_ocr(id_ticket):
    """Afficher les données du ticket pour l'ajout d'une facture"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    ticket_list=[]
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    afficher_MDO_MAT=int()
    cur.execute("SELECT Affiche_MDO_MAT FROM parametres WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        afficher_MDO_MAT=row[0]
    #print('MDO MAT:0', afficher_MDO_MAT)
    liste_ticket=[]
    cur.execute("SELECT IDTicket, IDIntervenant, Description_travail, DateComplet, HeuresEstimees, HeuresRequises, "
                      "Nbre_visites,Multitags, IntervenantAutre FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row in cur.fetchall():
        #vérifier si rubrique 'IntervenantAutre' est remplie
        if row[8]=='' or row[8]=='None':
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
                        (row[1], client_ident))
            for item in cur.fetchall():
                IntervenantNom = item
                row += IntervenantNom
        else:
            row += (row[8],)

        ticket_list.append(row)
        liste_ticket=[list(row) for row in ticket_list]
        # vérifier si c'est un multitags
        if row[7]==1:
            message=Markup("<b>Ce ticket no."+id_ticket+" est de type 'Multitags' car il s'applique à de multiples équipements.</b><br>") \
                    +Markup("Vous pouvez ainsi partager le montant de la facture avec un ticket dupliqué selon le travail effectué sur chaque équipement.<br>") \
                    +Markup("Un duplicata de ce ticket s'affichera à la fin de cette table dès que vous cliquerez sur 'Dupliquer'.<br>") \
                    +Markup("Lors de l'attribution du numéro de tag et des dépenses sur ces tickets, ne pas oublier de: <br>") \
                    +Markup("- modifier la description <br>") \
                    +Markup("- ajuster les heures requises <br>") \
                    +Markup("- décocher 'multi-tags'")
            flash(message, "warning")
            return redirect(url_for('bp_factures.attente_facture'))

    return render_template('facture_ajout.html', afficher_MDO_MAT=afficher_MDO_MAT, liste_ticket=liste_ticket[0],bd=profile_list[3])

@bp_factures.route('/facture_ajout/<id_ticket>', methods=['POST','GET'])
def facture_ajout(id_ticket):
    """Ajout de l'enregistrement à la table factures.

    |Une fois la facture enregistrée dans mySQL, ajouter les informations de la facture à l'enregistrement du ticket

    |Retour à la table de tickets en attente de facture"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')    # global date_ferme
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    compte_gl=str()
    val_mat=float()
    # trouver no. du compte GL
    cur.execute("SELECT IDCategorie FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row in cur.fetchall():
        cur.execute("SELECT CodeGl FROM categories WHERE IDCategorie=%s AND IDClient=%s", (row[0],client_ident))
        for item in cur.fetchall():
            compte_gl=item[0]
    # on vérifie si la mdo et mat sont affichables
    cur.execute("SELECT Affiche_MDO_MAT FROM parametres WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        afficher_MDO_MAT = row[0]
    if afficher_MDO_MAT==1:
        if request.form['mdo']=='':
            val_mdo=0
        else:
            val_mdo=float(request.form['mdo'])
        if request.form['mat']=='':
            val_mat=0
        else:
            val_mat=float(request.form['mat'])
    else:
        val_mdo=0
        val_mat=0

    # ajout de la facture à la base de données
    cur.execute('INSERT INTO factures (IDClient,DateSaisie,Fournisseur,NoFacture,MDO_HT,MAT_HT,TotalAvecTx,CpteGL,IDTicket) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',[client_ident, time.strftime('%Y-%m-%d'),request.form['fournisseur'],
                request.form['no_facture'], val_mdo, val_mat, request.form['total_facture_taxes'], compte_gl, id_ticket])
    cnx.commit()

    # ajout des infos au ticket
    cur.execute("SELECT NoFacture,CoutMainOeuvre,CoutMateriel, CoutTotalTTC FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row_1 in cur.fetchall():
        if row_1[0]==None or row_1[0]=='None' or row_1[0]=='':
            nos_factures=request.form['no_facture']
        else:
            nos_factures=str(row_1[0])+'/'+str(request.form['no_facture'])

        if row_1[1]==None or row_1[1]=='None' or row_1[1]==''or row_1[1]==0:
            mdo=round(float(val_mdo),2)
        else:
            mdo=float(row_1[1])+round(float(val_mdo),2)

        if row_1[3] == None or row_1[3] == 'None' or row_1[3] == '' or row_1[3] == 0:
            total = round(float(request.form['total_facture_taxes']), 2)
        else:
            total = float(row_1[3]) + round(float(request.form['total_facture_taxes']), 2)

        if row_1[2]==None or row_1[2]=='None' or row_1[2]=='' or row_1[2]==0:
            mat=round(float(val_mat),2)
        else:
            mat=float(row_1[2])+round(float(val_mat),2)

        cur.execute("UPDATE tickets SET NoFacture=%s, CoutTotalTTC = %s, CoutMainOeuvre = %s, CoutMateriel = %s, Evaluation = %s "
                     "WHERE IDTicket = %s AND IDClient=%s", (nos_factures, total, mdo, mat, request.form['eval'], id_ticket,client_ident))
        cnx.commit()
        cnx.close()

    return redirect(url_for("bp_factures.attente_facture"))

#affichage de la table de factures
@bp_factures.route('/factures_table', methods=['POST','GET'])
def factures_table():
    """Affichage de la table de factures avec boutons de modif et d'exportation"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    factures_list=[]
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT IDFacture,NoFacture,DateSaisie,Fournisseur,MDO_HT,MAT_HT,TotalAvecTx,CpteGL, IDTicket, CheminPath FROM factures WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        # pour afficher si numérisée ou non
        if row[9]=='' or row[9]==None:
            row+=('non',)
        else:
            row += ('oui',)
        factures_list.append(row)
    cnx.close()
    return render_template('factures_table.html', date_debut='', factures_list=factures_list,bd=profile_list[3])

#modification de facture
@bp_factures.route('/facture_modif/<id_facture>', methods=['POST','GET'])
def facture_modif(id_facture):
    """Afficher l'enregistrement d'une facture existante pour modification"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    afficher_MDO_MAT = int()
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT IDFacture,NoFacture,DateSaisie,Fournisseur,MDO_HT,MAT_HT,TotalAvecTx,CpteGL,CheminPath,IDTicket "
                      "FROM factures WHERE IDFacture=%s AND IDClient=%s", (id_facture,client_ident))
    for row in cur.fetchall():
        facture_list.append(row)
    # on vérifie si la mdo et mat sont affichables
    cur.execute("SELECT Affiche_MDO_MAT FROM parametres WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        afficher_MDO_MAT = row[0]

    return render_template('facture_modif.html', facture_list=facture_list[0], afficher_MDO_MAT = afficher_MDO_MAT, bd=profile_list[3])

#affichage de l'image de facture
@bp_factures.route('/facture_affiche/<id_facture>', methods=['POST','GET'])
def facture_affiche(id_facture):
    """Afficher l'image numérisée d'une facture existante"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    chemin_doc = str()
    cur.execute("SELECT CheminPath FROM factures WHERE IDFacture=%s AND IDClient=%s", (id_facture, client_ident))
    for item in cur.fetchall():
        folder=chemin_rep(mode_connexion)
        # ajout du chemin du fichier recherché
        if item[0] == None or item[0] == '':
            return redirect(url_for('bp_factures.factures_table'))
        chemin_doc = folder+ item[0]
        # pour obtenir le titre du doc seulement
        titre = item[0].split("docs/", 1)[1]
        cnx.close()
    return send_file(chemin_doc, attachment_filename=titre, cache_timeout=0)

@bp_factures.route('/facture_modif_post/<id_facture>', methods=['POST','GET'])
def facture_modif_post(id_facture):
    """Modifier la facture affichée"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # else: #pas de fichier téléchargé en remplacement
    # on vérifie si la mdo et mat sont affichables
    afficher_MDO_MAT=0
    val_mdo=float()
    val_mat=float()
    cur.execute("SELECT Affiche_MDO_MAT FROM parametres WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        afficher_MDO_MAT = row[0]
    if afficher_MDO_MAT == 1:
        if request.form['mdo'] == '':
            val_mdo = 0
        else:
            val_mdo = float(request.form['mdo'])
        if request.form['mat'] == '':
            val_mat = 0
        else:
            val_mat = float(request.form['mat'])
    else:
        val_mdo = 0

    cur.execute(
        "UPDATE factures SET Fournisseur=%s,MDO_HT=%s,MAT_HT=%s,TotalAvecTx=%s WHERE IDFacture=%s AND IDClient=%s",
        (
        [request.form['fournisseur'], val_mdo, val_mat, request.form['total_facture_taxes'],
         id_facture, client_ident]))
    cnx.commit()

    #modifier les valeurs en $ du ticket concerné

    cur.execute("SELECT CoutTotalTTC, CoutMainOeuvre, CoutMateriel FROM tickets WHERE IDTicket = %s AND IDClient=%s", (request.form['id_ticket'],client_ident))
    TTC_ticket_apres = float()
    mdo_ticket_apres=float()
    mat_ticket_apres=float()

    for row in cur.fetchall():
        # valeurs de la facture avant modif
        TTC_fact_avant = float(request.form['TTC_original'])
        mdo_fact_avant=float(request.form['mdo_original'])
        mat_fact_avant=float(request.form['mat_original'])
        # variation entre facture précédente et l'actuelle
        TTC_var = float(request.form['total_facture_taxes']) - TTC_fact_avant

        #print('TTC_var =', float(request.form['total_facture_taxes']),TTC_fact_avant)

        mdo_var=val_mdo-mdo_fact_avant
        mat_var=val_mat-mat_fact_avant
        #print('valeurs ticket ttc,mdo,mat:',row[0],row[1],row[2])
        TTC_ticket_apres = float(row[0]) + TTC_var
        mdo_ticket_apres=float(row[1]) + mdo_var
        mat_ticket_apres=float(row[2]) + mat_var
    cur.execute("UPDATE tickets SET CoutTotalTTC=%s, CoutMainOeuvre=%s, CoutMateriel=%s WHERE IDTicket=%s AND IDClient=%s",
                (TTC_ticket_apres,mdo_ticket_apres,mat_ticket_apres,int(request.form['id_ticket']),client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_factures.factures_table'))

# affichage de la liste de factures avec 'à partir de'
@bp_factures.route("/afficher_de_date", methods=['POST','GET'])
def afficher_de_date():
    """afficher la page de la table de factures à partir de date spécifiée
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    # # sélectionner enregistrements depuis date demandée
    date = request.form['date_debut']
    if date == '':
        flash('Vous devez sélectionner une date de début.', "warning")
        return redirect(url_for('bp_factures.factures_table'))
    # convertir date en datetime
    date_hre = datetime.strptime(date, "%Y-%m-%d")
    factures_list = []
    cur.execute("SELECT IDFacture,NoFacture,DateSaisie,Fournisseur,MDO_HT,MAT_HT,TotalAvecTx,CpteGL, IDTicket, CheminPath "
                "FROM factures WHERE DateSaisie>%s AND IDClient=%s", (date_hre, client_ident))
    for row in cur.fetchall():
        if row[9] == '' or row[9] == None:
            row += ('non',)
        else:
            row += ('oui',)
        factures_list.append(row)

    return render_template('factures_table.html', factures_list=factures_list, date_debut=date, bd=profile_list[3])

