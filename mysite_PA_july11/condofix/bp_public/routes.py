from flask import Blueprint, render_template,url_for,session,flash,request,redirect, json
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
import mysql.connector
import traceback
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import unicodedata
import urllib.request
from pathlib import Path

bp_public = Blueprint('bp_public', __name__)

#ouverture de la base de données principale
def connect_dbase():
    """Fonction de connexion à la base de données via objet mysql.connector.

    | Requise pour chaque blueprint"""
    # vérifier si l'app est utilisé en dev (pycharm) ou en prod (QA,demo ou app chez PythonAnywhere (PA))
    environnement = Path.cwd()
    if 'home/CondoFix/QA' in str(environnement):
     env = 'QA'
    if 'home/CondoFix/mysite' in str(environnement):
     env = 'APP'
    if 'mysite_PA_july11' in str(environnement):
     env = 'DEV'

    if env=='DEV':
        db = mysql.connector.connect(user='root', password='aholein1', host='127.0.0.1', database='demo')
    else:
        db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
        host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$demo')
    return db

@bp_public.route('/info_visiteur/<page>')
# fonction d'enregistrement de données des visiteurs
def info_visiteur(page):

    # on exclut les visiteurs hors Canada du traitement
    if session.get('visiteur')=='Non_Canada':
        return ''
    cnx = connect_dbase()
    cur = cnx.cursor()
    #print ('contenu de session', session.get('visiteur'))
    ville=str()
    if session.get('visiteur')== None:
        # enregistrement de la session (visiteur)
        dateheure_debut=datetime.now()
        ville=str()
        # accès bd des emplacements d'URL
        GEO_IP_API_URL = 'http://ip-api.com/json/'
        # adresse URL du visiteur
        if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
            IP_TO_SEARCH = request.environ['REMOTE_ADDR']
        else:
            IP_TO_SEARCH = request.environ['HTTP_X_FORWARDED_FOR']  # if behind a proxy

        try:
            if IP_TO_SEARCH=='127.0.0.1':
                ville='Urbano'
            else:
                # Creating request object to GeoLocation API
                req = urllib.request.Request(GEO_IP_API_URL + IP_TO_SEARCH)
                # Getting in response JSON
                response = urllib.request.urlopen(req).read()
                # Loading JSON from text to object
                json_response = json.loads(response.decode('utf-8'))
                ville_brut = json_response['city']
                pays = json_response['country']
                if pays == 'Canada':
                    # enlever accents
                    ville = ''.join(
                        (c for c in unicodedata.normalize('NFD', ville_brut) if unicodedata.category(c) != 'Mn'))
                else:
                    ville = 'exclusion'
                    session['visiteur'] = 'Non_Canada'
        except:
            return ''

        # durée minimale de 10 secondes fixée pour la première page
        if ville != 'Sherbrooke':
            if ville != 'exclusion':
                cur.execute("INSERT INTO sessions (Date, DureeSecondes,IP,Ville,Pages) "
                                "VALUES (%s, %s, %s, %s, %s)",(dateheure_debut,10, IP_TO_SEARCH, ville,page,))
                cnx.commit()
                cum_pages=page
                # on insère la valeur du IDVisite dans les données de la session
                id_session=cur.lastrowid
                cum_pages=page
                session['visiteur'] = [id_session,dateheure_debut,cum_pages]
        else:
            return ''
    else:
        if ville != 'exclusion':
            params=session.get('visiteur')

            # on ajuste la durée de la session
            debut_session=params[1]
            ID=params[0]
            duree_maj=datetime.now().replace(tzinfo=None) -debut_session.replace(tzinfo=None)
            # on ajoute la nouvelle page visitée
            cum_pages=params[2]+'/ '+page
            # on modifie les paramètres de la session
            session['visiteur'][2]=cum_pages
            # on modifie l'enregistrement en cours
            cur.execute("UPDATE sessions SET Pages=%s, DureeSecondes=%s WHERE IDSession = %s",(cum_pages,duree_maj.seconds,ID,))
            cnx.commit()
    return ''

@bp_public.route('/')
#page d'acceuil sans menu opérationnel
def home():
    """Ouverture de la page de bienvenue visible par le public"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Accueil')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    #return render_template('-bienvenue_resp.html')
    return render_template('-bienvenue_new.html')
    # durant maintenance:
    #return render_template('-maintenance_en_cours.html')

@bp_public.route('/demande_info')
#page de demande d'information
def demande_info():
    """ouverture d'écran de saisie d'infos de contact disponible dans la partie publique de l'application"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Demande Infos')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return render_template('-demande_info.html')


