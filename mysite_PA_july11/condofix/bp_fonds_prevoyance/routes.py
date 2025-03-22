import sys

from flask import Blueprint, render_template,json,session,request,redirect,url_for,flash,send_file
import mysql.connector
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import decimal
from utils import connect_db

bp_fonds_prevoyance = Blueprint('bp_fonds_prevoyance', __name__)

@bp_fonds_prevoyance.route('/home')
#page d'acceuil sans menu opérationnel
def home():
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    return render_template('fonds_prevoyance_proprio.html', bd=profile_list[3])

@bp_fonds_prevoyance.route('/import_excel')
#page d'acceuil sans menu opérationnel
def import_excel():
    return render_template('import_excel.html')

@bp_fonds_prevoyance.route('/admin')
def admin():
    return render_template('fonds_prevoyance_admin.html')

@bp_fonds_prevoyance.route('/calcul_dep/<args>')
def calcul_dep (args):
    """ fonction de calcul des dépenses selon les 3 arguments (args) soient 'usager' (syndicat et coproprios), 'mode' (base, scenario, ajuste)
     et 'taux' (taux d'inflation utilisé pour scenario ou ajuste...égal à '0' pour base). Celle-ci est intégrée dans les fonctions de graphique
    'depenses_fdp' et 'solde_fdp' et 'solde_fdp_ajuste'. Seulement l'usager 'syndicat' utilisé pour les dépenses utilisées dans le graphique du
    fonds de prévoyance.
        """

    # ***************************compilation de 50 ans de dépenses prévues
    # processus de programmation:
    # 1- débuter avec l'année de la dernière analyse de fonds de prévoyance
    # 2- selon l'usager choisi (syndicat ou coproprios), sélectionner toutes les interventions du fonds de prévoyance
        # syndicat: PartSyndicat>0   coproprios: PartSyndicat<1
    # 3- identifier les enregistrements qui ont plus d'un cycle d'intervention (année prochain plus fréquence<= 50 ans)
    # 4- créer de nouveaux items pour ceux-ci et ajouter à la liste en modifiant l'élément 'an_Prochain'
    # 5- selon le mode (base, scenario ou ajusté), appliquer le taux d'inflation indiqué et la part du syndicat à chaque élément de la liste à partir de l'année suivant celle de l'analyse et
    #     #    utilisant l'année prévue pour l'intervention:
    #   a) pour base: selon 5-10-15+ de chaque intervention
    #   b) pour scenario: taux global appliqué à toutes les années
    #   c) pour ajusté: taux réel de l'ICC appliqué durant les années oû la statistique est compilée puis retour au taux inflation annuel
    #                   moyen calculé à partir des valeurs (5-10-15+) de toutes les interventions
    # 6- trier la liste en ordre croissant par 'an_prochain'

    # LA LISTE PEUT MAINTENANT ÊTRE UTILISÉE POUR LES 2 FONCTIONS DE GRAPHIQUES ET POUR LE TABLEAU DYNAMIQUE DES DÉPENSES PRÉVUES

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager (pas employé)
    if profile_list[2] == 3:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]
    mode_connexion=profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # mettre en valeur les arguments de la fonction
    usager= args[0]# syndicat ou coproprios
    mode= args[1]# base ou scenario ou ajuste
    taux_applicable= args[2]# 0 ou taux du scenario ou taux réel (ajusté)


    date_anal = datetime

    cur.execute("SELECT DateAnalPrevoyance FROM parametres WHERE IDClient=%s", (client_ident,))
    # 1- débuter avec l'année de la dernière analyse de fonds de prévoyance
    for item in cur.fetchall():
        date_anal = item[0]

    # 2- mettre tous les enregistrements de la table de fonds de prévoyance dans une liste
    fill_brut = []
    if usager=='syndicat':
        cur.execute(
            "SELECT IDFondsPrevoyance, DescriptionDepense, TypeMtceRempl, IDCategorie, RefGroupeUniformat, RefAnalyse, ValeurActuelleInterv, "
            "FrequenceAns, AnProchain, Inflation5ans, Inflation6a15ans, InflationPlus15ans, IDIntervenant, PartSyndicat "
            "FROM fondsprevoyance WHERE PartSyndicat>%s AND Actif=%s AND IDClient=%s",(0,1,client_ident))
    else:
        cur.execute(
            "SELECT IDFondsPrevoyance, DescriptionDepense, TypeMtceRempl, IDCategorie, RefGroupeUniformat, RefAnalyse, ValeurActuelleInterv, "
            "FrequenceAns, AnProchain, Inflation5ans, Inflation6a15ans, InflationPlus15ans, IDIntervenant, PartSyndicat "
            "FROM fondsprevoyance WHERE PartSyndicat<%s AND Actif=%s AND IDClient=%s",(1,1,client_ident))
    type=str()
    desc_categ=str()
    gr_uniformat=int()
    desc_uniformat=str()
    desc_intervenant=str()
    taux_infl_moyen_anal = float()
    fill_indice_moy=[]
    for item in cur.fetchall():
        if item[2] == 1:
            type = "Maintenance"
        elif item[2] == 2:
            type = "Remplacement"
        item+=(type,)   #14
        cur.execute("SELECT Description, IDGroupe FROM categories WHERE IDCategorie=%s AND IDClient=%s",
                    (item[3], client_ident))
        for row in cur.fetchall():
            desc_categ= row[0]
            gr_uniformat = row[1]
        item += (desc_categ,) #15
        item += (gr_uniformat,) #16
        cur.execute("SELECT Descriptif FROM groupesuniformat WHERE IDGroupe=%s", (gr_uniformat,))
        for row_1 in cur.fetchone():
            desc_uniformat=row_1
        item += (desc_uniformat,)  #17
        if item[12]==0:
            desc_intervenant=''
        else:
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s", (item[12],client_ident))
            for row_1 in cur.fetchone():
                desc_intervenant = row_1
        item += (desc_intervenant,)  # 18
        fill_brut.append(item)

        # pour le calcul du taux d'inflation moyen utilisé parmi toutes les interventions
        ajout_indice = (item[9], item[10], item[11])
        fill_indice_moy.append(ajout_indice)

    # calcul du taux d'inflation moyen de toutes les interventions de l'analyse
    cum_index = 0
    for record in fill_indice_moy:
        # pour période de 25 ans (5,10 et 10)
        cum_index += (1 + record[0]) ** 5 * (1 + record[1]) ** 10 * (1 + record[2]) ** 10
    if len(fill_indice_moy) != 0:
        avg_index_brut = float(cum_index / len(fill_indice_moy))
        avg_index_net = avg_index_brut ** (1 / 25)
        taux_infl_moyen_anal = round(avg_index_net - 1, 4)

    # 3- fixer le nombre d'années applicables au traitement : ans_traites (5 , 25 ou autre)
    annee_anal = date_anal.year
    date_fin_brut = date_anal + relativedelta(years=50)
    annee_fin = date_fin_brut.year

    # 4- identifier les enregistrements qui ont plus d'un cycle d'intervention (année prochain plus fréquence>= ans_traites) et
    # 5- créer de nouveaux items pour ceux-ci et ajouter à la liste en modifiant le champ 'an_Prochain'
    fill_ajouts = []
    for item in fill_brut:
        # vérifier si plus d'un cycle d'intervention dans période fixée (période /fréquence_ans)
        proch_interv = item[8]
        freq = item[7]
        while proch_interv + freq <= annee_fin:
            proch_interv = proch_interv + item[7]
            # 'item' est un tuple et doit être transformé en liste pour remplacer un item puis ramené à un tuple
            a_list = list(item)
            a_list[8] = proch_interv
            updated_tuple = tuple(a_list)
            fill_ajouts.append(updated_tuple)

    # joindre les 2 listes (brut plus ajouts)
    fill_interv_50ans = fill_brut + fill_ajouts
    # 6- trier la liste en ordre croissant par 'année d'intervention'
    fill_interv_50ans.sort(key=lambda x: x[8])

    # 7- Appliquer les taux d'inflation et la part du syndicat à chaque intervention et ajouter à une nouvelle liste qui contiendra
    #    seulement les données requises pour les graphiques, le solde du fonds et le tableau dynamique

    # calculer l'indice du cout de construction réel depuis la date de l'analyse
    # 1 obtenir le dernier indice de la table
    indice_act = 0
    trimestre_act = 0
    annee_indice_act = 0
    cur.execute("SELECT * FROM indices WHERE IDIndice = (SELECT max(IDIndice) FROM indices)")
    for item in cur.fetchall():
        indice_act = item[4]
        trimestre_act = item[2]
        annee_indice_act = item[3]

    # 2 obtenir indice ICC au premier trimestre de la date du rapport
    indice_debut = 0
    cur.execute("SELECT Valeur,Annee FROM indices WHERE Annee=%s AND Trimestre=%s",
                (annee_anal, trimestre_act))  # datetime.now().year))
    for item in cur.fetchall():
        indice_debut = item[0]

    croiss_ICC=float()
    annee_chaine = date_anal.strftime("%Y%m%d")
    annee_deb = int(annee_chaine[0:4])
    delta_annees = annee_indice_act - annee_deb
    if delta_annees <= 0:
        # le taux statistique réel est remplacé par le taux moyen de toutes les interventions
        croiss_ICC = taux_infl_moyen_anal * 100
    elif delta_annees == 1:
        if indice_act > indice_debut and indice_debut != 0:
            croiss_ICC = round((indice_act - indice_debut) / 1, 2)
        else:
            croiss_ICC = taux_infl_moyen_anal * 100
    else:
        croiss_ICC = round((indice_act - indice_debut) / delta_annees, 2)

    indice = 1
    inflation_taux = float()
    fill_dep_50ans=[]
    annee_traitee = annee_anal
    taux_reel = float(croiss_ICC / 100)
    while annee_traitee <= annee_fin:
        for item in fill_interv_50ans:
            if item[8] == annee_traitee:
                # on ignore la première année soit celle de l'analyse du consultant
                if indice==1:
                    inflation_taux=1
                else:
                    if mode=='base':
                        # selon indice (nombre d'années courues), on calcule le taux d'inflation approprié
                        if indice < 6:
                            # prendre 1ere valeur d'inflation (5 ans)
                            inflation_taux = (1 + item[9]) ** (indice-1)
                        elif 5 < indice < 16:
                            # 2ème taux d'inflation pour ans 6 à 15
                            inflation_taux = ((1 + item[9]) ** 5) * (1 + item[10]) ** (indice - 6)
                        elif indice > 15:
                            # 3ème taux d'inflation pour après 15 ans
                            inflation_taux = ((1 + item[9]) ** 5) * ((1 + item[10]) ** 10) * ((1 + item[11]) ** (indice - 16))
                    elif mode=='ajuste':
                        # application du taux d'inflation pour données ajustées
                        taux_infl_moyen_anal = float(taux_infl_moyen_anal)
                        # SCÉNARIO DE RETOUR AU TAUX DE L'ANALYSE APRÈS X ANS AU TAUX RÉEL (X est le delta_annees)
                        if indice <= delta_annees:
                            inflation_taux = (1 + taux_reel) ** indice
                        else:
                            inflation_taux = ((1 + taux_reel) ** delta_annees) * (
                                        (1 + taux_infl_moyen_anal) ** (indice - delta_annees))
                    elif mode=='scenario':
                        inflation_taux=(1+taux_applicable) ** indice

                # on applique le taux d'inflation et la part du syndicat à la valeur actuelle de l'intervention:
                if item[13]==0:
                    dep_actualisee = item[6] * inflation_taux
                else:# le syndicat paie une part jusqu'à 100% ou le coût d'intervention est partagé
                    if usager=='syndicat':
                        dep_actualisee = decimal.Decimal(item[6]) * decimal.Decimal(inflation_taux) * decimal.Decimal(item[13])
                    else:
                        dep_actualisee = decimal.Decimal(item[6]) * decimal.Decimal(inflation_taux) * (1-decimal.Decimal(item[13]))
                # on ajoute l'élément à la nouvelle liste
                # CONTENU DE L'AJOUT=  ref_analyse, desc_intervention, frequence, dep_actualisee, annee de l'intervention,
                # desc type intervention, description categorie, IDGroupe uniformat, description groupe uniformat, nom d'intervenant
                #
                ajout=(item[5],item[1],str(item[7]),str(round(dep_actualisee,2)),str(annee_traitee),\
                      item[14],item[15],str(item[16]),item[17],item[18])
                fill_dep_50ans.append(ajout)
        annee_traitee += 1
        indice += 1
    # tri de la table par ordre d'année croissante
    fill_dep_50ans.sort(key=lambda x: x[4])
    indices=(taux_infl_moyen_anal,croiss_ICC)
    res=[fill_dep_50ans,indices]

    return res

