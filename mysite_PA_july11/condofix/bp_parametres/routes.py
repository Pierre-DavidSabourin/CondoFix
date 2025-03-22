from flask import Blueprint, render_template,g,session,url_for,redirect,request,flash
import mysql.connector
import collections
from collections import Counter
from datetime import datetime
from utils import connect_db

bp_parametres = Blueprint('bp_parametres', __name__)

@bp_parametres.route('/parametres', methods=['POST', 'GET'])
def parametres():
    """Contrôle des paramètres de l'application
    1- disponible seulement à l'admin CondoFix
    2- les 3 onglets de paramètres: Réglages, profil d'immeuble et Salaires
    3- Réglages: paramètres importants de l'app.
    4- Profil d'immeuble: données permettant de contrôler l'affichage de la documentation (rapports obligatoires)
    5- Salaires: permet d'attribuer les salaires des employés à 4 catégories différentes
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]
    version_client = profile_list[6]

    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fill_parametres = []
    cur.execute(
        "SELECT Date_MAJ_Preventif,DateDebutBudget,CibleAgeMoyenTicket,DateAnalPrevoyance,DateCarnetEntretien,LieuSauvegardeNumeric,"
        "EmailRezFacturable,NbreUnites,NbreEtages,AnneeConstruit,ValeurRemplacement,NbreAscenseurs,StationnementUnEtage,"
        "StationnementMultiEtages,Gicleurs,SystLavageVitres,ChuteOrdures,Generatrice,PiscIneInt,PiscineExt,Spa,"
        "SalairesTotal, PartCateg_8, PartCateg_17, PartCateg_20, PartCateg_21, DateRapportActivite, EmailsRapport, FreqRapportActivite,"
        " DateAnalPrevoyance, SoldeFdsDateAnal, ContributionAnnuelle, TauxAnnuelCroissContribution, TauxRendementMoyenPlacements,"
        "SoldeFdsActuel, DateSoldeActuel, EnvoiEMailSignal,EmailSignalement, TelUrgence1, TelUrgence2, TelUrgence3, AccesLimCoprop,"
        "AfficheOcrTags, AfficheOcrTicketOuvert, Affiche_MDO_MAT, FranchiseAssurances, SoldeActuelFdsAssurance, DateAjoutSolde, "
        "MontantAjoutSolde, AlerteSolde, AlerteFreqSinistres, EncoursEmploye, AfficheMessageRez, MessageRez FROM parametres WHERE IDClient = %s", (client_ident,))
    for row in cur.fetchall():
        fill_parametres.append(row)
    cnx.commit()
    cnx.close()
    #return render_template('parametres_futur.html', version=version_client, fill_parametres=fill_parametres, bd=profile_list[3])
    return render_template('parametres.html', fill_parametres=fill_parametres, bd=profile_list[3])


@bp_parametres.route('/reglages_modif', methods=['POST'])
def reglages_modif():
    """met à jour les données de paramètres de l'application"""
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

    if request.form.get('affiche_encours_cell') == None:
        affiche_encours_empl = 0
    else:
        affiche_encours_empl = 1

    email_signal=request.form['email_signalement']
    if request.form.get('envoi_signalement') == None:
        envoi_signal = 0
    else:
        envoi_signal = 1

    tel_urgence_1=request.form['tel_urgence_1']
    tel_urgence_2 = request.form['tel_urgence_2']
    tel_urgence_3 = request.form['tel_urgence_3']

    cur.execute("UPDATE parametres SET DateDebutBudget=%s,CibleAgeMoyenTicket=%s, DateCarnetEntretien=%s,"
                "EmailsRapport=%s, FreqRapportActivite=%s, EnvoiEMailSignal=%s, EmailSignalement=%s, "
                "TelUrgence1=%s, TelUrgence2=%s, TelUrgence3=%s, EncoursEmploye=%s WHERE IDClient = %s",
                ([request.form['date_debut'], request.form['cible_age_moyen'],request.form['date_cahier_entretien'],
                  request.form['emails_rapport'], request.form['freq_rapport'],
                  envoi_signal, email_signal, tel_urgence_1,  tel_urgence_2, tel_urgence_3, affiche_encours_empl, client_ident]))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))