@bp_public.route('/soumettre_info', methods=['POST', 'GET'])
#page de demande d'information
def soumettre_info():
    """envoi des données de demande de contact via email à l'équipe CondoFix et dans la bd démo"""
    # vérifier si le formulaire a été 'hacké' avec la longueurs des chaînes soumises
    if len(request.form['syndicat_nom']) > 40:
        flash("Les données soumises ne sont pas conformes.",'warning')
        return render_template('-demande_info.html')
    elif len(request.form['contact_nom']) > 40:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-demande_info.html')
    elif len(request.form['nbre_portes']) > 3:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-demande_info.html')
    elif len(request.form['contact_email']) > 40:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-demande_info.html')
    elif len(request.form['contact_tel']) > 12:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-demande_info.html')
    elif len(request.form['commentaires']) > 200:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-demande_info.html')


    # accès bd des emplacements d'URL
    GEO_IP_API_URL = 'http://ip-api.com/json/'
    # adresse URL du visiteur
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        IP_TO_SEARCH = request.environ['REMOTE_ADDR']
    else:
        IP_TO_SEARCH = request.environ['HTTP_X_FORWARDED_FOR']  # if behind a proxy


    try:
        # Creating request object to GeoLocation API
        req = urllib.request.Request(GEO_IP_API_URL + IP_TO_SEARCH)
        # Getting in response JSON
        response = urllib.request.urlopen(req).read()
        # Loading JSON from text to object
        json_response = json.loads(response.decode('utf-8'))
        ville = str()
        ville_brut = json_response['city']
        pays = json_response['country']
        if pays == 'Canada':
            ville=json_response['country']
            # enlever accents
            #ville = ''.join((c for c in unicodedata.normalize('NFD', ville_brut) if unicodedata.category(c) != 'Mn'))
    except:
        ville='Inconnue'

    #préparation et envoi du courriel à CondoFix
    nom_syndicat=request.form['syndicat_nom']
    nom_contact=request.form['contact_nom']
    note=request.form['commentaires']
    nbre_unites=request.form['nbre_portes']
    role=request.form.get('options_role')
    id_demande = request.form['options_demande']
    demande=str()
    email=request.form['contact_email']
    no_tel=request.form['contact_tel']

    if int(id_demande)==1:
        demande='Code pour démo'
    elif int(id_demande)==2:
        demande='Appel téléphonique'
    elif int(id_demande)==3:
        demande='Démo à distance'
    cnx = connect_dbase()
    cur = cnx.cursor()
    # enregistrer dans bd demo
    cur.execute("INSERT INTO demandes_info (Date, Nom, Syndicat, Ville, Portes, Courriel, Telephone, Role, TypeDemande,Commentaires) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [datetime.now(), nom_contact, nom_syndicat, ville, nbre_unites, email, no_tel, role, id_demande, note])
    cnx.commit()
    cnx.close()
    #envoi de courriel
    mail_to = 'donald.boileau@gmail.com,jaclus1111@icloud.com'
    email_list=mail_to.split(',')
    yahoo_mail_user = 'condofix.ca@yahoo.com'
    yahoo_mail_password = 'spyvlumgfwscqfkc'

    msg = MIMEMultipart("related")
    msg['Subject'] = 'Demande de prospect CondoFix'
    msg['From'] = yahoo_mail_user
    html = """
        <html><body>
        <p><b>Syndicat:</b>&nbsp;{nom_syndicat}<br/>
        <b>Soumis par:</b>&nbsp;{nom_contact}<br/>
        <b>Rôle:</b>&nbsp;{role}<br/>
        <b>Nombre de portes:</b>&nbsp;{nbre_unites}<br/>
        <b>Courriel:</b>&nbsp;{email}<br/>
        <b>Téléphone:</b>&nbsp;{no_tel}<br/>
        <b>Type de demande:</b>&nbsp;{demande}<br/>
        <b>Note:</b>&nbsp;{note}</p>
        </body></html>
        """

    html = html.format(nom_syndicat=nom_syndicat,nom_contact=nom_contact,role=role,nbre_unites=nbre_unites,email=email,
                       no_tel=no_tel,demande=demande,note=note)

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
        return render_template('-merci_demande_info.html')
    except:
        print(traceback.format_exc())
        return render_template('-merci_demande_info.html')

@bp_public.route('/produits')
#page 'produits'
def produits():
    """ouverture de la page publique décrivant les produits"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Offres')

    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return render_template('-offres.html')

@bp_public.route('/demarrage')
#page 'trousse de démarrage'
def demarrage():
    """PAGE ELIMINÉE ouverture de la page publique décrivant les produits"""
    info_visiteur('Produits')
    return render_template('-produits_resp.html')

@bp_public.route('/tarifs/<produit>')
#page 'tarifs' produit=1: essentiel  -2: plus
def tarifs(produit):
    """ouverture de la page publique pour le calcul de nos tarifs"""
    info_visiteur('Tarifs')
    choix=[]
    if produit=='1':
        choix=[1,0,0]
    if produit == '2':
        choix=[1,1,0]
    if produit == '3':
        choix=[1,1,1]

    return render_template('-tarifs_total.html', fill_tarifs=[], fill_visiteur=[], fill_choix=choix)

@bp_public.route('/calcul_tarifs', methods=['POST', 'GET'])
#page 'calcul tarifs'
def calcul_tarifs():
    # # pour éviter le choix de 2 produits simultanément
    # if request.form.get('carnet_essentiel')== 'on' and request.form.get('carnet_plus')== 'on':
    #     flash('Veuillez choisir une seule option (Carnet Entretien ou Carnet Plus) et saisir de nouveau le nombre de portes.', 'warning')
    #     return render_template('-tarifs_total.html', fill_tarifs=[], fill_visiteur=[], fill_choix=[1, 0, 0])
    # # pour éviter le choix de carnet essentiel avec réservations simultanément
    # if request.form.get('carnet_essentiel') == 'on' and request.form.get('rez') == 'on':
    #     flash("Le module de réservation est seulement disponible avec le Carnet Plus. Veuillez saisir de nouveau le nombre de portes.",
    #         'warning')
    #     return render_template('-tarifs_total.html', fill_tarifs=[], fill_visiteur=[], fill_choix=[1, 0, 0])

    """calculs du montant tatal avec taxes selon nombre de portes"""
    # obtenir profil du visiteur
    # accès bd des emplacements d'URL
    GEO_IP_API_URL = 'http://ip-api.com/json/'
    # adresse URL du visiteur

    # Can be also site URL like this : 'google.com'
    # IP_TO_SEARCH = request.environ['REMOTE_ADDR']#'70.50.162.182'

    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        IP_TO_SEARCH = request.environ['REMOTE_ADDR']
    else:
        IP_TO_SEARCH = request.environ['HTTP_X_FORWARDED_FOR']  # if behind a proxy

    try:
        # Creating request object to GeoLocation API
        req = urllib.request.Request(GEO_IP_API_URL + IP_TO_SEARCH)
        # Getting in response JSON
        response = urllib.request.urlopen(req).read()
        # Loading JSON from text to object
        json_response = json.loads(response.decode('utf-8'))

        pays = json_response['country']
        ville = json_response['city']

    except:
        ville='Inconnue'
        pays='Inconnu'

    nbre_portes = int(request.form['nbre_portes'])
    if nbre_portes != 0:
        regulier_plateforme = round(20 + (nbre_portes * 1.00), 2)
        promo_plateforme = round(regulier_plateforme * 0.65, 2)

        regulier_portail= round(nbre_portes * 0.75, 2)
        promo_portail = round(regulier_portail * 0.65, 2)

        promo_rez = round(nbre_portes * 0.65, 2)
        regulier_rez = round(nbre_portes * 0.65, 2)

        if request.form.get('rez') == None:
            if request.form.get('portail') == None:
                desc_rez = 'Non'
                desc_portail= 'Non'
                fill_tarifs = [('Plateforme CondoFix', format(promo_plateforme, '.2f'), format(regulier_plateforme, '.2f')),
                               ("Total", format(promo_plateforme, '.2f'), format(regulier_plateforme, '.2f'))]
                fill_choix = [1, 0, 0]
            else:
                desc_rez = 'Non'
                desc_portail = 'Oui'
                fill_tarifs = [('Plateforme CondoFix', format(promo_plateforme, '.2f'), format(regulier_plateforme, '.2f')),
                 ("Portail des copropriétaires", format(promo_portail, '.2f'), format(regulier_portail, '.2f')),
                 ("Total", format(promo_plateforme+promo_portail, '.2f'), format(regulier_plateforme+regulier_portail, '.2f'))]
                fill_choix = [1, 1, 0]
        else:
            desc_rez = 'Oui'
            desc_portail = 'Oui'
            fill_tarifs = [('Plateforme CondoFix', format(promo_plateforme, '.2f'), format(regulier_plateforme, '.2f')),
                 ("Portail des copropriétaires", format(promo_portail, '.2f'), format(regulier_portail, '.2f')),
                 ("Module Réservations", format(promo_rez, '.2f'), format(regulier_rez, '.2f')),
                 ("Total", format(promo_plateforme+promo_portail+promo_rez, '.2f'), format(regulier_plateforme+regulier_portail+regulier_rez, '.2f'))]

            fill_choix = [1, 1, 1]

        if request.form.get('rez') == None:
            module_rez = 0
        else:
            module_rez = 1
        fill_visiteur = [datetime.now().replace(microsecond=0), ville, pays, nbre_portes, module_rez]

        cnx = connect_dbase()
        cur = cnx.cursor()

        cur.execute("INSERT INTO demandes_info (Date, Ville, Portes, ModuleRez,TypeDemande) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    [datetime.now(), ville, request.form.get('nbre_portes'), module_rez, 5])
        cnx.commit()
        cnx.close()
        return render_template('-tarifs_total.html', fill_visiteur=fill_visiteur, fill_tarifs=fill_tarifs,
                           fill_choix=fill_choix)

    else:
        flash('Veuillez saisir un nombre de portes plus grand que 0.','warning')
        return render_template('-tarifs_total.html', fill_tarifs=[], fill_visiteur=[], fill_choix=[1, 0, 0])

    # # envoi d'email
    # date_tarifs=str(datetime.now().replace(microsecond=0))
    # # envoi de courriel
    # mail_to = 'donald.boileau@gmail.com,jaclus1111@icloud.com'
    # email_list = mail_to.split(',')
    # yahoo_mail_user = 'condofix.ca@yahoo.com'
    # yahoo_mail_password = 'spyvlumgfwscqfkc'
    #
    # msg = MIMEMultipart("related")
    # msg['Subject'] = 'Requête de tarifs'
    # msg['From'] = yahoo_mail_user
    # html = """
    #         <html><body>
    #         <p><b>Date:</b>&nbsp;{date}<br/>
    #         <b>Pays:</b>&nbsp;{pays}<br/>
    #         <b>Ville:</b>&nbsp;{ville}<br/>
    #         <b>Nombre de portes:</b>&nbsp;{nbre_portes}<br/>
    #         <b>Portail:</b>&nbsp;{desc_portail}<br/>
    #         <b>Réservations:</b>&nbsp;{desc_rez}<br/>
    #         </body></html>
    #         """
    #
    # html = html.format(date=date_tarifs, pays=pays, ville=ville, nbre_portes=nbre_portes, desc_portail=desc_portail, desc_rez=desc_rez )
    #
    # # enregistrer le MIME pour l'HTML
    # contenu = MIMEText(html, 'html')
    # # attacher le contenu au 'container' du message
    # msg.attach(contenu)
    # try:
    #     server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
    #     server.ehlo()
    #     server.login(yahoo_mail_user, yahoo_mail_password)
    #     # sendmail function takes 3 arguments: sender's address, recipient's address
    #     # and message to send - here it is sent as one string.
    #     for i in range(len(email_list)):
    #         server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
    #     server.quit()
    #     return render_template('-tarifs_total.html', fill_visiteur=fill_visiteur, fill_tarifs=fill_tarifs, fill_choix=fill_choix)
    #
    # except:
    #     print(traceback.format_exc())
     #   return render_template('-tarifs_total.html', fill_visiteur=fill_visiteur, fill_tarifs=fill_tarifs, fill_choix=fill_choix)


@bp_public.route('/carnet_entretien')
#page du carnet d'entretien
def carnet_entretien():
    """ouverture de la page publique carnet d'entretien et loi 16"""

    # enregistrement dans la bd 'sessions'
    info_visiteur('CarnetEntretien')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True

    return render_template('-carnet_entretien_resp.html')


@bp_public.route('/module_rez')
#page de 'module réservation'
def module_rez():
    """ouverture de la page publique du module de réservations"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Rez')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True

    return render_template('-module_rez.html')

@bp_public.route('/module_fdp')
#page de 'module de fonds de prévoyances'
def module_fdp():
    # enregistrement dans la bd 'sessions'
    info_visiteur('FDP')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True

    return render_template('-module_fdp.html')

@bp_public.route('/services')
#page de 'services'
def services():
    """ouverture de la page Importance du ticket"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Services')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return render_template('-services.html')

@bp_public.route('/agenda')
#page de 'carnet maison'
def agenda():
    """ouverture de la page Carnet Entretien Maison"""

    # enregistrement dans la bd 'sessions'
    info_visiteur('Agenda')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return render_template('-carnet_maison_resp.html')

@bp_public.route('/comptable')
#page de 'système comptable'
def comptable():
    """ouverture de la page Limites d'un système comptable"""

    # enregistrement dans la bd 'sessions'
    info_visiteur('SystComptable')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return render_template('-syst_comptable_resp.html')

@bp_public.route('/gmao')
#page de gmao
def gmao():
    """ouverture de la page Choix d'un GMAO"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('GMAO')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True

    return render_template('-gmao.html')

@bp_public.route('/demo')
#page d'accès à la demo
def demo():
    """ouverture de la page d'accès au demo"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Demo')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return redirect("https://demos-condofix.pythonanywhere.com/")