@bp_fonds_prevoyance.route('/depenses_fdp/<usager>', methods=['POST','GET'])
def depenses_fdp(usager):
    """afficher la page des dépenses du fonds de prévoyance aux admin selon usager
    'admin' ou 'coproprios'
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager (pas employé)
    if profile_list[2] == 3:
            return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]

     # ***************************préparation des données 25 ans du graphique histogramme de dépenses prévues
    # processus de programmation:
    # 1- appeler la fonction de calcul des interventions pour obtenir la liste complète 50 ans
    # 2- supprimer les éléments de la liste ayant un 'an_prochain' plus grand que la période voulue
    # 3- Créer les listes suivantes pour accumuler les données à afficher dans les graphiques:
    #       - étiquettes d'années selon 'ans_traites' (1 liste)
    #       - total annuel des valeurs actualisées pour les enregistrements pour chacun des 7 groupes Uniformat (7 listes)
    #       IMPORTANT: toutes ces listes doivent avoir le même nombre d'éléments pour faire coincider les étiquettes
    # 4- passer la liste dans une boucle avec 'ans_traites' croissants jusqu'au maximum
    #   - pour chaque année de calendrier:
    #       - multiplier la valeur de l'item par le taux d'inflation prévu selon le nombre d'années et selon la plage d'années applicables (0-5, 6-15, 16 et plus)
    #       - cumuler les enregistrements ayant le même groupe pour l'année en cours de traitement
    #       - ajouter ces cumuls à la liste du groupe applicable (voir item 8)

    #1 Fonction de calcul préalable
    if request.form.get('toggle')==None:
        entite='syndicat'
    else:
        entite='coproprios'

    # obtenir la liste des dépenses indexées pour prochains 50 ans
    #liste_parametres=[usager, mode, taux_inflation]
    parametres=[entite,'base',0]
    res=calcul_dep(parametres)
    fill_table=res[0]
    fill_dep=res[0]
    indices=res[1]
    taux_infl_moyen_anal=indices[0]
    croiss_ICC=indices[1]

    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    date_anal=datetime

    cur.execute("SELECT DateAnalPrevoyance, AccesLimCoprop FROM parametres WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        date_anal = item[0]
        # pour coproprios, vérifier si accès limité dans paramètres
        limite_acces = item[1]
    annee_anal = date_anal.year

    # 2- supprimer les éléments de la liste ayant un 'an_prochain' plus grand que la période de 25 ans
    indice = 0
    date_fin_brut = date_anal + relativedelta(years=24)
    annee_fin = date_fin_brut.year
    for item in fill_dep:
        #if item[4] > annee_fin:
        if item[4] > date_fin_brut.strftime('%Y'):
            del fill_dep[indice]
        indice += 1

    # 8- Créer les listes suivantes pour accumuler les données à afficher dans les graphiques:
    #    étiquettes d'années selon 'ans_traites'
    labels=[]
    # total annuel des valeurs actualisées pour chaque groupe Uniformat
    groupe_1=[]
    groupe_2 = []
    groupe_3 = []
    groupe_4 = []
    groupe_5 = []
    groupe_6 = []
    groupe_7 = []
    groupe_8 = [] #autres
    groupe_9 = []
    cum_total_mtce=0
    cum_total_rempl=0

   #       IMPORTANT: toutes ces listes doivent avoir le même nombre d'éléments pour faire coincider les étiquettes

    # 9- passer la liste dans une boucle avec 'ans_traites' croissants jusqu'au maximum
    #   - pour chaque année de calendrier:

    annee_en_cours=annee_anal
    indice=1
    dep_tot_10_ans=[]
    while annee_en_cours<=annee_fin:
        # étiquettes des années:
        labels.append(annee_en_cours)
        # valeurs affichées par groupe
        cum_1 = 0
        cum_2 = 0
        cum_3 = 0
        cum_4 = 0
        cum_5 = 0
        cum_6 = 0
        cum_7 = 0
        cum_8 = 0
        cum_9 = 0
        # CONTENU DE L'AJOUT=  0 ref_analyse, 1 desc_intervention, 2 frequence, 3 dep_actualisee, 4 annee de l'intervention,
        # 5 desc type intervention, 6 description categorie, 7 IDGroupe uniformat, 8 description groupe uniformat, 9 nom d'intervenant

        for item in fill_dep:
              if int(item[4])==int(annee_en_cours):
                # cumul valeurs actualisées par année selon groupe Uniformat

                if int(item[7]) == 1:
                    cum_1+= float(item[3])

                elif int(item[7]) == 2:
                    cum_2 += float(item[3])

                elif int(item[7]) == 3:
                    cum_3 += float(item[3])

                elif int(item[7]) == 4:
                    cum_4 += float(item[3])

                elif int(item[7]) == 5:
                    cum_5 += float(item[3])

                elif int(item[7]) == 6:
                    cum_6 += float(item[3])

                elif int(item[7]) == 7:
                    cum_7 += float(item[3])

                elif int(item[7]) == 8:
                    cum_8 += float(item[3])

                elif int(item[7]) == 9:
                    cum_9 += float(item[3])
                # cumul par type d'intervention (mtce ou remplacement)
                if item[5] == 'Maintenance':
                    cum_total_mtce += float(item[3])
                if item[5] == 'Remplacement':
                    cum_total_rempl += float(item[3])

        # cumul des dépenses totales prévues par année pour 10 ans pour graphique des actuelles vs. prévues
        cum_global_annee=cum_1+cum_2+cum_3+cum_4+cum_5+cum_6+cum_7+cum_8+cum_9
        if indice<11:
            ajout_annee=(annee_en_cours,int(cum_global_annee))
            dep_tot_10_ans.append(ajout_annee)


        # ajouter ces cumuls à la liste du groupe applicable
        groupe_1.append(int(cum_1))
        groupe_2.append(int(cum_2))
        groupe_3.append(int(cum_3))
        groupe_4.append(int(cum_4))
        groupe_5.append(int(cum_5))
        groupe_6.append(int(cum_6))
        groupe_7.append(int(cum_7))
        groupe_8.append(int(cum_8))
        groupe_9.append(int(cum_9))

        annee_en_cours+=1
        indice+=1

    # ***************************préparation des données 10 ans du graphique de courbes de dépenses actuelles vs. prévues

    fill_10_ans = []
    dep_10_ans=[]
    for item in dep_tot_10_ans:
        #print('item dans dep_tot-10ans:',item)
        fill_10_ans.append(item[0])
        dep_10_ans.append(item[1])
    #print ('liste 10 ans:',fill_10_ans)

    # obtenir dépenses des tickets fermés avec type de travail=2 (fonds de prévoyance)
    fill_tickets=[]
    cur.execute("SELECT DateComplet, CoutTotalTTC, IDCategorie FROM tickets WHERE TypeTravail=%s AND DateComplet>%s AND IDClient=%s",(2,date_anal,client_ident))
    for item in cur.fetchall():
        cur.execute("SELECT IDGroupe FROM categories WHERE IDCategorie=%s AND IDClient=%s",(item[2],client_ident))
        for row in cur.fetchall():
            # tenir compte des interventions dans parties communes à usage restreint ('Z') IDGroupe=9
            if entite=='syndicat' and row[0]!=9:
                ajout_ticket = (item[0].year, int(item[1]), row[0])
                fill_tickets.append(ajout_ticket)
            if entite == 'coproprios' and row[0] == 9:
                ajout_ticket = (item[0].year, int(item[1]), row[0])
                fill_tickets.append(ajout_ticket)

    groupe_1_act=[]
    groupe_2_act = []
    groupe_3_act = []
    groupe_4_act = []
    groupe_5_act = []
    groupe_6_act = []
    groupe_7_act = []
    groupe_8_act = []
    groupe_9_act = []

    for item in fill_10_ans:
        cum_dep_act_1 = 0
        cum_dep_act_2 = 0
        cum_dep_act_3 = 0
        cum_dep_act_4 = 0
        cum_dep_act_5 = 0
        cum_dep_act_6 = 0
        cum_dep_act_7 = 0
        cum_dep_act_8 = 0
        cum_dep_act_9 = 0
        for unit in fill_tickets:
            if unit[0]==item:
                  if unit[2]==1:
                      cum_dep_act_1+=unit[1]
                  if unit[2]==2:
                      cum_dep_act_2+=unit[1]
                  if unit[2]==3:
                      cum_dep_act_3+=unit[1]
                  if unit[2]==4:
                      cum_dep_act_4+=unit[1]
                  if unit[2]==5:
                      cum_dep_act_5+=unit[1]
                  if unit[2]==6:
                      cum_dep_act_6+=unit[1]
                  if unit[2]==7:
                      cum_dep_act_7+=unit[1]
                  if unit[2] == 8:
                      cum_dep_act_8 += unit[1]
                  if unit[2] == 9:
                      cum_dep_act_9 += unit[1]
        groupe_1_act.append(cum_dep_act_1)
        groupe_2_act.append(cum_dep_act_2)
        groupe_3_act.append(cum_dep_act_3)
        groupe_4_act.append(cum_dep_act_4)
        groupe_5_act.append(cum_dep_act_5)
        groupe_6_act.append(cum_dep_act_6)
        groupe_7_act.append(cum_dep_act_7)
        groupe_8_act.append(cum_dep_act_8)
        groupe_9_act.append(cum_dep_act_9)

#***************************remplissage de la table dynamique des dépenses prévues au bas de la page

    #vérifier si pour coproprios ou admin. Si coproprio, vérifier si accès limité dans paramètres
    if usager == 'coproprios':
        if limite_acces==1:
            return render_template('graph_fdp_dep_limite.html', labels=labels,
                                   values_1=groupe_1, values_2=groupe_2, values_3=groupe_3, values_4=groupe_4,
                                   values_5=groupe_5,
                                   values_6=groupe_6, values_7=groupe_7, values_8=groupe_8, values_9=groupe_9, fill_table=fill_table, labels_1=fill_10_ans,
                                   dep_prevues=dep_10_ans, toggle=entite,
                                   dep_grp_1=groupe_1_act, dep_grp_2=groupe_2_act, dep_grp_3=groupe_3_act,
                                   dep_grp_4=groupe_4_act, dep_grp_5=groupe_5_act, dep_grp_6=groupe_6_act,
                                   dep_grp_7=groupe_7_act, dep_grp_8=groupe_8_act, dep_grp_9=groupe_9_act,
                                   bd=profile_list[3])
        else: # pas de restriction
            return render_template('graph_fdp_dep_proprios.html', labels=labels, values_1=groupe_1, values_2=groupe_2,
                                   values_3=groupe_3,
                                   values_4=groupe_4, values_5=groupe_5, values_6=groupe_6, values_7=groupe_7, values_8=groupe_8,
                                   values_9=groupe_9, fill_table=fill_table, toggle=entite,
                                   labels_1=fill_10_ans, dep_prevues=dep_10_ans, dep_grp_1=groupe_1_act,
                                   dep_grp_2=groupe_2_act,
                                   dep_grp_3=groupe_3_act, dep_grp_4=groupe_4_act, dep_grp_5=groupe_5_act,
                                   dep_grp_6=groupe_6_act,
                                   dep_grp_7=groupe_7_act, dep_grp_8=groupe_8_act, dep_grp_9=groupe_9_act, bd=profile_list[3])

    if usager=='admin':
        return render_template('graph_fdp_dep_admin.html',labels=labels, values_1=groupe_1, values_2=groupe_2,values_3=groupe_3,
                               values_4=groupe_4,values_5=groupe_5,values_6=groupe_6,values_7=groupe_7,values_8=groupe_8,values_9=groupe_9,
                                fill_table=fill_table, toggle=entite,
                               labels_1=fill_10_ans, dep_prevues=dep_10_ans, dep_grp_1=groupe_1_act, dep_grp_2=groupe_2_act,
                               dep_grp_3=groupe_3_act, dep_grp_4=groupe_4_act, dep_grp_5=groupe_5_act, dep_grp_6=groupe_6_act,
                               dep_grp_7=groupe_7_act, dep_grp_8=groupe_8_act, dep_grp_9=groupe_9_act, bd=profile_list[3])

#****************************Page affichant le solde du fonds et les dépenses selon l'analyse ou la modélisation*******************
@bp_fonds_prevoyance.route('/calcul_solde/<args>', methods=['POST','GET'])
def calcul_solde(args):
    """afficher la page du solde du fonds de prévoyance
    args=[mode,usager]
    mode= base, scenario ou ajuste
    usager= admin ou coproprios
    """
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager (pas employé)
    if profile_list[2] == 3:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]

    # ***************************préparation des données 25 ans pour les graphiques selon le mode
    # processus de programmation:
    # 1- obtenir valeurs de paramètres et débuter avec l'année de la dernière analyse de fonds de prévoyance
    # 2- obtenir la liste des interventions actualisées sur 50 ans avec la fonction calcul
    # 3- Créer les listes suivantes pour accumuler les 4 ensembles de données à afficher dans les graphiques:
    #       - étiquettes d'années de 1 à 26 (1 liste)
    #       - total annuel des dépenses et du solde (base, scenario et ajuste)
    #    IMPORTANT: toutes ces listes doivent avoir le même nombre d'éléments pour faire coincider les étiquettes
    # 4- passer la liste dans une boucle avec 'ans_traites' croissants jusqu'au maximum
    #   - pour chaque année de calendrier et selon le mode:
    #       pour le calcul 'base':
    #       - multiplier la valeur de l'item par le taux d'inflation prévu selon le nombre d'années et selon la plage d'années applicables (0-5, 6-15, 16 et plus)
    #       pour le calcul 'ajusté':
    #      - multiplier la valeur de l'item par le taux d'inflation 'croiss_ICC' pour les 5 premières années et les taux applicables pour les périodes suivantes (6-15 et plus de 15)
    #       - pour les années 26 à 50, on utilise le taux 16 et plus
    #       pour le mode 'scenario':
    #       - multiplier la valeur de l'item par le taux d'inflation saisi par l'usager pour toutes les années
    #       calculer le solde du fonds en utilisant le taux de rendement moyen des paramètres ou le taux réel calculé pour les obligations du Canada
    #   - ajouter ces cumuls à la liste pour les 25 premières années
    # 5- Calculer les dépenses pour les années 26 à 50

    # on enlève les 'brackets', les apostrophes et les espaces dans la chaine 'args'
    print(args)
    mode=str()
    usager=str()
    if args.find("[")== -1:
        result = args.replace('(', '').replace(')', '').replace("'", '').replace(" ", '')
        result_list = result.split(',')
        print(result_list)
        mode = str(result_list[0])  # base, scenario ou ajuste
        usager = str(result_list[1])  # admin ou coproprios
    if args.find("(")== -1:
        result = args.replace('[', '').replace(']', '').replace("'", '').replace(" ", '')
        result_list = result.split(',')
        print(result_list)
        mode = str(result_list[0])  # base, scenario ou ajuste
        usager = str(result_list[1])  # admin ou coproprios


    # 1- obtenir valeurs de paramètres et débuter avec l'année de la dernière analyse de fonds de prévoyance
    mode_connexion=profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    date_anal = datetime
    solde_debut = int()
    date_deb_contrib = datetime
    contrib_annuelle = int()
    taux_contrib = float()
    taux_rendement = float()
    solde_act = int()
    date_solde_act = datetime
    taux_croiss_scenario=float()
    taux_contrib_affichable =float()
    taux_rendement_affichable=float()

    limite_acces = 0
    solde_actuel = 0
    date_solde_actuel = datetime
    # on va chercher les données dans les paramètres de la bd pour le solde du fonds
    cur.execute("SELECT SoldeFdsDateAnal, ContributionAnnuelle, TauxAnnuelCroissContribution, TauxRendementMoyenPlacements,"
        "DateAnalPrevoyance, AccesLimCoprop, SoldeFdsActuel, DateSoldeActuel FROM parametres WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        solde_debut = item[0]
        contrib_annuelle = item[1]
        # les taux sont enregistrés en % (e.g. 2.4 au lieu de 0,024)
        taux_contrib_affichable =item[2]
        taux_contrib = float(item[2])/100
        taux_rendement_affichable = item[3]
        taux_rendement = float(item[3])/100
        date_anal=item[4]
        limite_acces = item[5]
        solde_actuel=item[6]
        date_solde_actuel= item[7]
    mode_calcul='base'
    taux_infl_moyen=0 # pour mode de 'base'
    # selon la valeur du paramètre 'mode', on utilise les paramètres de la page web ou ceux de l'analyse du consultant
    if mode=='scenario_proprio' or mode=='scenario':
        mode_calcul='scenario'
        contrib_annuelle = int(request.form.get('contribution'))
        taux_contrib_affichable=request.form.get('taux_croiss_contrib')
        taux_contrib = float(request.form.get('taux_croiss_contrib'))/100
        taux_croiss_scenario= float(request.form.get('taux_inflation'))/100
        taux_infl_moyen_anal =float(request.form.get('taux_inflation'))/100
        taux_rendement_affichable = request.form.get('taux_rendement')
        taux_rendement= float(request.form.get('taux_rendement'))/100

        taux_infl_moyen=taux_infl_moyen_anal

    # 2- mettre tous les enregistrements de la table de fonds de prévoyance sur 50 ans dans une liste en excluant ceux qui ont une part du syndicat=0
    parametres=['syndicat', mode_calcul, taux_infl_moyen]
    # appel de fonction de calcul_dep
    res = calcul_dep(parametres)
    fill_dep = res[0]
    indices = res[1]
    taux_infl_moyen_anal = indices[0]
    croiss_ICC = indices[1]

    # 3- fixer le nombre d'années applicables au traitement
    per_selection = 50
    # on fixe l'année de traitement (année actuelle) au début de la période d'analyse, soit celle de la dernière analyse
    annee_chaine=date_anal.strftime("%Y%m%d")
    annee_actuelle=int(annee_chaine[0:4])
    annee_anal=int(annee_chaine[0:4])

    # 7- Créer les listes suivantes pour accumuler les données à afficher dans les graphiques:
    #    étiquettes d'années selon 'ans_traites'
    liste_annees = []
    # total annuel des valeurs actualisées
    # pour les courbes en trait continu (analyse et scénario)
    fill_dep_base = []
    fill_solde_base= []
    # pour les courbes en trait pointillé (ajusté)
    fill_dep_ajust = []
    fill_solde_ajust = []
    #       IMPORTANT: toutes ces listes doivent avoir le même nombre d'éléments pour faire coincider les étiquettes


    # 8- passer la liste dans une boucle avec 'ans_traites' croissants jusqu'au maximum
    #   - pour chaque année de calendrier:
    indice = 0
    inflation_taux = float()
    dep_tot_10_ans = []
    cum_plus_25_ans=0
    date_25 = date_anal + relativedelta(years=24)
    annee_25 = date_25.year
    solde_fds_an_act=0
    solde_fds_an_prec=int(solde_debut)
    fill_solde_actuel=[]

    # pour la boucle de calcul des dépenses:
    annee_traitement=annee_actuelle
    while annee_actuelle <= annee_25:
        if annee_actuelle==date_solde_actuel.year:
            fill_solde_actuel.append(solde_actuel)
        else:
            fill_solde_actuel.append(None)
        # calcul des dépenses de l'année en cours
        cum_dep_annee = 0
        for item in fill_dep:
            # # cumul valeurs actualisées pour 25 premières années
            if int(item[4]) == annee_actuelle:
                cum_dep_annee += float(item[3])

        # étiquettes des années:
        liste_annees.append(annee_actuelle)
        # ajouter ces cumuls à la liste du groupe applicable
        fill_dep_base.append(int(cum_dep_annee))

        #calcul du solde du fonds pour l'année en cours
        if indice==0:   #première année
            # contributions débutent le mois suivant la date d'analyse
            # convertir mois en numérique pour opération arithmétique
            mois_debut = int(date_anal.strftime("%m"))
            contrib_annee_act = int((contrib_annuelle/12) * (12 - mois_debut))
        elif indice==1:
            # on incrémente la contribution selon le taux de croissance annuel
            contrib_annee_act = int(contrib_annuelle * (1+taux_contrib))
        else:
            # on incrémente la contribution selon le taux de croissance annuel
            contrib_annee_act = int(contrib_annuelle * ((1+taux_contrib) ** (indice)))

        revenus_an_prec = int(solde_fds_an_prec * taux_rendement)

        #calcul du solde
        solde_fds_an_act = solde_fds_an_prec + contrib_annee_act + revenus_an_prec - int(cum_dep_annee)

        fill_solde_base.append(solde_fds_an_act)
        solde_fds_an_prec=int(solde_fds_an_act)

        # on incrémente les indices
        annee_actuelle += 1
        indice += 1


    # 9- **************** à partir de la 26ème année, on calcule le total des dépenses:

    # AVEC les $ actualisés
    # pour obtenir 50 intervalles incluant l'année de l'analyse
    cum_plus_25_ans = 0  # total non actualisé
    liste_plus_25_dep = []

    for item in fill_dep:
        if int(item[4]) >= annee_actuelle:
            cum_plus_25_ans += float(item[3])
            liste_plus_25_dep.append(float(item[3]))

    tot_dep_25_plus='{:,.2f}'.format(cum_plus_25_ans)+'$'

    nbre_annees=0
    cum_rendements=0
    rendement_oblig_cda = 0
    cur.execute("SELECT AnneeJanv, RendementMoyen FROM obligationscda3a5ans WHERE AnneeJanv IN ('%s','%s')",
                (annee_anal, datetime.now().year))
    for item in cur.fetchall():
        nbre_annees += 1
        cum_rendements += item[1]
    if nbre_annees > 0:
        rendement_oblig_cda = cum_rendements / nbre_annees
    else:
        rendement_oblig_cda = 0

    cnx.close()
    montant_solde = format(solde_actuel, ',d').replace(',', ' ') + '$'

    if mode_calcul == 'base':
        taux_infl_moyen=taux_infl_moyen_anal

    annee_debut_25_ans_plus=int(annee_actuelle)-1
    # liste pour remplir les champs de la page html
    fill_champs=[annee_debut_25_ans_plus, tot_dep_25_plus, len(liste_plus_25_dep), contrib_annuelle, taux_contrib_affichable , round(taux_infl_moyen*100,2),
                 taux_rendement_affichable, croiss_ICC, round(rendement_oblig_cda*100),1, montant_solde, date_solde_actuel]

    if mode=='base' or mode=='scenario':
        # vérifier si pour coproprios ou admin. Si coproprio, vérifier si accès limité dans paramètres
        if usager=='coproprios':
            if limite_acces == 1:
                return render_template('graph_fds_solde_limite.html', labels=liste_annees, values_1=fill_dep_base,
                                       values_2=fill_solde_base, values_3=fill_solde_actuel,
                                       fill_champs=fill_champs, bd=profile_list[3])
            else:  # pas de restriction
                return render_template('graph_fdp_solde_proprios.html', labels=liste_annees,values_1=fill_dep_base,values_2=fill_solde_base,
                               fill_champs=fill_champs,bd=profile_list[3])
        if usager=='admin':
            return render_template('graph_fdp_solde_admin.html', labels=liste_annees, values_1=fill_dep_base,
                                   values_2=fill_solde_base,
                                   fill_champs=fill_champs, bd=profile_list[3])
    else:
        # **********on continue pour le mode 'ajuste' qui utilisera les résultats du mode 'base' comme comparable
        # obtenir la liste des dépenses sur 50 ans selon le mode 'ajusté' utilisant les indices de ICC et d'obligations Canada de StatsCan

        parametres = ['syndicat', 'ajuste', 0]
        # appel de fonction de calcul_dep
        res = calcul_dep(parametres)
        fill_dep_ajust = res[0]
        indices = res[1]
        taux_infl_moyen_ajust = indices[0]
        croiss_ICC = indices[1]

        # cumuler les dépenses ajustées et les soldes par année
        annee_actuelle = annee_anal
        indice_ajust = 0
        solde_fds_an_prec = int(solde_debut)
        fill_solde_ajust = []
        fill_dep_ajust_par_an =[]
        while annee_actuelle <= annee_25:
            # calcul des dépenses de l'année en cours
            cum_dep_annee = 0
            for item in fill_dep_ajust:
                # # cumul valeurs actualisées pour 25 premières années
                if int(item[4]) == annee_actuelle:
                    cum_dep_annee += float(item[3])
            # ajouter ces cumuls à la liste du groupe applicable
            fill_dep_ajust_par_an.append(int(cum_dep_annee))
           # calcul du solde ajusté du fonds pour l'année en cours

            inflation_taux = float()
            dep_tot_10_ans = []
            cum_plus_25_ans = 0

            solde_fds_an_act = 0

            if indice_ajust == 0:  # première année
                # contributions débutent le mois suivant la date d'analyse
                # convertir mois en numérique pour opération arithmétique
                mois_debut = int(date_anal.strftime("%m"))
                contrib_annee_act = int((contrib_annuelle / 12) * (12 - mois_debut))
            elif indice_ajust == 1:
                # on incrémente la contribution selon le taux de croissance annuel
                contrib_annee_act = int(contrib_annuelle * (1 + taux_contrib))
            else:
                # on incrémente la contribution selon le taux de croissance annuel
                contrib_annee_act = int(contrib_annuelle * ((1 + taux_contrib) ** (indice_ajust)))

            revenus_an_prec = int(solde_fds_an_prec * rendement_oblig_cda)

            # calcul du solde
            solde_fds_an_act = solde_fds_an_prec + contrib_annee_act + revenus_an_prec - int(cum_dep_annee)
            #print(solde_fds_an_prec, contrib_annee_act,revenus_an_prec, cum_dep_annee, '=',solde_fds_an_act)
            fill_solde_ajust.append(solde_fds_an_act)
            solde_fds_an_prec = int(solde_fds_an_act)

            # on incrémente les indices
            annee_actuelle += 1
            indice_ajust += 1

        #  à partir de la 26ème année, on calcule le total des dépenses ajustées:
        # AVEC les $ actualisés
        # pour obtenir 50 intervalles incluant l'année de l'analyse
        cum_plus_25_ans = 0  # total non actualisé
        liste_plus_25_dep_ajust = []
        for item in fill_dep_ajust:
            if int(item[4]) >= annee_actuelle:
                cum_plus_25_ans += float(item[3])
                liste_plus_25_dep_ajust.append(float(item[3]))

        tot_dep_25_plus_ajust='{:,.0f}'.format(cum_plus_25_ans)+'$'

        # liste pour remplir les champs de la page html
        fill_champs = [annee_actuelle, tot_dep_25_plus_ajust, len(liste_plus_25_dep_ajust), contrib_annuelle,
                       round(taux_contrib * 100, 1), taux_infl_moyen_anal * 100,
                       round(taux_rendement * 100, 1), croiss_ICC, round((rendement_oblig_cda * 100), 1), montant_solde,
                       date_solde_actuel]

        # vérifier si pour coproprios ou admin.
        if usager == 'coproprios':
            return render_template('graph_fdp_solde_ajuste_proprios.html', labels=liste_annees, values_1=fill_dep_base,
                                   values_2=fill_solde_base, values_3=fill_dep_ajust_par_an, values_4=fill_solde_ajust,
                                   fill_champs=fill_champs,
                                   bd=profile_list[3])
        else:  # admin
            return render_template('graph_fdp_solde_ajuste_admin.html', labels=liste_annees, values_1=fill_dep_base,
                                   values_2=fill_solde_base,
                                   values_3=fill_dep_ajust_par_an, values_4=fill_solde_ajust, fill_champs=fill_champs,
                                   bd=profile_list[3])

@bp_fonds_prevoyance.route('/interventions_table', methods=['POST','GET'])
def interventions_table():
    """affichage de la page des interventions du fonds de prévoyance pour ajouts et modifs"""
    #permet de vérifier si les interventions saisies dans condofix correspondent au rapport du consultant pour FDP
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    if profile_list[2] == 3 or profile_list[2] == 5:
            return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    fill_table = []
    cur.execute("SELECT IDFondsPrevoyance, DescriptionDepense, TypeMtceRempl, IDCategorie, RefGroupeUniformat, RefAnalyse, ValeurActuelleInterv, "
        "FrequenceAns, AnProchain, IDIntervenant, CodeElementUniformat, PartSyndicat, Inflation5ans,"
                "Inflation6a15ans, InflationPlus15ans, IDEquipement, Actif FROM fondsprevoyance WHERE IDClient=%s",
        (client_ident,))
    type=str()
    categorie=str()
    groupe_unif=str()
    nom_interv=str()
    no_tag=0
    for item in cur.fetchall():
        if item[2] == 1:
            type = "Maintenance"
        elif item[2] == 2:
            type = "Remplacement"
        item+=(type,)#17
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s", (item[3], client_ident))
        for row in cur.fetchall():
            categorie = row[0]
        item += (categorie,)#18
        cur.execute("SELECT Descriptif FROM groupesuniformat WHERE IDGroupe=%s", (item[4],))
        for row_1 in cur.fetchall():
            groupe_unif = row_1[0]
        item+= (groupe_unif,)#19
        cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s", (item[9], client_ident))
        for row_2 in cur.fetchall():
            nom_interv = row_2[0]
        item += (nom_interv,)  # 20
        if item[15]==0 or item[15]==None:
            no_tag = ''
        else:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",
                        (item[15], client_ident))
            for row_3 in cur.fetchall():
                no_tag = str(row_3[0])+' '+row_3[1]
        item += (no_tag,)  # 21
        if item[16]==1:
            actif='oui'
        else:
            actif='non'
        item += (actif,)#22
        fill_table.append(item)
    cnx.close()
    #print('table interventions:',fill_table)
    return render_template('interventions_FDP_table.html', fill_table=fill_table, bd=profile_list[3])

@bp_fonds_prevoyance.route('/affiche_intervention', methods=['POST','GET'])
def affiche_intervention():
    """affichage de la page d'ajout d'intervention au fonds de prévoyance"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    if profile_list[2] == 3 or profile_list[2] == 5:
            return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    liste_intervenants=[]
    cur.execute("SELECT IDIntervenant, NomIntervenant,IDCategorie FROM intervenants WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_intervenants.append(row)
    liste_intervenants.sort(key=lambda tup: tup[1])
    liste_equipements = []
    cur.execute("SELECT NumTag, Nom, IDCategorie, IDEquipement FROM equipements WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)
    cnx.close()
    list_res_2 = set(map(lambda x: x[2], liste_equipements))
    list_categ_avec_tags = list(list_res_2)

    list_equip = [[(y[0], y[1]) for y in liste_equipements if y[2] == x] for x in list_categ_avec_tags]
    cnx.close()
    return render_template('intervention_fdp_ajout.html', liste_categories=liste_categories, liste_intervenants=liste_intervenants,bd=profile_list[3],
                           list_categ_avec_tags=json.dumps(list_categ_avec_tags),list_equip=json.dumps(list_equip))

@bp_fonds_prevoyance.route('/ajout_intervention', methods=['POST','GET'])
def ajout_intervention():
    """affichage de la page d'ajout d'intervention au fonds de prévoyance"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    if profile_list[2] == 3 or profile_list[2] == 5:
            return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    # pour tenir compte de checkbox 'aucun tag'
    if request.form.get('aucun_tag') == "1":
        tag_no = 0
    else:
        tag_no = request.form.get('tag')
    args_interv = request.form['interv'].replace('(', '').replace(')', '').split(',')
    id_interv = args_interv[0]

    id_equip = int()
    if tag_no==0:
        id_equip = 0
    else:
        cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s", (tag_no, client_ident))
        for item in cur.fetchall():
            id_equip = item[0]


    IDGroupeUniformat=0
    cur.execute("SELECT IDGroupe from categories WHERE IDCategorie=%s AND IDClient=%s", (request.form['categ'], client_ident))
    for row in cur.fetchall():
        IDGroupeUniformat=int(row[0])

    cur.execute('INSERT INTO fondsprevoyance (IDClient, IDIntervenant, IDCategorie, DescriptionDepense, TypeMtceRempl,'
                'RefGroupeUniformat, RefAnalyse, CodeElementUniformat, ValeurActuelleInterv, FrequenceAns, IDEquipement, PartSyndicat, AnProchain,'
                'Inflation5ans, Inflation6a15ans, InflationPLus15ans, Actif) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '
                '%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                [client_ident, id_interv, request.form['categ'], request.form['desc_travail'],
                 request.form['type'], IDGroupeUniformat, request.form['ref_anal'], request.form['code_uniformat'],
                 request.form['valeur_act'], request.form['freq'], id_equip, float(request.form['part_coprop'])/100, request.form['proch_annee'],
                 float(request.form['taux_0_5ans'])/100, float(request.form['taux_6_15ans'])/100, float(request.form['taux_15ans'])/100, 1])
    cnx.commit()
    cnx.close()
    return redirect(url_for("bp_fonds_prevoyance.interventions_table"))

@bp_fonds_prevoyance.route('/affiche_interv_modif/<id_interv>', methods=['POST','GET'])
def affiche_interv_modif(id_interv):
    """affichage de la page de modification d'intervention du fonds de prévoyance"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    if profile_list[2] == 3 or profile_list[2] == 5:
            return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fill_intervention = []
    tag_desc = str()
    tag_id = 0
    id_categorie = 0

    cur.execute('SELECT IDClient, IDIntervenant, IDCategorie, DescriptionDepense, TypeMtceRempl,'
        'RefGroupeUniformat, RefAnalyse, CodeElementUniformat, ValeurActuelleInterv, FrequenceAns, PartSyndicat, AnProchain,'
        'Inflation5ans, Inflation6a15ans, InflationPLus15ans, PageRapport, Actif, IDFondsPrevoyance, IDEquipement '
        'FROM fondsprevoyance WHERE IDFondsPrevoyance=%s AND IDClient=%s',(id_interv, client_ident))
    for row in cur.fetchall():
        PartSynd = float(row[10]) * 100
        row += (PartSynd,)
        Infl_0_5 = round(float(row[12]) * 100,2)
        row += (Infl_0_5,)
        Infl_6_15 = round(float(row[13]) * 100,2)
        row += (Infl_6_15,)
        Infl_15 = round(float(row[14]) * 100,2)
        row += (Infl_15,)

        if row[18] == None:
            row += ('',)
        else:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",
                        (row[18], client_ident))
            for item in cur.fetchall():
                tag_desc = str(item[0]) + ', ' + item[1]
                tag_id = item[0]
        fill_intervention.append(row)
        id_categorie = row[2]

    liste_intervenants = []
    cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE Actif=1 AND IDClient=%s",
                (client_ident,))
    for row_1 in cur.fetchall():
        liste_intervenants.append(row_1)
    liste_intervenants.sort(key=lambda tup: tup[1])
    liste_categories = []
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    liste_equipements = []
    liste_equip_en_cours = []

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

    return render_template('intervention_fdp_modif.html', fill_interv=fill_intervention,
                           liste_intervenants=liste_intervenants,
                           list_categ_avec_tags=json.dumps(list_categ_avec_tags), liste_categories=liste_categories,
                           list_equip=json.dumps(list_equip), liste_equip_en_cours=liste_equip_actuel,
                           tag_desc=tag_desc, tag_id=tag_id, bd=profile_list[3])


    # return render_template('intervention_fdp_modif.html', liste_categories=liste_categories, liste_intervenants=liste_intervenants,
    #                        fill_interv=fill_interv, list_equip=list_equip, bd=profile_list[3])

