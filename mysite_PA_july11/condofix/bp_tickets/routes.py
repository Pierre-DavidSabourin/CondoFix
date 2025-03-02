from flask import Blueprint, render_template,session,json,request,redirect,url_for, flash, make_response
import time
import collections
from collections import Counter
from datetime import datetime, date
from mysite_PA_july11.utils import connect_db

bp_tickets = Blueprint('bp_tickets', __name__)

#page de ticket 'en cours'
@bp_tickets.route('/en_cours')
def en_cours():
    """Afficher les tickets en cours dans une table ainsi que les indicateurs de statut selon priorité"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (tous excepté copropriétaires)
    if profile_list[2] > 4:
        return redirect(url_for('bp_admin.permission'))

    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    ticket_priorite_list=[]
    count_prior1=0
    count_prior2=0
    count_prior3=0
    count_prior4=0
    count_tot_encours=0
    cum_jrs_prior1=0
    cum_jrs_prior2=0
    cum_jrs_prior3=0
    cum_jrs_prior4=0
    cum_jrs_encours=0
    moy_jrs_prior1=0
    moy_jrs_prior2=0
    moy_jrs_prior3=0
    moy_jrs_prior4=0
    moy_jrs_encours=0
    cum_hres_estimees=0
    cum_tot_tickets_1 = 0
    cum_tot_tickets_2 = 0
    cum_tot_tickets_3 = 0
    cum_tot_tickets_4 = 0
    cur.execute("SELECT Priorite, DatePrevue, Statut, HeuresEstimees, IDIntervenant FROM tickets "
                "WHERE Statut=%s AND IDClient=%s",(2,client_ident,))
    for row in cur.fetchall():
        ticket_priorite_list.append(row)

    for item in ticket_priorite_list:
        # vérifier si le ticket touche un employé
        cur.execute("SELECT IDTypeIntervenant from intervenants WHERE IDIntervenant=%s", (item[4],))
        for row in cur.fetchall():
            if row[0] == 1:
                cum_hres_estimees=cum_hres_estimees+item[3]

        #calcul du nombre de jours depuis date prévue
        a = item[1]
        b = date.today()
        delta = b - a
        # selon statut, on sépare les bp_tickets
        if item[2] == 2:
            if item[0] == 1:
                cum_tot_tickets_1 += 1
                # éviter de compter les tickets avec une date prévue ultérieure
                if delta.days <= 0:
                    continue
                else:
                    count_prior1 += 1
                    cum_jrs_prior1 = cum_jrs_prior1 + delta.days
            elif item[0] == 2:
                cum_tot_tickets_2 += 1
                # éviter de compter les tickets avec une date prévue ultérieure
                if delta.days <= 0:
                    continue
                else:
                    count_prior2 += 1
                    cum_jrs_prior2 = cum_jrs_prior2 + delta.days
            elif item[0] == 3:
                cum_tot_tickets_3 += 1
                # éviter de compter les tickets avec une date prévue ultérieure
                if delta.days <= 0:
                    continue
                else:
                    count_prior3 += 1
                    cum_jrs_prior3 = cum_jrs_prior3 + delta.days
            elif item[0] == 4:
                cum_tot_tickets_4 += 1
                # éviter de compter les tickets avec une date prévue ultérieure
                if delta.days <= 0:
                    continue
                else:
                    count_prior4 += 1
                    cum_jrs_prior4 = cum_jrs_prior4 + delta.days
            count_tot_encours += 1
            cum_jrs_encours = cum_jrs_encours + delta.days

    if count_prior1!=0:
        moy_jrs_prior1=round(cum_jrs_prior1/count_prior1,1)
    if count_prior2!=0:
        moy_jrs_prior2=round(cum_jrs_prior2/count_prior2,1)
    if count_prior3!=0:
        moy_jrs_prior3=round(cum_jrs_prior3/count_prior3,1)
    if count_prior4!=0:
        moy_jrs_prior4=round(cum_jrs_prior4/count_prior4,1)
    if count_tot_encours!=0:
        moy_jrs_encours=int(cum_jrs_encours/count_tot_encours)

    indicateurs=[cum_tot_tickets_1,moy_jrs_prior1,cum_tot_tickets_2,moy_jrs_prior2,cum_tot_tickets_3,moy_jrs_prior3,cum_tot_tickets_4,
                 moy_jrs_prior4,moy_jrs_encours,count_tot_encours, int(cum_hres_estimees)]

    # traitement pour obtenir les données pour le tableau dynamique
    IntervenantNom=str()
    TypeInterv=int()
    Desc_priorite=str()
    ticket_list=[]
    ticket_list_cell = []
    cur.execute("SELECT IDTicket, IDClient,IDUsager,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, "
                "HeuresEstimees, HeuresRequises, TypeTravail FROM tickets WHERE Statut=%s AND IDClient=%s",(2,client_ident,))
    for row in cur.fetchall():
        cur.execute("SELECT NomIntervenant, IDTypeIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",(row[3],client_ident,))
        for item in cur.fetchall():
            IntervenantNom=item[0]
            TypeInterv=item[1]
        row+=(IntervenantNom,)
        row+=(TypeInterv,)
        cur.execute("SELECT Description FROM priorite WHERE IDPriorite=%s", (row[5],))
        for item_x in cur.fetchall():
            Desc_priorite=item_x[0]
            row+=(Desc_priorite,)
        cur.execute("SELECT Description FROM typetravail WHERE IDTypeTravail=%s", (row[10],))
        for item_y in cur.fetchall():
            Desc_travail = item_y[0]
            row += (Desc_travail,)
        ticket_list.append(row)

        # pour la page simplifiée de l'employé
        contenu=row[0], row[7], row[5],'No. '+str(row[0])+' ('+IntervenantNom+')\n'+str(row[6])+'\n Heures Est/Req:'+' '+str(row[8])+'/'+str(row[9])+'  '+'\n'+str(Desc_priorite)
        ticket_list_cell.append(contenu)
    #print('ticket list cell:',ticket_list_cell)
    # recherche du document ayant l'échéance la plus rapprochée pour affichage
    liste_docs=[]
    cur.execute("SELECT Description, DateProchain FROM documentation WHERE IDClient=%s",(client_ident,))
    for item_y in cur.fetchall():
        if item_y[1]!=None:
            liste_docs.append(item_y)
    liste_docs.sort( key=lambda tup: tup[1])
    if len(liste_docs)>0:
        proch_doc=liste_docs[0]
    else:
        proch_doc=''

    ticket_list.sort(key = lambda x: x[7])
    # 2ème paramètre pour identifier le nom du client actuellement en cours
    # trouver parametre pour affichage des tickets en cours selon type d'usager (employé vs. autres)
    parametre_employe = 0

    cur.execute("SELECT EncoursEmploye FROM parametres WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        if item[0]==1:
            parametre_employe = 1
    cnx.close()
    if profile_list[2]==3 and parametre_employe==1:  #employé
        return render_template('tickets_en_cours_cell.html', ticket_list=ticket_list_cell,indicateurs=indicateurs, bd=profile_list[3])
    else:
        return render_template('tickets_en_cours_table.html', version=version_client, ticket_list=ticket_list,proch_doc=proch_doc,indicateurs=indicateurs,bd=profile_list[3])

#page nouveau ticket
@bp_tickets.route('/nouveau_ticket')
def nouveau_ticket():
    """afficher la page d'ajout de nouveau ticket"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2] > 4:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_intervenants=[]
    cur.execute("SELECT IDIntervenant, NomIntervenant, IDCategorie FROM intervenants WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_intervenants.append(row)
    liste_intervenants.sort(key=lambda tup: tup[1])

    liste_types_travail = []
    cur.execute("SELECT IDTypeTravail, Description FROM typetravail")
    for row in cur.fetchall():
        liste_types_travail.append(row)

    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])

    liste_equipements=[]
    cur.execute("SELECT NumTag, Nom, IDCategorie FROM equipements WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)
    cnx.close()
    list_res_2 = set(map(lambda x:x[2], liste_equipements))
    list_categ_avec_tags=list(list_res_2)

    list_equip = [[(y[0], y[1]) for y in liste_equipements if y[2]==x] for x in list_categ_avec_tags]
    return render_template('ticket_ajout.html',version=version_client, liste_types_travail=liste_types_travail, liste_intervenants=liste_intervenants,list_categ_avec_tags=json.dumps(list_categ_avec_tags),liste_categories=liste_categories,list_equip=json.dumps(list_equip), bd=profile_list[3])


#fonction pour ajouter nouveau ticket et retourner à 'en cours'
@bp_tickets.route('/ajout_ticket', methods=['POST'])
def ajout_ticket():
    """ajout du nouveau ticket dans la base de données mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    # pour tenir compte de checkbox 'aucun tag'
    tag_no=int()
    if request.form.get('aucun_tag')==None:
        if request.form.get('tag')==None:
            tag_no=''
        else:
            tag_no=request.form['tag']
    if request.form.get('aucun_tag')=="1":
        tag_no=''
    if request.form.get('multi_tags')=="on":
        multi_tag=1
    else:
        multi_tag=0
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    args_interv=request.form['intervenant'].replace('(','').replace(')','').split(',')
    id_interv=args_interv[0]

    no_equip=int()
    cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s",(tag_no,client_ident))
    for item in cur.fetchall():
        no_equip=item[0]
    cur.execute('INSERT INTO tickets (IDClient, IDUsager,IDIntervenant, IntervenantAutre, DateCreation, '
                 'Statut, Priorite, TypeTravail, Description_travail, Emplacement, IDCategorie, IDEquipement, '
                 'DatePrevue, HeuresEstimees, HeuresRequises, CoutMainOeuvre, CoutMateriel, CoutTotalTTC, MultiTags) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                 [client_ident, profile_list[1], id_interv, request.form['intervenant_autre'], time.strftime('%Y-%m-%d %H:%M'),
                  "2", request.form['priorite'], request.form['type_travail'], request.form['desc_travail'],
                  request.form['emplacement'],request.form['categorie'],no_equip,
                  request.form['date_prevue'],request.form['hres_est'],0,0,0,0,multi_tag])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_tickets.en_cours',version=version_client))

#fonction pour modifier ticket à partir de page 'tickets en cours'
@bp_tickets.route("/affiche_ticket_en_cours/<id_ticket>")
def affiche_ticket_en_cours(id_ticket):
    """Afficher la page de modification de ticket"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_ticket=[]
    tag_desc=str()
    tag_id=0
    id_categorie=0
    cur.execute("SELECT IDTicket, IDIntervenant, IntervenantAutre, DateCreation,Statut, Priorite, TypeTravail, Description_travail, Emplacement, "
                "IDCategorie, IDEquipement, DatePrevue, HeuresEstimees, HeuresRequises, Nbre_visites, MultiTags  FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row in cur.fetchall():
        if row[10]==None:
            row += ('',)
        else:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",(row[10], client_ident))
            for item in cur.fetchall():
                tag_desc=str(item[0])+', '+item[1]
                tag_id=item[0]
        liste_ticket.append(row)
        id_categorie=row[9]

    liste_intervenants=[]
    cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row_1 in cur.fetchall():
        liste_intervenants.append(row_1)
    liste_intervenants.sort(key=lambda tup: tup[1])

    liste_types_travail = []
    cur.execute("SELECT IDTypeTravail, Description FROM typetravail")
    for row in cur.fetchall():
        liste_types_travail.append(row)

    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    liste_equipements=[]
    liste_equip_en_cours=[]
    equip=str()
    cur.execute("SELECT NumTag, Nom, IDCategorie FROM equipements WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)
        if row[2]==id_categorie:
            liste_equip_en_cours.append(row)
    # pour afficher les tags et descriptions correctement
    liste_equip_actuel = [(y[0], y[1], y[2]) for y in liste_equip_en_cours]

    list_res_2 = set(map(lambda x: x[2], liste_equipements))
    list_categ_avec_tags = list(list_res_2)
    cnx.close()
    list_equip = [[(y[0],y[1]) for y in liste_equipements if y[2] == x] for x in list_categ_avec_tags]
    return render_template('ticket_modif_en_cours.html', version=version_client, liste_ticket=liste_ticket[0], liste_intervenants=liste_intervenants,
                           list_categ_avec_tags=json.dumps(list_categ_avec_tags), liste_categories=liste_categories,
                           liste_types_travail=liste_types_travail, list_equip=json.dumps(list_equip), liste_equip_en_cours=liste_equip_actuel,  tag_desc=tag_desc, tag_id=tag_id, bd=profile_list[3])


@bp_tickets.route('/modifier_ticket_en_cours/<id_ticket>', methods=['POST'])
def modifier_ticket_en_cours (id_ticket):
    """Modification du ticket dans la base de données"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 4:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    tag_no = 0
    id_categorie = int()
    # pour tenir compte de checkbox 'aucun tag'
    if request.form.get('aucun_tag')==None:
        if request.form.get('tag')==None:
            tag_no=0
        else:
            tag_no=request.form['tag']
    if request.form.get('aucun_tag')=="1":
        tag_no=0
    if request.form.get('multi_tag')=="on":
        multi_tag=1
    else:
        multi_tag=0

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    no_equip = int()
    cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s", (tag_no, client_ident))
    for item in cur.fetchall():
        no_equip = item[0]

    # # pour s'assurer que la catégorie corresponde au tag sélectionné s'il y a lieu
    # if tag_no==0:
    #     id_categorie=request.form['categorie']
    # else:
    #     cur.execute("SELECT IDCategorie from equipements WHERE IDEquipement=%s AND IDClient=%s",(tag_no,client_ident))
    #     for item in cur.fetchall():
    #         id_categorie=item[0]
    if request.form['hres_req']=='':
        hres_req=0
    else:
        hres_req=request.form['hres_req']
    if request.form['visites_req']=='':
        visites_req=0
    else:
        visites_req=request.form['visites_req']

    cur.execute("UPDATE tickets SET IDIntervenant=%s, IntervenantAutre=%s,Priorite=%s, TypeTravail=%s, Statut=%s, Description_travail=%s, Emplacement=%s,"
                " IDCategorie=%s, IDEquipement=%s, DatePrevue=%s, HeuresEstimees=%s, HeuresRequises=%s, Nbre_visites=%s, MultiTags=%s  WHERE IDTicket=%s AND IDClient=%s",
                [request.form['intervenant'],request.form['intervenant_autre']  ,request.form['priorite'], request.form['type_travail'],
                 2, request.form['desc_travail'],request.form['emplacement'],request.form['categorie'],no_equip,
                 request.form['date_prevue'],request.form['hres_est'],hres_req,visites_req,multi_tag, id_ticket,client_ident])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_tickets.en_cours',version=version_client))

#fonction pour modifier ticket à partir de page 'tickets en attente'
@bp_tickets.route("/affiche_ticket_en_attente/<id_ticket>")
def affiche_ticket_en_attente(id_ticket):
    """Afficher les tickets ayant le statut 'en attente' (complétés mais pas de facture encore attribuée)"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_ticket = []
    tag_desc = str()
    tag_id = 0
    id_categorie = 0
    cur.execute(
        "SELECT IDTicket, IDIntervenant, IntervenantAutre, DateCreation,Statut, Priorite, TypeTravail, Description_travail, Emplacement, "
        "IDCategorie, IDEquipement, DatePrevue, HeuresEstimees, HeuresRequises, Nbre_visites, DateComplet, MultiTags  FROM tickets WHERE IDTicket=%s AND IDClient=%s",
        (id_ticket, client_ident))
    for row in cur.fetchall():
        if row[10] == None:
            row += ('',)
        else:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",
                        (row[10], client_ident))
            for item in cur.fetchall():
                tag_desc = str(item[0]) + ', ' + item[1]
                tag_id = item[0]
        liste_ticket.append(row)
        id_categorie = row[9]

    liste_intervenants = []
    cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row_1 in cur.fetchall():
        liste_intervenants.append(row_1)
    liste_intervenants.sort(key=lambda tup: tup[1])

    liste_types_travail = []
    cur.execute("SELECT IDTypeTravail, Description FROM typetravail")
    for row in cur.fetchall():
        liste_types_travail.append(row)

    liste_categories = []
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    liste_equipements = []
    liste_equip_en_cours = []
    equip = str()
    cur.execute("SELECT NumTag, Nom, IDCategorie FROM equipements WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)
        if row[2] == id_categorie:
            liste_equip_en_cours.append(row)
    # pour afficher les tags et descriptions correctement
    liste_equip_actuel = [(y[0], y[1], y[2]) for y in liste_equip_en_cours]

    list_res_2 = set(map(lambda x: x[2], liste_equipements))
    list_categ_avec_tags = list(list_res_2)
    cnx.close()
    list_equip = [[(y[0], y[1]) for y in liste_equipements if y[2] == x] for x in list_categ_avec_tags]

    return render_template('ticket_modif_en_attente.html', version=version_client, liste_ticket=liste_ticket[0],
                           liste_intervenants=liste_intervenants,
                           list_categ_avec_tags=json.dumps(list_categ_avec_tags), liste_categories=liste_categories,
                           list_equip=json.dumps(list_equip), liste_equip_en_cours=liste_equip_actuel,
                           liste_types_travail=liste_types_travail, tag_desc=tag_desc, tag_id=tag_id, bd=profile_list[3])

@bp_tickets.route('/modifier_ticket_en_attente/<id_ticket>', methods=['POST'])
def modifier_ticket_en_attente (id_ticket):
    """Afficher la page de modification du ticket pour y ajouter les infos concernant les factures."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    # pour tenir compte de checkbox 'aucun tag'
    tag_no=0
    id_categorie = int()
    # pour tenir compte de checkbox 'aucun tag'
    if request.form.get('aucun_tag') == None:
        if request.form.get('tag') == None:
            tag_no = 0
        else:
            tag_no = request.form['tag']
    if request.form.get('aucun_tag') == "1":
        tag_no = 0
    if request.form.get('multi_tag') == "on":
        multi_tag = 1
    else:
        multi_tag = 0

    no_equip = int()
    cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s", (tag_no, client_ident))
    for item in cur.fetchall():
        no_equip = item[0]

    if request.form['hres_req'] == '':
        hres_req = 0
    else:
        hres_req = request.form['hres_req']
    if request.form['visites_req'] == '':
        visites_req = 0
    else:
        visites_req = request.form['visites_req']

    cur.execute(
        "UPDATE tickets SET IDIntervenant=%s, IntervenantAutre=%s,Priorite=%s, TypeTravail=%s, Description_travail=%s, Emplacement=%s,"
        " IDCategorie=%s, IDEquipement=%s, DatePrevue=%s, HeuresEstimees=%s, HeuresRequises=%s, Nbre_visites=%s, DateComplet=%s, MultiTags=%s  WHERE IDTicket=%s AND IDClient=%s",
        [request.form['intervenant'], request.form['intervenant_autre'], request.form['priorite'],
         request.form['type_travail'], request.form['desc_travail'], request.form['emplacement'], request.form['categorie'], no_equip,
         request.form['date_prevue'], request.form['hres_est'], hres_req, visites_req, request.form['date_complete'], multi_tag, id_ticket,
         client_ident])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_factures.attente_facture', version=version_client))

#fonction pour supprimer ticket
@bp_tickets.route("/supprimer_ticket/<id_ticket>", methods=['POST'])
def supprimer_ticket(id_ticket):
    """Supprimer un ticket de la base de données."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("DELETE FROM tickets WHERE IDTicket=%s AND IDClient=%s",(id_ticket,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for("bp_tickets.en_cours", version=version_client))

#page de recherche de ticket
@bp_tickets.route("/recherche_tickets")
def recherche_tickets():
    """Afficher la page avec les critères pour la recherche de tickets."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 4:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_intervenants=[]
    cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_intervenants.append(row)
    liste_intervenants.sort(key=lambda tup: tup[1])
    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    cnx.close()
    return render_template('ticket_recherche.html', version=version_client, liste_intervenants=liste_intervenants,liste_categories=liste_categories,bd=profile_list[3])

#page de résultat de recherche de bp_tickets
@bp_tickets.route("/resultat_tickets", methods=['GET','POST'])
def resultat_tickets():
    """Afficher la page avec la table des tickets trouvés après la recherche ainsi qu'une fonction d'export."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    ticket_list = []
    # vérifier si plus d'un critère de recherche
    nb_criteres=0
    if request.form['ID_Ticket']!='':
        nb_criteres+=1
    if request.form['intervenant']!='Intervenant':
        nb_criteres+=1
    if request.form['date_debut'] !='':
        nb_criteres+=1
    if request.form['categorie'] !="Catégorie":
        nb_criteres+=1

    # selon version
    if version_client==1:
        if request.form['tag'] !='':
            nb_criteres+=1
    if nb_criteres>1:
        flash("Veuillez sélectionner SEULEMENT un champ de recherche.","warning")
        return redirect(url_for('bp_tickets.recherche_tickets'))
    if nb_criteres==0:
        flash('Vous devez sélectionner au moins un champ de recherche.')
        return redirect(url_for('bp_tickets.recherche_tickets'))

    if request.form['ID_Ticket']!='':
        cur.execute("SELECT IDTicket,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, IDCategorie, "
                    "IDEquipement, HeuresRequises, NoFacture, CoutMainOeuvre, CoutMateriel, CoutTotalTTC, "
                    "IntervenantAutre, DateComplet, HeuresEstimees, IDUsager, TypeTravail, Emplacement "
                    "FROM tickets WHERE IDTicket=%s AND IDClient=%s", (request.form['ID_Ticket'],client_ident))
    elif request.form['intervenant']!='Intervenant':
        cur.execute("SELECT IDTicket,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, IDCategorie, "
                    "IDEquipement, HeuresRequises, NoFacture, CoutMainOeuvre, CoutMateriel, CoutTotalTTC,"
                    "IntervenantAutre, DateComplet, HeuresEstimees, IDUsager, TypeTravail, Emplacement"
                    " FROM tickets WHERE IDIntervenant=%s AND IDClient=%s", (request.form['intervenant'],client_ident))
    elif request.form['date_debut'] !='':
        if request.form['date_fin'] =='':
            flash('Vous devez sélectionner une date de fin pour la recherche.')
            return redirect(url_for('bp_tickets.recherche_tickets'))
        cur.execute("SELECT IDTicket,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, IDCategorie, "
                    "IDEquipement, HeuresRequises, NoFacture, CoutMainOeuvre, CoutMateriel, CoutTotalTTC,"
                    " IntervenantAutre, DateComplet, HeuresEstimees, IDUsager, TypeTravail, Emplacement"
                    " FROM tickets WHERE DatePrevue BETWEEN %s AND %s AND IDClient=%s", (request.form['date_debut'], request.form['date_fin'],client_ident))
    elif request.form['categorie'] !="Catégorie":
        cur.execute("SELECT IDTicket,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, IDCategorie, "
                    "IDEquipement, HeuresRequises, NoFacture, CoutMainOeuvre, CoutMateriel, CoutTotalTTC,"
                    "IntervenantAutre, DateComplet, HeuresEstimees, IDUsager, TypeTravail, Emplacement"
                    " FROM tickets WHERE IDCategorie=%s AND IDClient=%s", (request.form['categorie'],client_ident))
    else:
        # selon version
        if version_client == 1:
            if request.form['tag'] !='':
                id_equip=int()
                cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s",(request.form['tag'],client_ident))
                for item in cur.fetchall():
                    id_equip=int(item[0])
                if id_equip ==0:
                    # rendre impossible de trouver un enregistrement
                    id_equip=99999999999
                cur.execute("SELECT IDTicket,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, IDCategorie, "
                            "IDEquipement, HeuresRequises, NoFacture, CoutMainOeuvre, CoutMateriel, CoutTotalTTC, "
                            "IntervenantAutre, DateComplet, HeuresEstimees, IDUsager, TypeTravail, Emplacement"
                            " FROM tickets WHERE IDEquipement=%s AND IDClient=%s", (id_equip,client_ident))
    for row in cur.fetchall():
        IntervenantNom=str()
        if row[1] == None or row[1] == '':
            IntervenantNom= 'Nil'
        else:
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s", (row[1],client_ident))
            for item in cur.fetchall():
                IntervenantNom=item[0]
        row+=(IntervenantNom,)#19
        cur.execute("SELECT Description FROM statut WHERE IDStatut=%s", (row[2],))
        for item_x in cur.fetchall():
            Desc_statut=item_x[0]
            row+=(Desc_statut,)#20
        cur.execute("SELECT Description FROM priorite WHERE IDPriorite=%s", (row[3],))
        for item_y in cur.fetchall():
            Desc_priorite=item_y[0]
            row+=(Desc_priorite,)#22
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s", (row[6],client_ident))
        for item_z in cur.fetchall():
            Desc_categorie=item_z[0]
            row+=(Desc_categorie,)#23
        cur.execute("SELECT Description FROM typetravail WHERE IDTypeTravail=%s", (row[17],))
        for item_z_1 in cur.fetchall():
            Desc_type_travail = item_z_1[0]
            row += (Desc_type_travail,)#24
        # selon version
        if version_client == 1:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s", (row[7],client_ident))
            for item_z1 in cur.fetchall():
                no_tag = item_z1[0]
                row += (no_tag,)#24
                desc = item_z1[1]
                row += (desc,)#25
        ticket_list.append(row)
    print(ticket_list)
    cnx.close()
    #tri par date prévue
    ticket_list.sort(key = lambda x: x[5], reverse=True)
    return render_template('tickets_resultat.html', version=version_client, ticket_list=ticket_list,bd=profile_list[3])

#fonction pour changer statut à 'complété'
@bp_tickets.route('/completer_ticket/<id_ticket>', methods=['POST','GET'])
def completer_ticket(id_ticket):
    """Changer le statut d'un ticket à 'complété' à l'aide d'un bouton de la table de tickets en cours."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT HeuresEstimees FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row in cur.fetchall():
        if row[0]==0:
            return render_template('ticket_incomplet.html',bd=profile_list[3])
    #tous les bp_tickets complétés sont mis en attente de facture
    #pour tenir compte d'achat de matériel par le concierge et permettre une évaluation
    statut=3
    date_complete=time.strftime('%Y-%m-%d')
    cur.execute("UPDATE tickets SET Statut = %s, DateComplet= %s WHERE IDTicket = %s AND IDClient=%s", (statut, date_complete, id_ticket,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for("bp_tickets.en_cours", version=version_client))

@bp_tickets.route('/ferme_ticket/<id_ticket>', methods=['POST','GET'])
def ferme_ticket(id_ticket):
    """Changer le statut d'un ticket à 'fermé' à l'aide d'un bouton de la table de tickets en cours."""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    # global date_ferme
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    date_ferme=time.strftime('%Y-%m-%d')
    statut= 4    #ticket fermé
    cur.execute("UPDATE tickets SET DateFermeture=%s, Statut = %s WHERE IDTicket = %s  AND IDClient=%s", (date_ferme, statut, id_ticket,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for("bp_factures.attente_facture", version=version_client))

#page de ticket 'en cours' pour les gestionnaires ayant de multiples clients
@bp_tickets.route('/en_cours_multi')
def en_cours_multi():
    """Afficher les tickets en cours dans une table ainsi que les indicateurs de statut selon priorité"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (tous excepté copropriétaires)
    if profile_list[2] > 4:
        return redirect(url_for('bp_admin.permission'))

    #calcul des indicateurs par priorité
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    ticket_priorite_list=[]
    count_prior1=0
    count_prior2=0
    count_prior3=0
    count_prior4=0
    count_tot_encours=0
    cum_jrs_prior1=0
    cum_jrs_prior2=0
    cum_jrs_prior3=0
    cum_jrs_prior4=0
    cum_jrs_encours=0
    moy_jrs_prior1=0
    moy_jrs_prior2=0
    moy_jrs_prior3=0
    moy_jrs_prior4=0
    moy_jrs_encours=0

    liste_clients = [1,2,3]

    # list_tup = tuple(liste_clients)
    #
    # params = {'list_tup': list_tup}

    #cursor.execute('SELECT * FROM table where id in %(list_tup)s',params)


    cur.execute("SELECT Priorite, DateCreation, Statut FROM tickets "
                "WHERE Statut=2 AND IDClient in (%s)" % ",".join(map(str,liste_clients)))
    for row in cur.fetchall():
        ticket_priorite_list.append(row)

    for item in ticket_priorite_list:
        #calcul du nombre de jours depuis création
        a = item[1]
        b = date.today()
        delta = b - a
        #selon statut, on sépare les bp_tickets
        if item[2]==2:
            if item[0]==1:
                count_prior1+=1
                cum_jrs_prior1=cum_jrs_prior1+delta.days
            elif item[0]==2:
                count_prior2+=1
                cum_jrs_prior2=cum_jrs_prior2+delta.days
            elif item[0]==3:
                count_prior3+=1
                cum_jrs_prior3=cum_jrs_prior3+delta.days
            elif item[0]==4:
                count_prior4+=1
                cum_jrs_prior4=cum_jrs_prior4+delta.days
            count_tot_encours+=1
            cum_jrs_encours=cum_jrs_encours+delta.days

    if count_prior1!=0:
        moy_jrs_prior1=round(cum_jrs_prior1/count_prior1,1)
    if count_prior2!=0:
        moy_jrs_prior2=round(cum_jrs_prior2/count_prior2,1)
    if count_prior3!=0:
        moy_jrs_prior3=round(cum_jrs_prior3/count_prior3,1)
    if count_prior4!=0:
        moy_jrs_prior4=round(cum_jrs_prior4/count_prior4,1)
    if count_tot_encours!=0:
        moy_jrs_encours=int(cum_jrs_encours/count_tot_encours)

    indicateurs=[count_prior1,moy_jrs_prior1,count_prior2,moy_jrs_prior2,count_prior3,moy_jrs_prior3,count_prior4,
                 moy_jrs_prior4,moy_jrs_encours,count_tot_encours]
    IntervenantNom=str()
    TypeInterv=int()
    Desc_priorite=str()
    ticket_list=[]
    liste_clients=[2,]
    cur.execute("SELECT IDTicket, IDClient,IDUsager,IDIntervenant, Statut, Priorite, Description_travail, DatePrevue, HeuresEstimees, "
                "HeuresRequises FROM tickets WHERE Statut=2 AND IDClient IN (%s)" % ",".join(map(str,liste_clients)))
    for row in cur.fetchall():
        cur.execute("SELECT NomIntervenant, IDTypeIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",(row[3],client_ident,))
        for item in cur.fetchall():
            IntervenantNom=item[0]
            TypeInterv=item[1]
        row+=(IntervenantNom,)
        row+=(TypeInterv,)
        cur.execute("SELECT Description FROM priorite WHERE IDPriorite=%s", (row[5],))
        for item_x in cur.fetchall():
            Desc_priorite=item_x
            row+=(Desc_priorite)
        # trouver nom des clients pour affichage
        if row[1]==1:
            row+=('Urbano',)
        if row[1]==2:
            row+=('Montana',)
        if row[1]==3:
            row+=('Merici',)
        ticket_list.append(row)
    # recherche du document ayant l'échéance la plus rapprochée pour affichage
    liste_docs=[]
    cur.execute("SELECT Description, DateProchain FROM documentation WHERE IDClient=%s",(client_ident,))
    for item_y in cur.fetchall():
        if item_y[1]!=None:
            liste_docs.append(item_y)
    liste_docs.sort( key=lambda tup: tup[1])
    proch_doc=liste_docs[0]
    cnx.close()
    ticket_list.sort(key = lambda x: x[7])
    # 2ème paramètre pour identifier le nom du client actuellement en cours
    return render_template('tickets_en_cours_table_multi.html',version=version_client,ticket_list=ticket_list,proch_doc=proch_doc,indicateurs=indicateurs,bd=profile_list[3])


# duplication de ticket lorsque 'multitags'
@bp_tickets.route('/dupliquer_en_attente/<id_ticket>', methods=['POST','GET'])
def dupliquer_en_attente(id_ticket):
    """ajout du nouveau ticket identique à l'original dans la base de données mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("INSERT INTO tickets SELECT Null, IDClient, IDUsager,IDSignalement,IDIntervenant,IntervenantAutre, DateCreation, "
                "Statut, Priorite, TypeTravail, Description_travail, Emplacement, IDCategorie, IDEquipement, MultiTags, "
                "DatePrevue, DateComplet, HeuresEstimees, HeuresRequises, Nbre_visites, 0, Null, 0, 0, 0, 0 FROM tickets WHERE IDTicket=%s",(id_ticket,))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_factures.attente_facture', version=version_client))

# tableau dynamique de d'historique des travaux d'entretien
@bp_tickets.route('/histo/<mode>', methods=['POST','GET'])
def histo(mode):
    """Recherche et affichage des tickets >1000$ ou selon paramètre de l'usager"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    version_client = profile_list[6]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # ************ traitement du tableau dynamique de l'historique ****************
    ticket_list = []
    if mode=='initialiser':
        montant_min=1000
    else:
        montant_min=request.form['montant_min']
    cur.execute(
        "SELECT DateComplet, IDCategorie, Description_travail, IDEquipement, IDIntervenant, CoutTotalTTC, Emplacement, IDTicket, NoFacture, TypeTravail "
        "FROM tickets WHERE Statut=4 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        cout_tot=row[5]
        # on élimine les tickets en bas de 1000$
        if cout_tot is not None:
            if int(cout_tot) < int(montant_min):
                continue
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s",
                    (row[1], client_ident,))
        CategorieNom = str()
        for item in cur.fetchall():
            CategorieNom = item[0]
        row += (CategorieNom,)

        IntervenantNom = str()
        cur.execute(
            "SELECT NomIntervenant, IDTypeIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
            (row[4], client_ident,))
        for item_1 in cur.fetchall():
            IntervenantNom = item_1[0]
        row += (IntervenantNom,)

        if row[3] == None or row[3] == '':
            row += ('',)
        else:
            cur.execute("SELECT Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",
                        (row[3], client_ident,))
            Desc_equip = str()
            for item_2 in cur.fetchall():
                Desc_equip = item_2[0]
            row += ('no. ' + str(row[3]) + ', ' + str(Desc_equip),)
        cur.execute("SELECT Description FROM typetravail WHERE IDTypeTravail=%s", (row[9],))
        for item_3 in cur.fetchall():
            Desc_travail = item_3[0]
            row += (Desc_travail,)
        ticket_list.append(row)
        ticket_list.sort(key=lambda x: x[0])

    # ************ traitement des graphiques ****************
    cur.execute("SELECT DateComplet, IDCategorie, CoutTotalTTC FROM tickets WHERE Statut=4 AND IDClient=%s", (client_ident,))
    cum_tickets_tot=0
    cum_cout_tot=0
    cum_0=0
    cum_moins_250=0
    cum_250_1000 = 0
    cum_1000_5000=0
    cum_plus_5000=0
    liste_annuelle=[]
    liste_categories=[]
    liste_groupe_cout=[]
    for row in cur.fetchall():
        # graphique par année
        annee=str(row[0].year)
        ajout_1=(annee,row[2])
        liste_annuelle.append(ajout_1)
        # graphique par catégorie
        ajout_2=(row[1],row[2])
        liste_categories.append(ajout_2)
        # graphique par cout total des tickets (groupés)
        if row[2] == 0:
            cum_0 += 1
        if 0 < row[2] < 250:
            cum_moins_250 +=1
        elif 249.99 <= row[2] < 1000:
            cum_250_1000 +=1
        elif 999.99 < row[2] < 5000:
            cum_1000_5000 +=1
        elif row[2] >= 5000:
            cum_plus_5000 +=1

        cum_tickets_tot +=1
        cum_cout_tot += row[2]

    totals_1 = {}
    for uid, x in liste_annuelle:
        if uid not in totals_1:
            totals_1[uid] = x
        else:
            totals_1[uid] += x
    liste_annuelle_triee=sorted(totals_1.items(), key=lambda x: x[0], reverse=False)
    liste_etiq_annees=[]
    liste_dep_annuelles=[]
    for item in liste_annuelle_triee:
        liste_etiq_annees.append(item[0])
        liste_dep_annuelles.append(int(item[1]))
    totals_2 = {}
    for uid, x in liste_categories:
        if uid not in totals_2:
            totals_2[uid] = x
        else:
            totals_2[uid] += x
    liste_categories_triee = sorted(totals_2.items(), key=lambda x: x[1], reverse=True)
    liste_etiq_categories=[]
    liste_dep_categories=[]
    i=0
    for item in liste_categories_triee:
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s",(item[0],client_ident))
        for res in cur.fetchone():
            liste_etiq_categories.append(res)
        liste_dep_categories.append(int(item[1]))
        i+=1
        if i==10:
            break

    cnx.close()
    tot_dep_globales=int(cum_cout_tot)
    liste_etiq_groupe_brut='0$,Moins de 250$,250 à 1000$,1000 à 5000$,Plus de 5000$'
    liste_etiq_groupe=liste_etiq_groupe_brut.split(',')
    liste_nbre_groupe=[cum_0, cum_moins_250, cum_250_1000, cum_1000_5000, cum_plus_5000]
    return render_template('historique_new.html', version=version_client, labels_annees=liste_etiq_annees, dep_annuelles=liste_dep_annuelles,
                           labels_pie=liste_etiq_categories, depenses_pie=liste_dep_categories, cum_dep_globales=tot_dep_globales,tot_tickets=cum_tickets_tot,
                           labels_groupes=liste_etiq_groupe,nombre_groupes=liste_nbre_groupe,fill_histo=ticket_list, montant_min=montant_min, bd=profile_list[3])

#page de saisie de facture avec ocr et création de ticket simultanée
@bp_tickets.route('/facture_ocr')
def facture_ocr():
    """À partir de facture importée dans CondoFix, remplir les champs du ticket"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (tous excepté copropriétaires)
    if profile_list[2] > 4:
        return redirect(url_for('bp_admin.permission'))
    return render_template('facture_ocr_ajout.html')