@bp_public.route('/quiz')
# #page du quiz
def quiz():
    # enregistrement dans la bd 'sessions'
    info_visiteur('Quiz')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return redirect("http://demos-condofix.pythonanywhere.com/quiz")

@bp_public.route('/blog')
def blog():
    # enregistrement dans la bd 'sessions'
    info_visiteur('Blog')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    """ouverture de la section blog"""
    return redirect (url_for('static', filename='blog/index.html'))

@bp_public.route('/video_infos', methods=['POST', 'GET'])
#page d'accès au vidéo
def video_infos():
    """ouverture de la page d'accès au vidéo"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Vidéo')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return render_template('-video_infos.html')

@bp_public.route('/affiche_video', methods=['POST', 'GET'])
#page d'affichage du vidéo
def affiche_video():
    """ouverture du vidéo"""
    # vérifier si le formulaire a été 'hacké' avec la longueurs des chaînes soumises
    if len(request.form['nom']) > 40:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-video_infos.html')
    elif len(request.form['portes']) > 3:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-video_infos.html')
    elif len(request.form['courriel']) > 40:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-video_infos.html')
    elif len(request.form['tel']) > 12:
        flash("Les données soumises ne sont pas conformes.", 'warning')
        return render_template('-video_infos.html')

    # on récupère les données
    # accès bd des emplacements d'URL
    GEO_IP_API_URL = 'http://ip-api.com/json/'

    # adresse URL du visiteur
    if request.environ.get('HTTP_X_FORWARDED_FOR') is None:
        IP_TO_SEARCH=request.environ['REMOTE_ADDR']
    else:
        IP_TO_SEARCH=request.environ['HTTP_X_FORWARDED_FOR']

    try:
        # Creating request object to GeoLocation API
        req = urllib.request.Request(GEO_IP_API_URL + IP_TO_SEARCH)
        # Getting in response JSON
        response = urllib.request.urlopen(req).read()
        # Loading JSON from text to object
        json_response = json.loads(response.decode('utf-8'))
        ville_brut = json_response['city']
        # # enlever accents
        ville = ''.join((c for c in unicodedata.normalize('NFD', ville_brut) if unicodedata.category(c) != 'Mn'))
    except:
        ville='Inconnue'

    cnx = connect_dbase()
    cur = cnx.cursor()
    cur.execute("INSERT INTO demandes_info (Date, Ville, Courriel, Syndicat, Portes, Telephone, TypeDemande) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [datetime.now(), ville, request.form['courriel'], request.form['nom'],
                 request.form['portes'], request.form['tel'], 4])
    cnx.commit()
    cnx.close()
    return render_template('-video_affiche.html')

# @bp_public.route('/affiche_video_OCR')
# def affiche_video_OCR():
#     # enregistrement dans la bd 'sessions'
#     info_visiteur('VideoOCR')
#     # pour permettre un maximum de 3 tentatives de saisie de login par session
#     session['solde_tentatives'] = 3
#     session['logged_in'] = False
#
#     # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
#     session.permanent = True
#     return render_template('-video_affiche_OCR.html')

@bp_public.route('/confidentialite')
def confidentialite():
    """ouverture de la page de la politique de confidentialité"""
    # enregistrement dans la bd 'sessions'
    info_visiteur('Confidentialité')
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True

    return render_template('-politique_confidentialite.html')


@bp_public.route('/attestation_home')
def attestation_home():
    # pour permettre un maximum de 3 tentatives de saisie de login par session
    session['solde_tentatives'] = 3
    session['logged_in'] = False

    # pour faire un timeout selon le nombre de minutes d'inactivité de l'usager (voir flask_app.py):
    session.permanent = True
    return "Bientôt: nouveau site de préparation d'attestation d'état de copropriété"