@bp_fonds_prevoyance.route('/modif_intervention/<id_interv>', methods=['POST','GET'])
def modif_intervention(id_interv):
    """traitement de modification d'intervention au fonds de prévoyance"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    if profile_list[2] == 3 or profile_list[2] == 5:
            return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    tag_no=0
    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1

    # pour tenir compte de checkbox 'aucun tag'
    if request.form.get('aucun_tag') == None:
        if request.form.get('tag') == None:
            tag_no = 0
        else:
            tag_no = request.form['tag']
    if request.form.get('aucun_tag') == "1":
        tag_no = 0

    no_equip = int()
    cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s", (tag_no, client_ident))
    for item in cur.fetchall():
        no_equip = item[0]

    IDGroupeUniformat = 0
    cur.execute("SELECT IDGroupe from categories WHERE IDCategorie=%s AND IDClient=%s",
                (request.form['categ'], client_ident))
    for row in cur.fetchall():
        IDGroupeUniformat = int(row[0])
    cur.execute("UPDATE fondsprevoyance SET IDIntervenant=%s, IDCategorie=%s, DescriptionDepense=%s, TypeMtceRempl=%s, "
                "RefGroupeUniformat=%s, RefAnalyse=%s, CodeElementUniformat=%s, ValeurActuelleInterv=%s, FrequenceAns=%s, "
                "PartSyndicat=%s, AnProchain=%s, Inflation5ans=%s, Inflation6a15ans=%s, InflationPLus15ans=%s, "
                "Actif=%s, IDEquipement=%s WHERE IDClient=%s AND IDFondsPrevoyance=%s",([request.form['interv'], request.form['categ'], request.form['desc_travail'],
                 request.form['type'], IDGroupeUniformat, request.form['ref_anal'], request.form['code_uniformat'],
                 request.form['valeur_act'], request.form['freq'], float(request.form['part_coprop']) / 100,
                 request.form['proch_annee'],
                 float(request.form['taux_0_5ans']) / 100, float(request.form['taux_6_15ans']) / 100,
                 float(request.form['taux_15ans']) / 100, val_actif, no_equip, client_ident, id_interv]))
    cnx.commit()
    cnx.close()
    return redirect(url_for("bp_fonds_prevoyance.interventions_table"))

@bp_fonds_prevoyance.route('/consultation')
def consultation():
    page_visee='104'
    titre='fds-prc3a9voyance-touchette-cossette-final.pdf'+"#"+'page='+page_visee
    # trouver répertoire de base
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # enlever le mot 'condofix' pour se retrouver au niveau de 'mysite'
    modified_dir = base_dir.replace('condofix', 'documentation\\Test_docs\\')

    chemin_doc = modified_dir + titre
    return send_file(chemin_doc, attachment_filename=titre)
    #return "../static/fds_prevoyancep.pdf#page=104"