@bp_parametres.route('/profil_modif', methods=['POST', 'GET'])
def profil_modif():
    """met à jour les données du profil d'immeuble de l'application"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    usager_id = profile_list[1]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    desc_rapp = str()
    freq = int()
    if request.form.get('park_int_1') == None:
        parking_1etage = 0
    else:
        parking_1etage = 1

    if request.form.get('park_int_multi') == None:
        parking_multi = 0
    else:
        parking_multi = 1

    # vérifier si rapport inspection détecteurs CO existant (s'applique aux parkings à 1 ou plusieurs étages)
    cur.execute("SELECT IDDoc FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (4, client_ident))
    # rapport trouvé
    data = cur.fetchall()
    if len(data) > 0:
        if parking_1etage == 0 and parking_multi == 0:
            # suppression
            cur.execute("DELETE FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (4, client_ident))
            cnx.commit()
        # sinon, on laisse le rapport dans la bd
    else:  # rapport non trouvé
        if parking_1etage == 1 or parking_multi == 1:  # on ajoute le rapport obligatoire à la bd
            cur.execute("SELECT Description,FrequenceAns FROM rapportsobligatoires WHERE IDRappOblig=%s",(4,))
            for item in cur.fetchall():
                desc_rapp = item[0]
                freq = item[1]
            cur.execute("INSERT INTO documentation (IDClient, IDTypeDoc, IDRappOblig, IDUsager, Description, FrequenceAns) "
                "VALUES (%s, %s, %s, %s, %s, %s)", [client_ident, 1, 4, usager_id, desc_rapp, freq])
            cnx.commit()

    # vérifier si rapport inspection stationnement étagé existant (s'applique aux parkings à plusieurs étages)
    cur.execute("SELECT IDDoc FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (3, client_ident))
    # rapport trouvé
    data = cur.fetchall()
    if len(data) > 0:
        if parking_multi == 0:
            # suppression
            cur.execute("DELETE FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (3, client_ident))
            cnx.commit()
        # sinon, on laisse le rapport dans la bd
    else:  # rapport non trouvé
        if parking_multi == 1:  # on ajoute le rapport obligatoire à la bd
            cur.execute("SELECT Description,FrequenceAns FROM rapportsobligatoires WHERE IDRappOblig=%s", (3,))
            for item in cur.fetchall():
                desc_rapp = item[0]
                freq = item[1]
            cur.execute(
                "INSERT INTO documentation (IDClient, IDTypeDoc, IDRappOblig, IDUsager, Description, FrequenceAns) "
                "VALUES (%s, %s, %s, %s, %s, %s)", [client_ident, 1, 3, usager_id, desc_rapp, freq])
            cnx.commit()

    if request.form.get('gicleurs') == None:
        gicleurs = 0
    else:
        gicleurs = 1

    # vérifier si rapport inspection gicleurs existant
    cur.execute("SELECT IDDoc FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (5, client_ident))
    # rapport trouvé
    data = cur.fetchall()
    if len(data) > 0:
        if gicleurs== 0:
            # suppression
            cur.execute("DELETE FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (5, client_ident))
            cnx.commit()
        # sinon, on laisse le rapport dans la bd
    else:  # rapport non trouvé
        if gicleurs == 1:  # on ajoute le rapport obligatoire à la bd
            cur.execute("SELECT Description,FrequenceAns FROM rapportsobligatoires WHERE IDRappOblig=%s", (5,))
            for item in cur.fetchall():
                desc_rapp = item[0]
                freq = item[1]
            cur.execute(
                "INSERT INTO documentation (IDClient, IDTypeDoc, IDRappOblig, IDUsager, Description, FrequenceAns) "
                "VALUES (%s, %s, %s, %s, %s, %s)", [client_ident, 1, 5, usager_id, desc_rapp, freq])
            cnx.commit()

    if request.form.get('lavage_vitres') == None:
        lavage_vitres = 0
    else:
        lavage_vitres = 1

    # vérifier si rapport inspection supports de nacelle existant
    cur.execute("SELECT IDDoc FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (6, client_ident))
    # rapport trouvé
    data = cur.fetchall()
    if len(data) > 0:
        if lavage_vitres == 0:
            # suppression
            cur.execute("DELETE FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (6, client_ident))
            cnx.commit()
        # sinon, on laisse le rapport dans la bd
    else:  # rapport non trouvé
        if lavage_vitres == 1:  # on ajoute le rapport obligatoire à la bd
            cur.execute("SELECT Description,FrequenceAns FROM rapportsobligatoires WHERE IDRappOblig=%s", (6,))
            for item in cur.fetchall():
                desc_rapp = item[0]
                freq = item[1]
            cur.execute(
                "INSERT INTO documentation (IDClient, IDTypeDoc, IDRappOblig, IDUsager, Description, FrequenceAns) "
                "VALUES (%s, %s, %s, %s, %s, %s)", [client_ident, 1, 6, usager_id, desc_rapp, freq])
            cnx.commit()

    if request.form.get('chute_ordures') == None:
        chute_ordures = 0
    else:
        chute_ordures = 1

    if request.form.get('generatrice') == None:
        generatrice = 0
    else:
        generatrice = 1

    # vérifier si rapport inspection génératrice existant
    cur.execute("SELECT IDDoc FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (9, client_ident))
    # rapport trouvé
    data = cur.fetchall()
    if len(data) > 0:
        if generatrice == 0:
            # suppression
            cur.execute("DELETE FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (9, client_ident))
            cnx.commit()
        # sinon, on laisse le rapport dans la bd
    else:  # rapport non trouvé
        if generatrice == 1:  # on ajoute le rapport obligatoire à la bd
            cur.execute("SELECT Description,FrequenceAns FROM rapportsobligatoires WHERE IDRappOblig=%s", (9,))
            for item in cur.fetchall():
                desc_rapp = item[0]
                freq = item[1]
            cur.execute(
                "INSERT INTO documentation (IDClient, IDTypeDoc, IDRappOblig, IDUsager, Description, FrequenceAns) "
                "VALUES (%s, %s, %s, %s, %s, %s)", [client_ident, 1, 9, usager_id, desc_rapp, freq])
            cnx.commit()

    if request.form.get('piscine_int') == None:
        piscine_int = 0
    else:
        piscine_int = 1
    if request.form.get('piscine_ext') == None:
        piscine_ext = 0
    else:
        piscine_ext = 1
    if request.form.get('spa') == None:
        spa = 0
    else:
        spa = 1
    if int(request.form.get('nbre_etages')) >= 5:
        inspection_facade = 1
    else:
        inspection_facade = 0

    # vérifier si rapport inspection de façade existant
    cur.execute("SELECT IDDoc FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (1, client_ident))
    # rapport trouvé
    data = cur.fetchall()
    if len(data) > 0:
        if inspection_facade == 0:
            # suppression
            cur.execute("DELETE FROM documentation WHERE IDRappOblig=%s AND IDClient=%s", (1, client_ident))
            cnx.commit()
        # sinon, on laisse le rapport dans la bd
    else:  # rapport non trouvé
        if inspection_facade == 1:  # on ajoute le rapport obligatoire à la bd
            cur.execute("SELECT Description,FrequenceAns FROM rapportsobligatoires WHERE IDRappOblig=%s", (1,))
            for item in cur.fetchall():
                desc_rapp = item[0]
                freq = item[1]
            cur.execute(
                "INSERT INTO documentation (IDClient, IDTypeDoc, IDRappOblig, IDUsager, Description, FrequenceAns) "
                "VALUES (%s, %s, %s, %s, %s, %s)", [client_ident, 1, 1, usager_id, desc_rapp, freq])
            cnx.commit()

    cur.execute(
        "UPDATE parametres SET NbreUnites=%s,NbreEtages=%s,AnneeConstruit=%s,ValeurRemplacement=%s,NbreAscenseurs=%s,StationnementUnEtage=%s, "
        "StationnementMultiEtages=%s,Gicleurs=%s,SystLavageVitres=%s,ChuteOrdures=%s,Generatrice=%s,PiscIneInt=%s,PiscineExt=%s,Spa=%s WHERE IDClient = %s",
        ([request.form.get('nbre_unites'), request.form.get('nbre_etages'), request.form.get('annee_construit'),
          request.form.get('val_remplacement'),
          request.form.get('nbre_ascenseurs'), parking_1etage, parking_multi, gicleurs, lavage_vitres, chute_ordures,
          generatrice,
          piscine_int, piscine_ext, spa, client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))

@bp_parametres.route('/salaires_modif', methods=['POST'])
def salaires_modif():
    """met à jour les données de salaires d'employés et attribution par catégorie"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    total_categ = int(request.form.get('categ_8')) + int(request.form.get('categ_17')) + int(
        request.form.get('categ_20')) + int(request.form.get('categ_21'))
    if total_categ != 100:
        flash('Le total des pourcentages pour la répartition des salaires doit être égal à 100', 'warning')
        return redirect(url_for('bp_parametres.parametres'))
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute(
        "UPDATE parametres SET SalairesTotal=%s, PartCateg_8=%s, PartCateg_17=%s, PartCateg_20=%s, PartCateg_21=%s WHERE IDClient=%s",
        ([request.form.get('salaires'), request.form.get('categ_8'), request.form.get('categ_17'),
          request.form.get('categ_20'), request.form.get('categ_21'), client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))

@bp_parametres.route('/sinistres_modif', methods=['POST'])
def sinistres_modif():
    """met à jour les données de paramètres pour la gestion des sinistres"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    alerte_montant_fds=0
    alerte_frequence_sin=0
    if request.form.get('alerte_fds_ass') == None:
        alerte_montant_fds = 0
    else:
        alerte_montant_fds = 1
    if request.form.get('alerte_freq_sinistres') == None:
        alerte_frequence_sin = 0
    else:
        alerte_frequence_sin = 1
    date_dernier_ajout=datetime
    montant_ajout=0
    # obtenir la date du dernier ajout au solde de fonds d'assurance
    cur.execute("SELECT SoldeActuelFdsAssurance, DateAjoutSolde, MontantAjoutSolde FROM parametres WHERE IDClient=%s", (client_ident,))

    for item in cur.fetchall():
        if item[1]==None:
            # la rubrique est vide, on la met à '0'
            montant_ajout=0
        else:
            montant_ajout=item[1]
        if request.form['ajout_fonds_ass'] != '':
            date_dernier_ajout= datetime.now()
            montant_ajout=request.form['ajout_fonds_ass']

        else:
            date_dernier_ajout = item[0]

    cur.execute(
        "UPDATE parametres SET FranchiseAssurances=%s, SoldeActuelFdsAssurance=%s, DateAjoutSolde=%s, MontantAjoutSolde=%s, "
        "AlerteSolde=%s, AlerteFreqSinistres=%s WHERE IDClient = %s",
        ([request.form['franchise'], request.form['solde_fonds_ass'], date_dernier_ajout,
          montant_ajout, alerte_montant_fds, alerte_frequence_sin, client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))

@bp_parametres.route('/conformite_modif', methods=['POST'])
def conformite_modif():
    """met à jour les données de paramètres pour la conformité du syndicat"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fdp_limite=0
    if request.form.get('fdp_restreint') == None:
        fdp_limite = 0
    else:
        fdp_limite = 1
    cur.execute(
        "UPDATE parametres SET DateAnalPrevoyance=%s, SoldeFdsDateAnal=%s, ContributionAnnuelle=%s, TauxAnnuelCroissContribution=%s, "
        "TauxRendementMoyenPlacements=%s, SoldeFdsActuel=%s, DateSoldeActuel=%s, AccesLimCoprop=%s WHERE IDClient = %s",
        ([request.form['date_analyse_prevoyance'], request.form['solde_debut_anal'],
          request.form['contribution_annuelle'],
          request.form['taux_contribution'], request.form['taux_rendement'], request.form['solde_actuel'],
          request.form['date_solde_actuel'], fdp_limite, client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))


@bp_parametres.route('/fds_prevoyance_modif', methods=['POST'])
def fds_prevoyance_modif():
    """met à jour les données de paramètres pour le fonds de prévoyance de l'application"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    fdp_limite=0
    if request.form.get('fdp_restreint') == None:
        fdp_limite = 0
    else:
        fdp_limite = 1
    cur.execute(
        "UPDATE parametres SET DateAnalPrevoyance=%s, SoldeFdsDateAnal=%s, ContributionAnnuelle=%s, TauxAnnuelCroissContribution=%s, "
        "TauxRendementMoyenPlacements=%s, SoldeFdsActuel=%s, DateSoldeActuel=%s, AccesLimCoprop=%s WHERE IDClient = %s",
        ([request.form['date_analyse_prevoyance'], request.form['solde_debut_anal'],
          request.form['contribution_annuelle'],
          request.form['taux_contribution'], request.form['taux_rendement'], request.form['solde_actuel'],
          request.form['date_solde_actuel'], fdp_limite, client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))

@bp_parametres.route('/achalandage', methods=['POST', 'GET'])
def achalandage():
    """Graphiques sur l'achalandage du site par les usagers (logins)
    1- Histogramme pour derniers 12 mois
    2- Pie chart pour le cumulatif dès le début
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager (pas permis aux employés)
    if profile_list[2] == 3:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    list_logins = []
    type_usager=str()
    liste_etiq_cum = []
    liste_valeurs_cum = []

    total_logins=0
    date_debut=str()
    logins_type_2 = 0
    logins_type_3 = 0
    logins_type_4 = 0
    logins_type_5 = 0

    cur.execute("SELECT * FROM achalandage WHERE IDClient = %s", (client_ident,))
    for row in cur.fetchall():
        list_logins.append(row)
    cnx.close()

    # pie chart du cum des logins depuis début
    for item in list_logins:
        if item[2]==2:
            type_usager='Admin CondoFix'
            date_debut=str(item[15])
        elif item[2]==3:
            type_usager='Employés'
        elif item[2]==4:
            type_usager='Membres du CA'
        elif item[2]==5:
            type_usager='Copropriétaires'

        liste_etiq_cum.append(type_usager)
        liste_valeurs_cum.append(item[16])
        total_logins+=item[16]

    # histogramme des logins par mois par type
    labels_mois=['Jan','Fev','Mars','Avril','Mai','Juin','Juil','Août','Sept','Oct','Nov','Dec']
    for item in list_logins:
        if item[2]==2:
            logins_type_2=[item[3],item[4],item[5],item[6],item[7],item[8],item[9],item[10],item[11],item[12],item[13],item[14]]
        elif item[2]==3:
            logins_type_3=[item[3],item[4],item[5],item[6],item[7],item[8],item[9],item[10],item[11],item[12],item[13],item[14]]
        elif item[2]==4:
            logins_type_4=[item[3],item[4],item[5],item[6],item[7],item[8],item[9],item[10],item[11],item[12],item[13],item[14]]
        elif item[2]==5:
            logins_type_5=[item[3],item[4],item[5],item[6],item[7],item[8],item[9],item[10],item[11],item[12],item[13],item[14]]

    return render_template('achalandage.html', liste_etiq_cum=liste_etiq_cum, liste_valeurs_cum=liste_valeurs_cum, total_logins=total_logins,
                           date_debut=date_debut, labels_mois=labels_mois, logins_type_5=logins_type_5, logins_type_4=logins_type_4,
                           logins_type_3=logins_type_3, logins_type_2=logins_type_2, bd=profile_list[3])

@bp_parametres.route('/factures_OCR_modif', methods=['POST'])
def factures_OCR_modif():
    """met à jour les données de paramètres pour le fonds de prévoyance de l'application"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    # trouver le mode de connexion (Dev ou sur serveur PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    if request.form.get('tags_affiche') == None:
        aff_tags = 0
    else:
        aff_tags = 1
    # if request.form.get('taxes_affiche') == None:
    #     aff_taxes = 0
    # else:
    #     aff_taxes = 1
    if request.form.get('ticket_ouvert_affiche') == None:
        aff_ouvert = 0
    else:
        aff_ouvert = 1
    if request.form.get('MDO_MAT_affiche') == None:
        aff_MDO_MAT = 0
    else:
        aff_MDO_MAT= 1
    # case taxes éliminée pour le moment
    # cur.execute(
    #     "UPDATE parametres SET AfficheOcrTags=%s, AfficheOcrTaxes=%s, AfficheOcrTicketOuvert=%s, Affiche_MDO_MAT=%s WHERE IDClient = %s",
    #     ([aff_tags, aff_taxes, aff_ouvert, aff_MDO_MAT, client_ident]))
    cur.execute(
        "UPDATE parametres SET AfficheOcrTags=%s, AfficheOcrTicketOuvert=%s, Affiche_MDO_MAT=%s WHERE IDClient = %s",
        ([aff_tags, aff_ouvert, aff_MDO_MAT, client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))

@bp_parametres.route('/reservations_modif', methods=['POST'])
def reservations_modif():
    """met à jour les données de paramètres de l'application"""
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

    if request.form.get('affiche_message_rez') == None:
        affiche_message_rez = 0
    else:
        affiche_message_rez = 1

    message_rez=request.form['message_rez']
    email_facturable=request.form['email_facturable']

    cur.execute(
        "UPDATE parametres SET AfficheMessageRez=%s, MessageRez=%s, EmailRezFacturable=%s WHERE IDClient = %s",
        ([affiche_message_rez, message_rez, email_facturable, client_ident]))

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_parametres.parametres'))