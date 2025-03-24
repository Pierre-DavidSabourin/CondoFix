from flask import Flask, render_template, session, Blueprint, redirect,url_for
import collections
from collections import Counter
import mysql.connector
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from utils import connect_db
import traceback

import matplotlib
matplotlib.use('Agg')#pour éviter que le retour au tableau de bord cause une erreur
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
import matplotlib.ticker as mtick

bp_tableaux_bord = Blueprint('bp_tableaux_bord', __name__)


#********************TABLEAU DE BORD****************************************
#page tableau de bord
#graphique par année de remplacement, par priorité en cours, par intervenant
#durant année budgétaire en cours, bp_tickets par équipement, dépenses vs. budget

# futur tableau de carnet d'entretien pour les copropriétaires
# tableau dynamique de d'historique des travaux d'entretien (1000$ et plus)
@bp_tableaux_bord.route('/histo_proprios')
def histo_proprios():
    """Recherche et affichage des tickets >1000$"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode_connexion=profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    ticket_list=[]
    cur.execute("SELECT DatePrevue, IDCategorie, Description_travail, IDEquipement, IDIntervenant, CoutMainOeuvre, CoutMateriel, Statut "
                "FROM tickets WHERE Statut=4 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        tot=0
        if row[5]!=None:
            tot=row[5]
        else:
            tot=0
        if row[6]!=None:
            tot=tot+row[6]
        else:
            tot=tot+0
        tot_travaux=int(tot*1.1475)
        row+=(tot_travaux,)
        # on élimine les tickets en bas de 1000$
        if tot_travaux<1000:
            continue
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s",(row[1],client_ident,))
        CategorieNom=str()
        for item in cur.fetchall():
            CategorieNom=item[0]
        row+=(CategorieNom,)
        IntervenantNom=str()
        cur.execute("SELECT NomIntervenant, IDTypeIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",(row[4],client_ident,))
        for item_1 in cur.fetchall():
            IntervenantNom=item_1[0]
        row+=(IntervenantNom,)

        if row[3]==None or row[3]=='':
            row+=('',)
        else:
            cur.execute("SELECT Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s", (row[3],client_ident,))
            Desc_equip=str()
            for item_2 in cur.fetchall():
                Desc_equip=item_2[0]
            row+=('no. '+row[3]+', '+Desc_equip,)
        ticket_list.append(row)
    cnx.close()
    ticket_list.sort(key = lambda x: x[0])
    # mémoriser 2 _images statiques ou 2 graphiques des dépenses vs. budgets
    image_a="../static/Budget.png"
    image_b="../static/Categories.png"

    return render_template('histo_proprios.html',fill_histo=ticket_list,image_1=image_a, image_2=image_b, bd=profile_list[3])

# page de suivi de budget pour copropriétaires
# inclut graphique de dépenses mensuelles vs. budget, graphique des 10 catégories les plus actives et

@bp_tableaux_bord.route('/budget_proprios')
def budget_proprios():
    """ Page de suivi de budget pour copropriétaires inclut:

    * graphique de dépenses mensuelles vs. budget
    * graphique des 10 catégories les plus actives
    """
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    ytd_pourcent=0
    labels_10 = []
    records_10 = []
    budgets_10=[]
    labels_mois=[]
    budget_list= []
    list_cum_rep = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    list_cum_prev = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    try:
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        date_annee_cour=date.today()

        # ***************** Activité par catégorie d'équipement histogramme******************************

        # trouver la date du début d'année fiscale budgétaire
        cur.execute("SELECT DateDebutBudget FROM parametres WHERE IDClient=%s",(client_ident,))
        for item in cur.fetchall():
            date_annee_cour=item[0]

        #calculer avancement sur année budgétaire
        a = date_annee_cour
        b = date.today()
        delta = b - a
        days_ytd=delta.days
        ytd_pourcent=str(round(int(days_ytd*100/365)))+'%'

        #trouver budget pour chaque catégorie
        cur.execute("SELECT IDCategorie,Description,BudgetAnnuel FROM categories WHERE Actif=%s AND IDClient=%s", (1, client_ident))
        categ_list=[]
        for row in cur.fetchall():
            #listes en ordre de catégorie dont IDCategorie=1 sera budget_list[0]
            categ_list.append(row)

        #trouver tickets selon année courante et statut>2
        ticket_list=[]
        IDCateg_list_tickets=[]
        cur.execute("SELECT IDCategorie, CoutTotalTTC, Statut, DateComplet, TypeTravail FROM tickets "
                    "WHERE Statut>2 AND DateComplet > %s AND TypeTravail IN ('1','3') AND IDClient=%s",
                    (date_annee_cour, client_ident))
        for row_1 in cur.fetchall():
            for item in categ_list:
                if item[0] == row_1[0]:
                    IDCateg_list_tickets.append(row_1[0])
                    ticket_list.append(row_1)
        # s'assurer que les 4 catégories liées au salaires sont dans la liste
        if 8 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(8)
        if 17 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(17)
        if 20 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(20)
        if 21 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(21)
        salaires_tot=0
        # trouver les salaires par catégorie
        list_salaires_categ=[]
        cur.execute("SELECT SalairesTotal, PartCateg_8, PartCateg_17, PartCateg_20, PartCateg_21 FROM parametres "
                    "WHERE IDClient=%s",(client_ident,))
        for row in cur.fetchall():
            salaires_tot=row[0]
            list_salaires_categ.append(row)

        #compter le nombre de tickets par catégorie: ex. IDCateg:nbre tickets
        res_count_numeros=Counter(IDCateg_list_tickets)
        unique_cat_list_numeros=list(res_count_numeros)
        budgets=[]
        labels=[]
        records=[]

        for item in unique_cat_list_numeros:
            for item_1 in categ_list:
                if item_1[0]==item:
                    label_contenu=item_1[1]+'('+str(res_count_numeros[item])+')'
                    labels.append(label_contenu)
                    if item_1[2] is None or item_1[2]=='None':
                        budgets.append(0)
                    elif item_1[2]=='':
                        budgets.append(0)
                    else:
                        budgets.append(int(item_1[2]))
            cum_dep=0

            for i in ticket_list:
                if i[0]==item:
                    cum_dep=cum_dep+i[1]

            #ajout des salaires pour catégories (8,17,20,21)
            salaires=0
            if item==8:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][1]/100)*days_ytd/365
            elif item==17:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][2]/100)*days_ytd/365
            elif item==20:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][3]/100)*days_ytd/365
            elif item==21:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][4]/100)*days_ytd/365
            cum_dep=cum_dep+int(salaires)
            records.append(int(cum_dep))

        # trier les trois listes en même temps basé sur les dépenses (records) en ordre décroissant
        zipped_list=zip(records,budgets,labels)
        liste_triee=sorted(zipped_list,key=None, reverse=True)

        #choisir les 10 premières catégories (plus de dépenses)
        records_10=[i[0] for i in liste_triee[0:10]]
        budgets_10=[i[1] for i in liste_triee[0:10]]
        labels_10=[i[2] for i in liste_triee[0:10]]

        # *************** Graphique des dépenses année à date *********************************

        # trouver le total du budget en cours et diviser par mois
        tot_budget = 0
        budget_list = []
        cum_budget = 0
        budget_mensuel = 0
        cur.execute("SELECT BudgetAnnuel FROM categories WHERE IDClient=%s", (client_ident,))
        for row in cur.fetchall():
            if row[0] != None:
                tot_budget += row[0]
        if tot_budget != 0:
            budget_mensuel = tot_budget / 12
        for i in range(12):
            cum_budget = cum_budget + budget_mensuel
            val_mois = int(cum_budget)
            budget_list.append(val_mois)
        cnx.close()

        # cumul dépenses pour entretien et réparations
        Dep_janv_r = 0
        Dep_fev_r = 0
        Dep_mars_r = 0
        Dep_avril_r = 0
        Dep_mai_r = 0
        Dep_juin_r = 0
        Dep_juil_r = 0
        Dep_aout_r = 0
        Dep_sept_r = 0
        Dep_oct_r = 0
        Dep_nov_r = 0
        Dep_dec_r = 0
        # cumul dépenses pour préventif
        Dep_janv_p = 0
        Dep_fev_p = 0
        Dep_mars_p = 0
        Dep_avril_p = 0
        Dep_mai_p = 0
        Dep_juin_p = 0
        Dep_juil_p = 0
        Dep_aout_p = 0
        Dep_sept_p = 0
        Dep_oct_p = 0
        Dep_nov_p = 0
        Dep_dec_p = 0
        rep = 0
        prev = 0

        for item in ticket_list:
            date_complete = item[3]
            if item[4] == 1:
                rep = int(item[1])
            else:
                rep=0
            if item[4] == 3:
                prev= int(item[1])
            else:
                prev = 0
            # cumuler les dépenses selon le mois
            if date_complete.month == 1:  # janvier
                if item[4] == 1:  # réparation
                    Dep_janv_r += rep
                elif item[4] == 3:  # préventif
                    Dep_janv_p += prev
            if date_complete.month == 2:  # février
                if item[4] == 1:  # réparation
                    Dep_fev_r += rep
                elif item[4] == 3:  # préventif
                    Dep_fev_p += prev
            if date_complete.month == 3:  # mars
                if item[4] == 1:  # réparation
                    Dep_mars_r += rep
                elif item[4] == 3:  # préventif
                    Dep_mars_p += prev
            if date_complete.month == 4:  # avril
                if item[4] == 1:  # réparation
                    Dep_avril_r += rep
                elif item[4] == 3:  # préventif
                    Dep_avril_p += prev
            if date_complete.month == 5:  # mai
                if item[4] == 1:  # réparation
                    Dep_mai_r += rep
                elif item[4] == 3:  # préventif
                    Dep_mai_p += prev
            if date_complete.month == 6:  # juin
                if item[4] == 1:  # réparation
                    Dep_juin_r += rep
                elif item[4] == 3:  # préventif
                    Dep_juin_p += prev
            if date_complete.month == 7:  # juillet
                if item[4] == 1:  # réparation
                    Dep_juil_r += rep
                elif item[4] == 3:  # préventif
                    Dep_juil_p += prev
            if date_complete.month == 8:  # aout
                if item[4] == 1:  # réparation
                    Dep_aout_r += rep
                elif item[4] == 3:  # préventif
                    Dep_aout_p += prev
            if date_complete.month == 9:  # septembre
                if item[4] == 1:  # réparation
                    Dep_sept_r += rep
                elif item[4] == 3:  # préventif
                    Dep_sept_p += prev
            if date_complete.month == 10:  # octobre
                if item[4] == 1:  # réparation
                    Dep_oct_r += rep
                elif item[4] == 3:  # préventif
                    Dep_oct_p += prev
            if date_complete.month == 11:  # novembre
                if item[4] == 1:  # réparation
                    Dep_nov_r += rep
                elif item[4] == 3:  # préventif
                    Dep_nov_p += prev
            if date_complete.month == 12:  # décembre
                if item[4] == 1:  # réparation
                    Dep_dec_r += rep
                elif item[4] == 3:  # préventif
                    Dep_dec_p += prev

        # préparation de la liste pour calcul du cumulatif par mois
        list_dep_rep = [Dep_janv_r, Dep_fev_r, Dep_mars_r, Dep_avril_r, Dep_mai_r, Dep_juin_r, Dep_juil_r, Dep_aout_r,
                        Dep_sept_r, Dep_oct_r, Dep_nov_r, Dep_dec_r]
        list_dep_prev = [Dep_janv_p, Dep_fev_p, Dep_mars_p, Dep_avril_p, Dep_mai_p, Dep_juin_p, Dep_juil_p, Dep_aout_p,
                         Dep_sept_p, Dep_oct_p, Dep_nov_p, Dep_dec_p]
        # print('liste tickets:', ticket_list)
        # print('liste réparations j-dec:',list_dep_rep)
        # print('liste préventif:', list_dep_prev)
        # on divise les salaires totaux /12 pour répartition mensuelle
        if salaires_tot != None or salaires_tot != 0:
            dep_sal = int(salaires_tot / 12)
        else:
            dep_sal = 0
        # print('salaires:',salaires_tot)
        list_cum_rep = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        list_cum_prev = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        mois_debut_budget = date_annee_cour.month
        mois_actuel = date.today().month
        cum_rep = 0
        cum_prev = 0

        # on passe à travers les 12 mois en débutant par le mois de début de budget
        for i in range(0,11):
            indice=mois_debut_budget+i
            if indice<=12:
                if indice==mois_actuel+1:
                    break
                cum_rep=cum_rep + list_dep_rep[indice-1]+dep_sal
                list_cum_rep[i]=cum_rep
                cum_prev=cum_prev + list_dep_prev[indice-1]
                list_cum_prev[i] = cum_prev
            else:
                indice_plus=indice-12
                if indice_plus==mois_actuel+1:
                    break
                cum_rep = cum_rep + list_dep_rep[indice_plus-1]+dep_sal
                list_cum_rep[i] = cum_rep
                cum_prev = cum_prev + list_dep_prev[indice_plus-1]
                list_cum_prev[i] = cum_prev

        # préparation des listes pour le graphique
        liste_mois = ['Jan', 'Fev', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aout', 'Sept', 'Oct', 'Nov', 'Dec']
        # rotation des listes à partir d'un indice à partir de la fin de la liste
        deq = collections.deque(liste_mois)
        deq.rotate(12 - int(mois_debut_budget) + 1)
        labels_mois = list(deq)
    except:
        print(traceback.format_exc())

    return render_template('dashboard_proprios.html', labels_mois=labels_mois, budgets_mois=budget_list, reparations=list_cum_rep,
                           preventif=list_cum_prev,ytd_pourcent=ytd_pourcent, labels_10=labels_10, budget_10=budgets_10, records_10=records_10,
                           bd=profile_list[3])

# tableau de bord avec ChartJS
#graphique par année de remplacement, par priorité en cours, par intervenant
#durant année budgétaire en cours, bp_tickets par équipement, dépenses vs. budget

@bp_tableaux_bord.route("/plotView_js", methods=["GET"])
def plotView_js():
    """Afficher le tableau de bord des administrateurs avec graphiques de CHartJS.

    * histogramme de tickets en cours par intervenant et par priorité
    * histogramme d'activité par catégorie d'équipement
    * durant année budgétaire en cours, tickets par équipement, dépenses vs. budget
    * historique des projets d'entretien (plus de 1000$)
    * pie chart des tickets par tag d'équipement depuis le démarrage du système
    * histogramme d'entretien préventif déjà cédulé dans l'année à partir de la table 'préventif'

    |  3 tableaux et une table dynamique:

    * Tableau des dépenses année à date par type de travail avec tickets selon année courante et statut>2
    * remplissage des indicateurs de couleur:
    *     nombre de tickets en cours et délais par priorité
    *     total de tickets complétés, fermés"""
    intervenant_list=[]
    priorite_1_count=[]
    priorite_2_count = []
    priorite_3_count = []
    priorite_4_count = []
    ytd_pourcent=str()
    labels_12=[]
    budgets_12=[]
    records_12=[]
    labels_pie=[]
    tickets_pie=[]
    labels_categ_pie = []
    tickets_categ_pie = []
    labels_preventif=[]
    heures_fournisseurs=[]
    heures_employes=[]
    version_client=0
    # ******************remplissage des indicateurs: champs du nombre de tickets et délais *********************
    try:
        if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list=session.get('ProfilUsager')
        client_ident=profile_list[0]
        version_client=profile_list[6]

        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        date_annee_cour=date.today()
        cible_age=0
        # trouver la date du début d'année fiscale budgétaire
        cur.execute("SELECT DateDebutBudget, CibleAgeMoyenTicket FROM parametres WHERE IDClient=%s",(client_ident,))
        for item in cur.fetchall():
            date_annee_cour=item[0]
            cible_age=item[1]
        ticket_priorite_list=[]
        ticket_statut_list=[]
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
        count_completes=0
        cum_jrs_completes=0
        count_fermes=0
        moy_jrs_prior1=0
        moy_jrs_prior2=0
        moy_jrs_prior3=0
        moy_jrs_prior4=0
        moy_jrs_encours=0
        moy_jrs_completes=0
        cum_hres_est=0
        cum_hres_estimees=0
        cum_hres_req=0
        cum_tot_tickets_1 = 0
        cum_tot_tickets_2 = 0
        cum_tot_tickets_3 = 0
        cum_tot_tickets_4 = 0
        # préparer liste des tickets en cours incluant ceux créés avant la date de début du budget
        cur.execute("SELECT Priorite, DatePrevue, Statut, HeuresEstimees, IDIntervenant FROM tickets "
                "WHERE Statut=%s AND IDClient=%s",(2,client_ident,))
        for row in cur.fetchall():
            ticket_priorite_list.append(row)
        for item in ticket_priorite_list:
            # vérifier si le ticket touche un employé
            cur.execute("SELECT IDTypeIntervenant from intervenants WHERE IDIntervenant=%s", (item[4],))
            for row in cur.fetchall():
                if row[0] == 1:
                    cum_hres_estimees = cum_hres_estimees + item[3]

            #calcul du nombre de jours par rapport à date prévue
            a = item[1]
            b = date.today()
            delta = b - a
            #selon statut, on sépare les bp_tickets
            if item[2]==2:
                if item[0]==1:
                    cum_tot_tickets_1 += 1
                    # éviter de compter les tickets avec une date prévue ultérieure
                    if delta.days<=0:
                        continue
                    else:
                        count_prior1+=1
                        cum_jrs_prior1=cum_jrs_prior1+delta.days
                elif item[0]==2:
                    cum_tot_tickets_2 += 1
                    # éviter de compter les tickets avec une date prévue ultérieure
                    if delta.days <= 0:
                        continue
                    else:
                        count_prior2+=1
                        cum_jrs_prior2=cum_jrs_prior2+delta.days
                elif item[0]==3:
                    cum_tot_tickets_3 += 1
                    # éviter de compter les tickets avec une date prévue ultérieure
                    if delta.days <= 0:
                        continue
                    else:
                        count_prior3+=1
                        cum_jrs_prior3=cum_jrs_prior3+delta.days
                elif item[0]==4:
                    cum_tot_tickets_4 += 1
                    # éviter de compter les tickets avec une date prévue ultérieure
                    if delta.days <= 0:
                        continue
                    else:
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

        #préparer liste de tickets selon statut durant année de budget en cours
        cur.execute("SELECT Priorite, DateCreation, Statut, HeuresEstimees, HeuresRequises, IDIntervenant FROM tickets "
                    "WHERE DateCreation >= %s AND IDClient=%s",(date_annee_cour,client_ident))
        for row in cur.fetchall():
            ticket_statut_list.append(row)

        count_tot_encours=0
        for item in ticket_statut_list:
            #calcul du nombre de jours depuis création
            a = item[1]
            b = date.today()
            delta = b - a

            #selon statut, on sépare les tickets
            if item[2]==2:
                count_tot_encours+=1
                cum_jrs_encours=cum_jrs_encours+delta.days
            elif item[2] == 3:
                count_completes += 1
                cum_jrs_completes = cum_jrs_completes + delta.days
                if item[3] != None:
                    cum_hres_est = cum_hres_est + item[3]
                if item[4] != None:
                    cum_hres_req = cum_hres_req + item[4]
            elif item[2] == 4:
                count_fermes += 1
                if item[3] != None:
                    cum_hres_est = cum_hres_est + item[3]
                if item[4] != None:
                    cum_hres_req = cum_hres_req + item[4]
        cnx.close()
        if count_completes!=0:
            moy_jrs_completes=int(cum_jrs_completes/count_completes)
        if cum_hres_req!=0:
            performance_estimation=int((cum_hres_est/cum_hres_req)*100)
        else:
            performance_estimation=0
        # on remplace la performance d'estimation avec le total des heures estimées pour les tickets en cours
        indicateurs=[cum_tot_tickets_1,moy_jrs_prior1,cum_tot_tickets_2,moy_jrs_prior2,cum_tot_tickets_3,moy_jrs_prior3,cum_tot_tickets_4,
                     moy_jrs_prior4,moy_jrs_encours,count_tot_encours,count_completes,count_fermes,int(cum_hres_estimees),cible_age]
        print('indicateurs:',indicateurs)
    except:
        print(traceback.format_exc())
        indicateurs=[0,0,0,0,0,0,0,0,0,0,0,0,0,0]

    # ***************** Tickets par intervenant et priorité histogramme **********************************
    try:
        if session.get('ProfilUsager') is None:
            # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list = session.get('ProfilUsager')
        # vérifier type d'usager si employé
        if profile_list[2] == 3:
            return redirect(url_for('bp_admin.permission'))
        client_ident = profile_list[0]
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()

        intervenant_list=[]
        priorite_1_count=[]
        priorite_2_count=[]
        priorite_3_count=[]
        priorite_4_count=[]
        #trouver les 10 bp_intervenants ayant le plus de bp_tickets en cours
        select_interv_list=[]
        cur.execute("SELECT IDIntervenant FROM tickets WHERE Statut=2 AND IDClient=%s",(client_ident,))
        NomIntervenant=''
        for row in cur.fetchall():
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s", (row[0],client_ident))
            for item_1 in cur.fetchall():
                NomIntervenant=item_1[0]
            select_interv_list.append(NomIntervenant)
        #compter le nombre de bp_tickets par intervenant
        counter=collections.Counter(select_interv_list)
        interv_dict=dict(counter)
        #print('Tickets par intervenant:',interv_dict)
        sorted_list=sorted(interv_dict.items(), key=lambda x:x[1], reverse=True)
        top_15_list=sorted_list[0:15]
        #print('10 premiers:',top_10_list)
        intervenant_list=[]
        for i in top_15_list:
            intervenant_list.append(i[0])
        #print('Liste finale:',intervenant_list)
        #traiter les bp_tickets en cours
        ticket_list=[]
        cur.execute("SELECT IDIntervenant, Priorite FROM tickets WHERE Statut=2 AND IDClient=%s",(client_ident,))
        for row in cur.fetchall():
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s", (row[0],client_ident))
            for item_1 in cur.fetchall():
                NomIntervenant=item_1[0]
            list_item=(str(NomIntervenant),(row[1]))
            ticket_list.append(list_item)
        cnx.close()
        #intervenant_list=list(dict.fromkeys(intervenant_list))
        # pour compter le nombre de billets par priorité par intervenant
        for i in intervenant_list:
            count_1=0
            count_2=0
            count_3=0
            count_4=0
            for j in ticket_list:
                if j[0]==i:
                    if j[1]==1:
                        count_1+=1
                    elif j[1]==2:
                        count_2+=1
                    elif j[1]==3:
                        count_3+=1
                    elif j[1]==4:
                        count_4+=1
            priorite_1_count.append(count_1)
            priorite_2_count.append(count_2)
            priorite_3_count.append(count_3)
            priorite_4_count.append(count_4)

    except:
        print(traceback.format_exc())

#     #***************** Activité par catégorie d'équipement histogramme******************************
    try:
        if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list=session.get('ProfilUsager')
        client_ident=profile_list[0]
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        date_annee_cour=date.today()
        cible_age=0
        # trouver la date du début d'année fiscale budgétaire
        cur.execute("SELECT DateDebutBudget, CibleAgeMoyenTicket FROM parametres WHERE IDClient=%s",(client_ident,))
        for item in cur.fetchall():
            date_annee_cour=item[0]
            cible_age=item[1]

        #calculer avancement sur année budgétaire
        a = date_annee_cour
        b = date.today()
        delta = b - a
        days_ytd=delta.days
        ytd_pourcent=str(round(int(days_ytd*100/365)))+'%'

        #trouver budget pour chaque catégorie
        cur.execute("SELECT IDCategorie,Description,BudgetAnnuel FROM categories WHERE IDClient=%s",(client_ident,))
        categ_list=[]
        for row in cur.fetchall():
            #listes en ordre de catégorie dont IDCategorie=1 sera budget_list[0]
            categ_list.append(row)

        #trouver tickets selon année courante et statut>2
        ticket_list=[]
        IDCateg_list_tickets=[]
        cur.execute("SELECT IDCategorie, CoutTotalTTC, Statut FROM tickets "
            "WHERE Statut>2 AND DateComplet > %s AND TypeTravail IN ('1','3') AND IDClient=%s",(date_annee_cour,client_ident))
        for row in cur.fetchall():
            IDCateg_list_tickets.append(row[0])
            ticket_list.append(row)

        # s'assurer que les 4 catégories liées au salaires sont dans la liste
        if 8 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(8)
        if 17 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(17)
        if 20 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(20)
        if 21 not in IDCateg_list_tickets:
            IDCateg_list_tickets.append(21)

        # trouver les salaires par catégorie
        list_salaires_categ=[]
        cur.execute("SELECT SalairesTotal, PartCateg_8, PartCateg_17, PartCateg_20, PartCateg_21 FROM parametres "
                    "WHERE IDClient=%s",(client_ident,))
        for row in cur.fetchall():
            list_salaires_categ.append(row)
        cnx.close()
        #compter le nombre de tickets par catégorie: ex. IDCateg:nbre tickets
        res_count_numeros=Counter(IDCateg_list_tickets)
        unique_cat_list_numeros=list(res_count_numeros)
        budgets=[]
        labels=[]
        records=[]

        for item in unique_cat_list_numeros:
            for item_1 in categ_list:
                if item_1[0]==item:
                    label_contenu=item_1[1]+'('+str(res_count_numeros[item])+')'
                    labels.append(label_contenu)
                    if item_1[2] is None or item_1[2]=='None':
                        budgets.append(0)
                    elif item_1[2]=='':
                        budgets.append(0)
                    else:
                        budgets.append(int(item_1[2]))
            cum_dep=0

            for i in ticket_list:
                if i[0]==item:
                    if i[1]==None or i[1]=='':
                        cum_dep=cum_dep
                    else:
                        cum_dep=cum_dep+i[1]

            #ajout des salaires pour catégories (8,17,20,21)
            salaires=0
            if item==8:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][1]/100)*days_ytd/365
            elif item==17:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][2]/100)*days_ytd/365
            elif item==20:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][3]/100)*days_ytd/365
            elif item==21:
                salaires=list_salaires_categ[0][0]*(list_salaires_categ[0][4]/100)*days_ytd/365

            cum_dep=int(cum_dep+int(salaires))
            records.append(cum_dep)

        # trier les trois listes en même temps basé sur les dépenses (records) en ordre décroissant
        zipped_list=zip(records,budgets,labels)
        liste_triee=sorted(zipped_list,key=None, reverse=True)

        #choisir les 12 premières catégories (plus de dépenses)
        records_12=[i[0] for i in liste_triee[0:12]]
        budgets_12=[i[1] for i in liste_triee[0:12]]
        labels_12=[i[2] for i in liste_triee[0:12]]

    except:
        print(traceback.format_exc())

    #*************** Tableau des dépenses année à date *********************************

    #trouver tickets selon année courante et statut>2
    try:
        if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list=session.get('ProfilUsager')
        client_ident=profile_list[0]
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        date_annee_cour=date.today()
        # trouver la date du début d'année fiscale budgétaire
        cur.execute("SELECT DateDebutBudget FROM parametres WHERE IDClient=%s",(client_ident,))
        for item in cur.fetchall():
            date_annee_cour=item[0]
        ticket_list=[]
        cur.execute("SELECT TypeTravail, HeuresRequises, CoutTotalTTC, Statut FROM tickets "
            "WHERE Statut>2 AND DateComplet > %s AND IDClient=%s",(date_annee_cour,client_ident))
        for row in cur.fetchall():
            ticket_list.append(row)

        # comptage des dépenses et des heures selon type de travail
        cum_totalTTC_1=0
        cum_totalTTC_2 = 0
        cum_totalTTC_3 = 0
        cum_totalTTC_4 = 0
        cum_totalTTC_5 = 0

        for item in ticket_list:
            if item[0]==1:
                cum_totalTTC_1=cum_totalTTC_1+((0 if item[2] == None or item[2] == '' else item[2]))
            elif item[0]==2:
                cum_totalTTC_2=cum_totalTTC_2+((0 if item[2] == None or item[2] == '' else item[2]))
            elif item[0]==3:
                cum_totalTTC_3=cum_totalTTC_3+((0 if item[2] == None or item[2] == '' else item[2]))
            elif item[0]==4:
                cum_totalTTC_4 = cum_totalTTC_4 + ((0 if item[2] == None or item[2] == '' else item[2]))
            elif item[0]==5:
                cum_totalTTC_5 = cum_totalTTC_5 + ((0 if item[2] == None or item[2] == '' else item[2]))

        #calculer avancement sur année budgétaire
        a = date_annee_cour
        b = date.today()
        delta = b - a
        days_ytd=delta.days

        # trouver les salaires par catégorie
        list_salaires_categ=[]
        cur.execute("SELECT SalairesTotal FROM parametres WHERE IDClient=%s",(client_ident,))
        for row in cur.fetchall():
            list_salaires_categ.append(row)
        cnx.close()
        # ajout des salaires au total de main d'oeuvre
        ajout_salaires=list_salaires_categ[0][0]*days_ytd/365

        cum_totalTTC_1=int(cum_totalTTC_1)+int(ajout_salaires)
        tot_totalTTC=int(cum_totalTTC_1)+int(cum_totalTTC_2)+int(cum_totalTTC_3)+int(cum_totalTTC_4)+int(cum_totalTTC_5)
        if tot_totalTTC!=0:
            part_1 = 100*float(cum_totalTTC_1) / float(tot_totalTTC)
            part_2 = 100*float(cum_totalTTC_2) / float(tot_totalTTC)
            part_3 = 100*float(cum_totalTTC_3) / float(tot_totalTTC)
            part_4 = 100*float(cum_totalTTC_4) / float(tot_totalTTC)
            part_5 = 100 * float(cum_totalTTC_5) / float(tot_totalTTC)
            part_mdo_tot = 100 * (cum_totalTTC_1 + cum_totalTTC_2 + cum_totalTTC_3 + cum_totalTTC_4) / tot_totalTTC

        else:
            part_1 = 0
            part_2 = 0
            part_3 = 0
            part_4 = 0
            part_5 = 0
            part_mdo_tot = 0

        tableau_list=[("Entretien/réparations",int(cum_totalTTC_1), round(part_1,1)),("Fonds de prévoyance",int(cum_totalTTC_2),round(part_2,1)),
                      ("Préventif",int(cum_totalTTC_3),round(part_3,1)),("Projets d'amélioration",int(cum_totalTTC_4),
                    round(part_4,1)),("Sinistres",int(cum_totalTTC_5),round(part_5,1)),("Total ($)",tot_totalTTC,round(part_mdo_tot,1))]

    except:
        print(traceback.format_exc())
        tableau_list=['nil','nil','nil','nil']


#         #*************** Tickets par équipement pie chart (Carnet PLus seulement) *********************************
    try:
        if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list=session.get('ProfilUsager')
        client_ident=profile_list[0]
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        ticket_list=[]
        # comptage des bp_tickets par IDEquipement
        cur.execute("SELECT IDEquipement FROM tickets WHERE IDClient=%s",(client_ident,))
        for row in cur.fetchall():
            if row[0]!='':
                #ticket_list.append(row[0])
                cur.execute("SELECT Actif FROM equipements WHERE IDEquipement=%s AND IDClient=%s",(row[0],client_ident))
                for row_1 in cur.fetchall():
                    if row_1[0]==1:
                        ticket_list.append(row[0])

        counter=collections.Counter(ticket_list)
        equip_dict=dict(counter)
        sorted_list=sorted(equip_dict.items(), key=lambda x:x[1], reverse=True)
        top_10_list=sorted_list[0:10]
        labels_pie=[]
        tickets_pie=[]
        for item in top_10_list:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",(item[0],client_ident))
            for row in cur.fetchall():
                desc=str(row[0])+' - '+str(row[1])
                labels_pie.append(desc)
                tickets_pie.append(item[1])
        cnx.close()

    except:
        print(traceback.format_exc())

##*************** Tickets par catégorie pie chart (Carnet Entretien seulement) *********************************
    try:
        if session.get('ProfilUsager') is None:
            # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list = session.get('ProfilUsager')
        client_ident = profile_list[0]
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        ticket_list_categ = []
        # comptage des bp_tickets par IDEquipement
        cur.execute("SELECT IDCategorie FROM tickets WHERE IDClient=%s", (client_ident,))
        for row in cur.fetchall():
            if row[0] != '':
                # ticket_list.append(row[0])
                cur.execute("SELECT Actif FROM categories WHERE IDCategorie=%s AND IDClient=%s",
                            (row[0], client_ident))
                for row_1 in cur.fetchall():
                    if row_1[0] == 1:
                        ticket_list_categ.append(row[0])

        counter = collections.Counter(ticket_list_categ)
        equip_dict_categ = dict(counter)
        sorted_list = sorted(equip_dict_categ.items(), key=lambda x: x[1], reverse=True)
        top_10_categ_list = sorted_list[0:10]
        labels_categ_pie = []
        tickets_categ_pie = []
        for item in top_10_categ_list:
            cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s",
                        (item[0], client_ident))
            for row in cur.fetchall():
                desc = str(row[0])
                labels_categ_pie.append(desc)
                tickets_categ_pie.append(item[1])
        cnx.close()

    except:
        print(traceback.format_exc())

    # *************************Histogramme d'entretien préventif déjà cédulé dans l'année
    try:
        if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
            return render_template('session_ferme.html')
        profile_list=session.get('ProfilUsager')
        client_ident=profile_list[0]
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        prev_list=[]
        #obtenir tous les préventifs d'ici à un an
        end_date=date.today()+ relativedelta(years=1)
        # utiliser `Dec` pour éviter erreur mysql due à 'mot réservé'
        cur.execute("SELECT IDIntervenant, IDPreventif, HresEstimees,FreqAns,Janv,Fev,Mars,"
                    "Avril,Mai,Juin,Juil,Aout,Sept,Oct,Nov,`Dec`,DateProchain FROM preventif "
                    "WHERE IDTypeTravail=3 AND DateProchain <= %s AND IDClient=%s",(end_date,client_ident))
        for row in cur.fetchall():
            prev_list.append(row)
        # tous les cumulatifs sont de type 'float' pour éviter erreur numpy dû à comparaison entre float et decimal.Decimal (dans liste)
        Hres_janv = float()
        Hres_fev = float()
        Hres_mars = float()
        Hres_avril = float()
        Hres_mai = float()
        Hres_juin = float()
        Hres_juil = float()
        Hres_aout = float()
        Hres_sept = float()
        Hres_oct = float()
        Hres_nov = float()
        Hres_dec = float()
        # cumul d'heures pour employé
        Hres_janv_1 = float()
        Hres_fev_1 = float()
        Hres_mars_1 = float()
        Hres_avril_1 = float()
        Hres_mai_1 = float()
        Hres_juin_1 = float()
        Hres_juil_1 = float()
        Hres_aout_1 = float()
        Hres_sept_1 = float()
        Hres_oct_1 = float()
        Hres_nov_1 = float()
        Hres_dec_1 = float()
        Interv_type = int()
        for item in prev_list:
            cur.execute("SELECT IDTypeIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
                        (item[0], client_ident))
            for res in cur.fetchall():
                Interv_type = res[0]
            # cumuler les Dates prochaines de tous les mois car si freqans-1, il pourrait y avoir répétition, sinon, pas de répétition.
            # date_enreg=item[16]
            # tous les cumulatifs sont de type 'float' pour éviter erreur numpy dû à comparaison entre float et decimal.Decimal (dans liste)

            if item[4] == 1:  # janvier
                if Interv_type == 1:  # employé
                    Hres_janv_1 += float(item[2])
                else:
                    Hres_janv += float(item[2])
            if item[5] == 1:
                if Interv_type == 1:
                    Hres_fev_1 += float(item[2])
                else:
                    Hres_fev += float(item[2])
            if item[6] == 1:
                if Interv_type == 1:
                    Hres_mars_1 += float(item[2])
                else:
                    Hres_mars += float(item[2])
            if item[7] == 1:
                if Interv_type == 1:
                    Hres_avril_1 += float(item[2])
                else:
                    Hres_avril += float(item[2])

            if item[8] == 1:
                if Interv_type == 1:
                    Hres_mai_1 += float(item[2])
                else:
                    Hres_mai += float(item[2])
            if item[9] == 1:
                if Interv_type == 1:
                    Hres_juin_1 += float(item[2])
                else:
                    Hres_juin += float(item[2])
            if item[10] == 1:
                if Interv_type == 1:
                    Hres_juil_1 += float(item[2])
                else:
                    Hres_juil += float(item[2])
            if item[11] == 1:
                if Interv_type == 1:
                    Hres_aout_1 += float(item[2])
                else:
                    Hres_aout += float(item[2])
            if item[12] == 1:
                if Interv_type == 1:
                    Hres_sept_1 += float(item[2])
                else:
                    Hres_sept += float(item[2])
            if item[13] == 1:
                if Interv_type == 1:
                    Hres_oct_1 += float(item[2])
                else:
                    Hres_oct += float(item[2])
            if item[14] == 1:
                if Interv_type == 1:
                    Hres_nov_1 += float(item[2])
                else:
                    Hres_nov += float(item[2])
            if item[15] == 1:
                if Interv_type == 1:
                    Hres_dec_1 += float(item[2])
                else:
                    Hres_dec += float(item[2])

        cnx.close()
        liste_mois=['Jan','Fev','Mar','Avr','Mai','Juin','Juil','Aout','Sept','Oct','Nov','Dec']
        liste_hres_fournisseurs=[Hres_janv,Hres_fev,Hres_mars,Hres_avril,int(Hres_mai),Hres_juin,Hres_juil,Hres_aout,Hres_sept,Hres_oct,Hres_nov,Hres_dec]
        liste_hres_employes=[Hres_janv_1,Hres_fev_1,Hres_mars_1,Hres_avril_1,Hres_mai_1,Hres_juin_1,Hres_juil_1,Hres_aout_1,Hres_sept_1,Hres_oct_1,Hres_nov_1,Hres_dec_1]

        date_cour = date.today()
        mois_courant=date_cour.month

        #rotation des listes à partir d'un indice à partir de la fin de la liste
        deq=collections.deque(liste_mois)
        deq.rotate(12-int(mois_courant)+1)
        labels_preventif=list(deq)
        deq=collections.deque(liste_hres_fournisseurs)
        deq.rotate(12-int(mois_courant)+1)
        heures_fournisseurs=list(deq)
        deq=collections.deque(liste_hres_employes)
        deq.rotate(12-int(mois_courant)+1)
        heures_employes=list(deq)
        # les 2 listes sont maintenant en ordre de mois à partir du mois courant

    except:
        print(traceback.format_exc())


    return render_template('dashboard_plus.html', indicateurs=indicateurs, intervenant_list=intervenant_list,
                           priorite_1=priorite_1_count, priorite_2=priorite_2_count, priorite_3=priorite_3_count, priorite_4=priorite_4_count,
                           ytd_pourcent=ytd_pourcent, labels_12=labels_12, budget_12=budgets_12, records_12=records_12, tableau_list=tableau_list,
                           labels_pie=labels_pie, tickets_pie=tickets_pie, labels_preventif=labels_preventif, heures_fournisseurs=heures_fournisseurs,
                           heures_employes=heures_employes, bd=profile_list[3])
