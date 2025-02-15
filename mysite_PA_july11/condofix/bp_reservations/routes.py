from flask import Blueprint, render_template,session,url_for,redirect,request,flash,Markup
import mysql.connector
from datetime import datetime,timedelta
import pytz
from pytz import timezone
from dateutil.relativedelta import relativedelta
from io import StringIO
import unicodedata
import csv
from werkzeug.wrappers import Response
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback
from utils import connect_db



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


#page du calendrier de reservations avec fonction ajout
@bp_reservations.route("/calendrier_rez/<usager>")
def calendrier_rez(usager):
    """Afficher les réservations des copropriétaires à l'aide du calendrier javascript. Affiche
    seulement les enregistrements à partir de la date actuelle et permet d'ajouter une réservation.
    Application d'un code de couleur selon la ressource spécifiée"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier si le client a acheté le module réservations

    if profile_list[5] == 0:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    liste_ress_actives=[]

    # fixer couleurs pour chaque ressource active
    cur.execute("SELECT IDRessource,Description from ressources WHERE Actif=1 and IDClient=%s",(client_ident,))
    for item in cur.fetchall():
        liste_ress_actives.append(item)
    # s'assurer qu'il y a 10 items dans la liste
    while len(liste_ress_actives)<10:
                addition=(0,'')
                liste_ress_actives.append(addition)

    # obtenir réservations en cours à partir d'aujourd'hui
    cur.execute("SELECT IDReservation, IDRessource, Date, HeureDebut, DureeHres, NoUnite, Note from reservations "
                "WHERE Date>=%s AND IDClient=%s",(datetime.now().strftime('%Y-%m-%d'),client_ident))
    event={}
    events_list=[]
    for row in cur.fetchall():
        date_1=row[2]
        time_delta=row[3]
        date=str(date_1)
        time=str(time_delta)
        # régler problème avec heures ayant seulement 1 caractère (ex. 9:00 vs. 13:00)
        if time.index(':')==1:
            time_1=time[0]
            # formatter pour acceptation du module calendrier (boite noire)
            a = datetime(int(date[0:4]),int(date[5:7]), int(date[8:10]),int(time_1),int(time[2:4]),int(time[5:7]))
        else:
            time_1=time[0:2]
            a = datetime(int(date[0:4]),int(date[5:7]), int(date[8:10]),int(time_1),int(time[3:5]),int(time[6:8]))
        # la couleur de la ressource est fixée ici:
        indice=int()
        for t in liste_ress_actives:
            if t[0]==row[1]:
                event["no_unite"]=row[5]
                event["date_heure"]=a
                event["ressource"]=row[1]
                event["duree"]=row[4]
                #indice= liste_ress_actives.index(row[1])
                indice=liste_ress_actives.index(t)

        if indice==0:
            event["couleur"]='black'
        elif indice==1:
            event["couleur"]='lawngreen'
        elif indice==2:
            event["couleur"]='blue'
        elif indice==3:
            event["couleur"]='red'
        elif indice==4:
            event["couleur"]='orange'
        elif indice==5:
            event["couleur"]='pink'
        elif indice==6:
            event["couleur"]='lightslategrey'
        elif indice==7:
            event["couleur"]='magenta'
        elif indice==8:
            event["couleur"]='peru'
        elif indice==9:
            event["couleur"]='purple'
        events_list.append(event.copy())
    cnx.close()
    if usager=='admin':
        return render_template('calendrier_rez_admin.html', events_list=events_list,fill_ressources=liste_ress_actives,bd=profile_list[3])
    else:#proprio
        return render_template('calendrier_rez.html', events_list=events_list,fill_ressources=liste_ress_actives,bd=profile_list[3])

#fonctions pour afficher page d'ajout de rez
@bp_reservations.route("/reservation_affiche_admin", methods=['GET','POST'])
def reservation_affiche_admin():
    """Afficher l'écran pour effectuer une réservation pour l'admin"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si  admin condofix
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    fill_ressources=[]
    fill_modes_paiement=[]
    cur.execute("SELECT IDRessource,Description FROM ressources WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        fill_ressources.append(item)
    cur.execute("SELECT IDPaiement,Description FROM modepaiement WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        fill_modes_paiement.append(item)
    cnx.close()
    return render_template('reservation_ajout_admin.html',fill_ressources=fill_ressources, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])

#fonctions pour afficher page d'ajout de rez
@bp_reservations.route("/reservation_affiche_proprio", methods=['GET','POST'])
def reservation_affiche_proprio():
    """Afficher l'écran pour effectuer une réservation pour les copropriétaires.
    Les champs sont remplis selon les paramètres fixés pour la ressource sélectionnée dans le calendrier de réservations."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    fill_ressource=[]
    fill_modes_paiement=[]
    ident_ress=request.form.get('ress_select')
    desc_ressource=str()
    cur.execute("SELECT Description FROM ressources WHERE IDRessource=%s AND IDClient=%s", (ident_ress,client_ident))
    row = cur.fetchone()
    if row == None:  # pas d'enregistrement trouvé: on retourne au calendrier de réservation
        return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))
    else:
        desc_ressource=row[0]

    # pour remplir combo de mode de paiement
    cur.execute("SELECT IDPaiement,Description FROM modepaiement WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        fill_modes_paiement.append(item)

    # pour afficher un message avant de permettre la réservation
    message_affiche=0
    message_rez=str()
    cur.execute("SELECT AfficheMessageRez, MessageRez FROM parametres WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        if item[0]==1:
            message_affiche=1
            message_rez=item[1]

    # pour remplir les champs de date, heure et durée (déclarer variables globales)
    date_debut=datetime
    delai=int()
    hre_debut=datetime
    rez_duree=float()
    delai_min_hres=float()
    delai_max_jrs=0
    interv_rez_hres=float()
    hre_debut_permise = datetime
    # aller chercher la valeur des paramètres pour cette ressource
    cur.execute("SELECT  DureeMaxHres, DelaiMinHres, HreDebutPermise, HreFinPermise, DelaiMaxJrs, IntervalleRezHres FROM ressources WHERE Actif=1 "
                "AND IDRessource=%s AND IDClient=%s", (ident_ress, client_ident))
    for item in cur.fetchall():
        rez_duree=item[0]
        delai_min_hres=item[1]
        hre_debut_permise=item[2]
        hre_fin_permise=item[3]
        delai_max_jrs=item[4]
        interv_rez_hres=item[5]

    # 1- Pour la prod, convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
    # donne aussi l'heure locale sur l'environnement dev
    utc_time = datetime.utcnow()
    tz = pytz.timezone('America/Montreal')
    utc_time_1 =utc_time.replace(tzinfo=pytz.UTC) #replace method
    local_time=utc_time_1.astimezone(tz)
    dateheure=datetime.now()
    # 2- Ajouter le délai min en h. à l’heure actuelle de la demande = heure_act_delai
    heure_act_delai=local_time+timedelta(hours=delai_min_hres)
    #return 'delai:'+str(delai_min_hres)+'dateheure avec delai:'+str(heure_act_delai)

    # 3- Vérifier si heure act_delai de demande >paramètre heure début permise.
    # transformer hre_debut_permise dans paramètres en format datetime.time
    # par ex. selon que l'heure de début permise (dans bd) se lit '8:00'  ou '18:00'

    if len(str(hre_debut_permise).split(':')[0])==1:
        dateheure = datetime.strptime(str(hre_debut_permise),"%H:%M:%S")
    if len(str(hre_debut_permise).split(':')[0])==2:
        dateheure = datetime.strptime(str(hre_debut_permise),"%H:%M:%S")
    #heure_debut=dateheure.time()
    heure_debut = datetime.time(dateheure)
    #print('Dateheure:',dateheure)
    #print('heure début en datetime:', heure_debut)

    if heure_act_delai.time()>heure_debut:
        dateheure_act=heure_act_delai+timedelta(days=1)
        dateheure_dem=datetime.strptime(str(dateheure_act.date())+' '+str(heure_debut),"%Y-%m-%d %H:%M:%S")
    else:
        dateheure_dem=datetime.strptime(str(heure_act_delai.date())+' '+str(heure_debut),"%Y-%m-%d %H:%M:%S")

    # vérifier si conflit avec réservations actuelles (boucle):
    # requête des enregistrements de réservation pour cette ressource avec date >= date demandée
    liste_enreg=[]
    cur.execute("SELECT IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite FROM reservations WHERE IDRessource=%s AND Date>=%s AND IDClient=%s",
                (ident_ress, dateheure_dem.date(), client_ident))
    for row in cur.fetchall():
        date_1=row[2]
        time_delta=row[3]
        date=str(date_1)
        time=str(time_delta)
        enreg_time=datetime.strptime(date+' '+time,"%Y-%m-%d %H:%M:%S")
        de= enreg_time
        secondes_debut_enreg= float(de.timestamp())
        plage=float(row[4]*3600)
        secondes_fin_enreg=float(secondes_debut_enreg)+plage
        enreg=(secondes_debut_enreg,secondes_fin_enreg)
        liste_enreg.append(enreg)

    # si liste est vide, on va directement à l'affichage de la page de nouvelle réservation
    if len(liste_enreg)==0:
        # prévoir date avec délai minimum
        date_today=datetime.now().date()
        date_debut=date_today+timedelta(days=round(delai_min_hres/24))
        if message_affiche==0:
            return render_template('reservation_ajout_proprio.html', id_ress=ident_ress, desc_ressource=desc_ressource,
                               date=dateheure_dem.date(), heure=dateheure_dem.time(), duree=rez_duree, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])
        else:
            return render_template('reservation_ajout_proprio_message.html', id_ress=ident_ress, desc_ressource=desc_ressource,
                                   date=dateheure_dem.date(), heure=dateheure_dem.time(), duree=rez_duree,
                                   fill_modes_paiement=fill_modes_paiement, message_rez=message_rez, bd=profile_list[3])

    # la liste contient des réservations: trier la liste des enregistrements à partir d'aujourd'hui
    liste_enreg.sort( key=lambda tup: tup[0])
    cnx.close()
    compteur_jrs=0
    conflit=False

    # heure de réservation selon les jours consécutifs débutant à 0
    #rez_time = rez_time+timedelta(days=round(delai_min_hres/24,0))
    # secondes depuis 1970-01-01

    # pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
    # on retranche/ajoute l'intervalle exigé entre chaque réservation
    # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
    secondes_rez_debut = dateheure_dem.timestamp()-(float(interv_rez_hres)*3600)+1
    secondes_rez_fin = dateheure_dem.timestamp()+float(rez_duree*3600)+(float(interv_rez_hres)*3600)-2
    nbr_enreg=len(liste_enreg)
    # voir s'il y a chevauchement avec une réservation actuelle
    while compteur_jrs<delai_max_jrs:
        enreg_courant=0
        for item in liste_enreg:
            secondes_debut_enreg= item[0]
            secondes_fin_enreg=item[1]
            # ne pas traiter les enregistrements précédant la date rajustée avec compteurs jours
            if secondes_rez_debut>secondes_fin_enreg:
                enreg_courant+=1
                if enreg_courant==nbr_enreg: # pas d'enregistrement applicable à la demande, on sort de la boucle et on affiche la page de nouvelle rez
                    date_debut=dateheure_dem+timedelta(days=compteur_jrs)
                    if message_affiche == 0:
                        return render_template('reservation_ajout_proprio.html', id_ress=ident_ress, desc_ressource=desc_ressource, date=date_debut.date(),
                                       heure=date_debut.time(), duree=rez_duree, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])
                    else:
                        return render_template('reservation_ajout_proprio_message.html', id_ress=ident_ress,
                                        desc_ressource=desc_ressource, date=date_debut.date(),
                                        heure=date_debut.time(), duree=rez_duree,
                                        fill_modes_paiement=fill_modes_paiement, message_rez=message_rez, bd=profile_list[3])

                else:
                    continue


            # print('enreg:',secondes_debut_enreg, secondes_fin_enreg)
            # print('enreg:',datetime.fromtimestamp(secondes_debut_enreg),datetime.fromtimestamp(secondes_fin_enreg))
            # print('rez:',secondes_rez_debut, secondes_rez_fin)
            # print('rez:',datetime.fromtimestamp(secondes_rez_debut),datetime.fromtimestamp(secondes_rez_fin))
            # print('compteur:',compteur_jrs)

            if secondes_rez_debut<=secondes_debut_enreg<=secondes_rez_fin:
                conflit=True
            elif secondes_debut_enreg<=secondes_rez_debut<=secondes_fin_enreg:
                conflit=True

            if conflit==True:
                conflit=False
                compteur_jrs+=1
                # supprimer enregistrement de la liste pour éviter erreur de comparaison multiple

                #liste_enreg.remove(item)
                dr = dateheure_dem+timedelta(days=compteur_jrs)

                # secondes depuis 1970-01-01
                # pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
                # on retranche/ajoute l'intervalle exigé entre chaque réservation
                # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
                secondes_rez_debut = dr.timestamp()-(float(interv_rez_hres)*3600)+1
                secondes_rez_fin=dr.timestamp()+float(rez_duree*3600)+(float(interv_rez_hres)*3600)-2
                break
            else:
                date_debut=dateheure_dem+timedelta(days=compteur_jrs)
                if message_affiche == 0:
                    return render_template('reservation_ajout_proprio.html', id_ress=ident_ress, desc_ressource=desc_ressource, date=date_debut.date(),
                                       heure=date_debut.time(), duree=rez_duree, fill_modes_paiement=fill_modes_paiement, bd=profile_list[3])
                else:
                    return render_template('reservation_ajout_proprio_message.html', id_ress=ident_ress,
                                           desc_ressource=desc_ressource, date=date_debut.date(),
                                           heure=date_debut.time(), duree=rez_duree,
                                           fill_modes_paiement=fill_modes_paiement, message_rez=message_rez, bd=profile_list[3])

        # fin de la boucle WHILE compteur




#fonctions pour ajouter une réservations
@bp_reservations.route("/reservation_ajout_admin", methods=['POST'])
def reservation_ajout_admin():
    """Ajout d'une réservation à la table de la bd par l'admin. Si la réservation est facturable, un courriel
    est expédié aux destinataires spécifiés dans les paramètres."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si  admin condofix
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    # convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
    utc_time = datetime.utcnow()
    tz = pytz.timezone('America/Montreal')
    utc_time_1 =utc_time.replace(tzinfo=pytz.UTC) #replace method
    local_time=utc_time_1.astimezone(tz)

    # assembler les deux valeurs date et heure selon le bon format 'datetime'
    date_rez=request.form['date_rez']
    time_rez=request.form['heure_rez']
    rez_time = datetime(int(date_rez[0:4]),int(date_rez[5:7]),int(date_rez[8:10]),int(time_rez[0:2]),int(time_rez[3:5]))

    # savoir si facturable  pour cette ressource...aucune autre contrainte de réservation pour l'administrateur
    facturable=int()
    desc_ress=str()
    cur.execute("SELECT Facturable, Description FROM ressources WHERE IDRessource=%s AND IDClient=%s", (request.form['ress_select'],client_ident))
    for item in cur.fetchall():
        facturable=item[0]
        desc_ress=item[1]
    email_list=[]

    if request.form['mode_paiement']== '':
        mode_de_paiement=0
    else:
        mode_de_paiement=request.form['mode_paiement']

    # b) pour toute réservation (boucle): aucune vérification de chevauchement
    compteur_jrs=0
    while compteur_jrs<float(request.form['jrs_consecutifs']):
        date_rez_courante=rez_time+timedelta(days=compteur_jrs)
        heure_rez_courante=request.form['heure_rez']
        # ajout de la réservation
        cur.execute('INSERT INTO reservations (DateHeureCreation,IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, '
                    'Note, Courriel, ModePaiement) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    [local_time, request.form['ress_select'], client_ident, date_rez_courante, heure_rez_courante,
                     request.form['duree_rez'],request.form['no_unite'],request.form['note'],request.form['courriel'], mode_de_paiement])
        cnx.commit()
        compteur_jrs+=1

    #envoi de courriel d'alerte à l'adresse dans les paramètres
    cur.execute("SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",(client_ident,))
    for item in cur.fetchall():
        email_a=item[0]
        email_list=email_a.split(',')
    mode_text=str()
    cur.execute("SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s", (mode_de_paiement,client_ident))
    for item in cur.fetchall():
        mode_text = item[0]
    cnx.close()
    if facturable==1:
        yahoo_mail_user = 'condofix.ca@yahoo.com'
        yahoo_mail_password = 'spyvlumgfwscqfkc'

        no_unite=request.form['no_unite']
        date=request.form['date_rez']
        heure=request.form['heure_rez']
        duree=request.form['duree_rez']
        jours=request.form['jrs_consecutifs']
        courriel=request.form['courriel']
        note=request.form['note']
        mode_de_paiement=mode_text

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

        html = html.format(desc_ress=desc_ress,no_unite=no_unite,date=date,heure=heure,duree=duree,jours=jours,courriel=courriel,
                           mode_de_paiement=mode_de_paiement,note=note)

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

    return redirect(url_for('bp_reservations.reservations_table'))

#fonctions pour ajouter une réservations
@bp_reservations.route("/reservation_ajout_proprio", methods=['POST'])
def reservation_ajout_proprio():
    """Ajout d'une réservation à la table de la bd par les copropriétaires. Si la réservation est facturable, un courriel
     est expédié aux destinataires spécifiés dans les paramètres. Les réglages effectués par l'admin
     dans la table des ressources appliquent des restrictions sur l'acceptation d'une réservation et
     un message d'avertissement est affiché (flash message) dans la page reservation_ajout_proprio_mess expliquant la limitation."""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()

    # assembler les deux valeurs date et heure selon le bon format 'datetime'
    date_rez=request.form['date_rez']
    time_rez=request.form['heure_rez']
    rez_time = datetime(int(date_rez[0:4]),int(date_rez[5:7]),int(date_rez[8:10]),int(time_rez[0:2]),int(time_rez[3:5]))
    #convertir du type timezone naive à timezone aware pour calcul du delta
    rez_time_modif=rez_time.astimezone()

    # pour respecter l'heure locale: le serveur PythonAnywhere est a  Londres (heure utc)

    # convertir l'heure du serveur PythonAnywhere à l'heure locale en type timezone aware
    utc_time = datetime.utcnow()
    #tz = pytz.timezone('America/Montreal')
    tz = pytz.timezone('Europe/London')
    utc_time_1 =utc_time.replace(tzinfo=pytz.UTC) #replace method
    #local_time=utc_time_1.astimezone(tz)
    #local_time=utc_time.astimezone(tz)
    utcnow = timezone('utc').localize(datetime.utcnow()) # generic time
    local_time = utcnow.astimezone(timezone('America/Montreal'))




    utcnow = timezone('utc').localize(datetime.utcnow()) # generic time
    here = utcnow.astimezone(timezone('America/Montreal')).replace(tzinfo=None)
    there = utcnow.astimezone(timezone('utc')).replace(tzinfo=None)
    offset = relativedelta(there, here)
    time_diff_serv_pa=offset.hours
    #print(offset, time_diff)



    delta = rez_time_modif-local_time
    # délai de rez en heures avec 1 décimale
    delai_rez_hres=round(delta.total_seconds()/3600,3)+ round(time_diff_serv_pa,3)

    # print('time diff pa:',time_diff_serv_pa)
    # print('délai rez hres:',delai_rez_hres)


    # définition des variables pour qu'elles ne soient pas hors contexte
    desc_ress=str()
    facturable=0
    duree_max=0
    delai_min_h=0
    delai_max_j=0
    date_debut_non_dispo=str()
    duree_non_dispo=0
    jrs_consecutifs_permis=0
    interv_rez_hres=0
    hre_debut_permise=str()
    hre_fin_permise=str()
    # obtenir tous les paramètres pour cette ressource
    cur.execute("SELECT Description, Facturable, DureeMaxHres, DelaiMinHres, DelaiMaxJrs, DateDebutNonDispo, DureeNonDispoHres,"
                "JoursConsecutifsPermis, IntervalleRezHres, HreDebutPermise, HreFinPermise FROM ressources WHERE IDRessource=%s AND IDClient=%s", (request.form['ident_ress'],client_ident))
    for item in cur.fetchall():
        desc_ress=item[0]
        facturable=item[1]
        duree_max=float(item[2])
        delai_min_h=float(item[3])
        delai_max_j=float(item[4])
        date_debut_non_dispo=str(item[5])
        duree_non_dispo=item[6]
        jrs_consecutifs_permis=float(item[7])
        interv_rez_hres=item[8]
        hre_debut_permise=item[9]
        hre_fin_permise=item[10]

    # pour afficher les messages d'avertissement où l'usager a dépassé un paramètre
    # on affiche une page spéciale identique à 'nouvelle réservation' en utilisant le contenu des champs actuels dans une liste
    liste_rez=[request.form['ident_ress'], desc_ress, request.form['date_rez'],request.form['heure_rez'],request.form['duree_rez'],
               request.form['jrs_consecutifs'],request.form['no_unite'],request.form['courriel'],
               request.form['mode_paiement'],request.form['note']]
    avertissement=False # permet d'envoyer l'usager à la page d'avertissement
    message=str() # on accumule le texte des messages pour l'utiliser à la fin du processus de vérif
    fill_modes_paiement=[]
    # modes de paiement à retenir pour page ayant messages d'avertissement
    cur.execute("SELECT IDPaiement,Description from modepaiement WHERE IDClient=%s",(client_ident,))
    for item in cur.fetchall():
        fill_modes_paiement.append(item)

    # pour s'assurer que l'usager saisisse son courriel et le mode de paiement (rez facturable)
    if facturable==1:
        if request.form['courriel']=='':
            avertissement=True
            message=Markup("<b>Vous devez saisir votre courriel pour réserver une ressource facturable.</b><br>") \

        if request.form['mode_paiement']=='':
            avertissement=True
            message=message+Markup("<b>Vous devez saisir un mode de paiement pour réserver une ressource facturable.</b><br>") \

    # séquence de vérification pour accepter la réservation (rejet de la demande aussitôt qu'un critère n'est pas conforme):
    # a) peu importe le nombre de jours consécutifs demandés:
    # - voir si le nombre de jours consécutifs demandé dépasse le maximum permis
    # - vérifier si durée demandée est au-delà du maximum
    # - vérifier si le délai minimal est respecté (date de la première rez de la série consécutive)
    # - vérifier si le délai maximal est respecté (date de la dernière rez de la série consécutive)
    # - vérifier si l'heure demandée tombe entre l'heure début et de fin permise
    # - vérifier si la ressource est temporairement indisponible (date début + durée non dispo)

    # b) pour toute réservation :
    # - vérifier si l'intervalle entre les rez est respecté selon l'heure demandée
    # - voir s'il y a chevauchement avec une réservation actuelle

    # a) peu importe le nombre de jours consécutifs demandés:
    # 1- voir si le nombre de jours consécutifs demandé dépasse le maximum permis
    if float(request.form['jrs_consecutifs'])>jrs_consecutifs_permis:
        avertissement=True
        message=message+Markup("<b>Le nombre de jours consécutifs demandés excède celui fixé par le syndicat pour cette ressource soit de "+str(jrs_consecutifs_permis)+" jours.</b><br>") \

    # 2- vérifier si durée demandée est au-delà du maximum
    rez_duree=float(request.form['duree_rez'])
    if rez_duree>duree_max:
        avertissement=True
        message=message+Markup("<b>La durée demandée excède celle fixée par le syndicat pour cette ressource soit de "+str(duree_max)+" heures.</b><br>") \

    # 3- vérifier si délai minimal en heures est respecté
    if delai_rez_hres<delai_min_h:
        avertissement=True
        message=message+Markup("<b>La réservation demandée n'est pas conforme au délai minimal fixé par le syndicat pour cette ressource soit de "+str(float(delai_min_h))+" heures.</b><br>") \

    # 4- vérifier si délai maximal en jours est respecté
    delai_rez_avec_jrs_consec=delai_rez_hres/24+float(request.form['jrs_consecutifs'])-1
    if delai_rez_avec_jrs_consec>delai_max_j:
        avertissement=True
        message=message+Markup("<b>Le délai maximal pour la demande de réservation est plus long que celui fixé par le syndicat pour cette ressource soit de "+str(float(delai_max_j))+" jours.</b><br>") \

    # 5- vérifier si l'heure demandée tombe entre l'heure début et de fin permise
    # convertir heure de rez en datetime.datetime

    #print('heure brut:',request.form['heure_rez'])
    heure_brut=str(request.form['heure_rez'])
    heure_net=heure_brut[0:5]
    #print('heure net:',heure_net)
    hre_rez_datetime=datetime.strptime(heure_net, '%H:%M' )
    # vérifier si critère exigé pour cette ressource:
    if hre_debut_permise is not None:
        if hre_debut_permise!= timedelta(seconds=0):#='0:00:00' si remis à zéro par usager
            hre_debut_modif=hre_debut_permise
            # convertir heures permises de datetime.timedelta en str puis en datetime.datetime
            hre_debut_str=str(hre_debut_modif)
            hre_debut_datetime=datetime.strptime(hre_debut_str, '%H:%M:%S')
            if hre_rez_datetime<hre_debut_datetime:
                avertissement=True
                message=message+Markup("<b>L'heure de début demandée est plus tôt que celle fixée par le syndicat pour cette ressource soit "+str(hre_debut_permise)+".</b><br>") \

    if hre_fin_permise!=None:
        if hre_fin_permise!=timedelta(seconds=0):
            # enlever la durée de la rez de la date de début permise
            min_duree=rez_duree*60
            duree=timedelta(minutes = min_duree)
            hre_fin_modif=hre_fin_permise-duree
            # convertir heures permises moins durée de datetime.timedelta en str puis en datetime.datetime
            hre_fin_str=str(hre_fin_modif)
            hre_fin_datetime=datetime.strptime(hre_fin_str, '%H:%M:%S')
            if hre_rez_datetime>hre_fin_datetime:
                avertissement=True
                message=message+Markup("<b>L'heure de fin demandée (heure plus durée) tombe plus tard que celle fixée par le syndicat pour cette ressource soit "+str(hre_fin_permise)+".</b><br>") \

    # 6- vérifier si la ressource est temporairement indisponible (date début + durée non dispo)
    # vérifier si ces critères sont exigés pour cette ressource:
    if date_debut_non_dispo!='':
        if duree_non_dispo!=None or duree_non_dispo!='':
            # heure de réservation selon les jours consécutifs débutant à 0
            # secondes depuis 1970-01-01
            # période de réservation demandée
            # on ajoute et on retranche des secondes à la réservation pour éviter que les limites des heures se touchent
            secondes_rez_debut=rez_time.timestamp()+1
            # on ajoute la durée et les jours consécutifs (ajout de 0 jrs si jrs consécutifs=1)
            secondes_rez_fin=secondes_rez_debut+float(rez_duree*3600)+((float(request.form['jrs_consecutifs'])-1)*24*3600)-2


            print('Date non dispo:',date_debut_non_dispo)
            datetime_non_dispo=datetime(int(date_debut_non_dispo[0:4]),int(date_debut_non_dispo[5:7]),int(date_debut_non_dispo[8:10]))#,int(time_rez[0:2]),int(time_rez[3:5]))

            secondes_nondispo_debut=datetime_non_dispo.timestamp()
            secondes_nondispo_fin=secondes_nondispo_debut+float(duree_non_dispo*3600)

            # voir s'il y a chevauchement
            if secondes_rez_debut<=secondes_nondispo_debut<=secondes_rez_fin:
                avertissement=True
                message=message+Markup("<b>Cette ressource n'est pas disponible à partir du "+str(date_debut_non_dispo)+" pour "+str(duree_non_dispo)+" heures..</b><br>") \

            elif secondes_nondispo_debut<=secondes_rez_debut<=secondes_nondispo_fin:
                avertissement=True
                message=message+Markup("<b>Cette ressource n'est pas disponible à partir du "+str(date_debut_non_dispo)+" pour "+str(duree_non_dispo)+" heures.</b><br>") \


    # si le système a trouvé un conflit avec les paramètres, on affiche le ou les messages cumulés:
    if avertissement==True:
        message=message+Markup("Veuillez modifier les champs visés afin de compléter cette réservation.")
        flash(message,'warning')
        return render_template('reservation_ajout_proprio_mess.html',fill_rez=liste_rez,fill_modes=fill_modes_paiement)
    else:
        print(avertissement)

    # 7- vérification du chevauchement avec réservations existante:
    # on sauvegarde les réservations à venir dans une liste
    # requête des enregistrements de réservation pour cette ressource avec date >= date demandée
    liste_enreg=[]
    cur.execute("SELECT IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite FROM reservations WHERE IDRessource=%s AND Date>=%s AND IDClient=%s",
                    (request.form['ident_ress'], datetime.now(), client_ident))
    for row in cur.fetchall():
        liste_enreg.append(row)
    #print(liste_enreg)
    # début de la boucle
    compteur_jrs=0
    while compteur_jrs<float(request.form['jrs_consecutifs']):
        # heure de réservation selon les jours consécutifs débutant à 0
        dr = rez_time+timedelta(days=compteur_jrs)
        # secondes depuis 1970-01-01
        #print('counter:',compteur_jrs)

        # 7- pour vérifier si l'intervalle entre les rez est respecté selon l'heure demandée:
        # on retranche/ajoute l'intervalle exigé entre chaque réservation
        # et on ajoute et on retranche des secondes pour éviter que les limites des heures se touchent (si interval=0)
        secondes_rez_debut = dr.timestamp()-(float(interv_rez_hres)*3600)+1
        secondes_rez_fin=dr.timestamp()+float(rez_duree*3600)+(float(interv_rez_hres)*3600)-2

        # 8- voir s'il y a chevauchement avec une réservation actuelle

        for item in liste_enreg:
            date_1=item[2]
            time_delta=item[3]
            date=str(date_1)
            time=str(time_delta)
            # régler problème avec heures ayant seulement 1 caractère (ex. 9:00 vs. 13:00)
            if time.index(':')==1:
                time_1=time[0]
                time_2=time[2:4]
            else:
                time_1=time[0:2]
                time_2=time[3:5]

            enreg_time = datetime(int(date[0:4]),int(date[5:7]), int(date[8:10]),int(time_1),int(time_2))

            de= enreg_time
            secondes_debut_enreg= float(de.timestamp())
            plage=float(item[4]*3600)
            secondes_fin_enreg=float(secondes_debut_enreg)+plage

            if secondes_rez_debut<=secondes_debut_enreg<=secondes_rez_fin:
                if interv_rez_hres==0:
                    avertissement=True
                    message=message+Markup("<b>Cette ressource est déjà réservée par l'unité "+str(row[5])+".</b><br>") \

                else:
                    avertissement=True
                    message=message+Markup("<b>Cette réservation entre en conflit avec une autre réservation adjacente. Veuillez tenir compte de " \
                                   "l'intervalle de "+str(interv_rez_hres)+" heures exigé par le syndicat entre chaque réservation.</b><br>") \

            elif secondes_debut_enreg<=secondes_rez_debut<=secondes_fin_enreg:
                if interv_rez_hres==0:
                    avertissement=True
                    message=message+Markup("<b>Cette ressource est déjà réservée par l'unité "+str(row[5])+".</b><br>") \

                else:
                    avertissement=True
                    message=message+Markup("<b>Cette réservation entre en conflit avec une autre réservation adjacente. Veuillez tenir compte de " \
                                   "l'intervalle de "+str(interv_rez_hres)+" heures exigé par le syndicat entre chaque réservation.</b><br>")

            if avertissement==True:
                message=message+Markup("Veuillez modifier les champs visés afin de compléter cette réservation.")
                flash(message,'warning')
                return render_template('reservation_ajout_proprio_mess.html',fill_rez=liste_rez,fill_modes=fill_modes_paiement)

        compteur_jrs+=1

    if avertissement==False:
        compteur_jrs=0
        while compteur_jrs<float(request.form['jrs_consecutifs']):
            date_rez_courante=rez_time+timedelta(days=compteur_jrs)
            heure_rez_courante=request.form['heure_rez']

            # mode de paiement doit être un numérique
            if request.form['mode_paiement']=='':#champ vide
                mode_paiement=0
            else:
                mode_paiement=request.form['mode_paiement']
            # ajout de la réservation
            cur.execute('INSERT INTO reservations (DateHeureCreation,IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, Note, Courriel, ModePaiement) '
                        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                        [ local_time, request.form['ident_ress'], client_ident, date_rez_courante,heure_rez_courante,
                          request.form['duree_rez'],request.form['no_unite'],request.form['note'],request.form['courriel'],mode_paiement])
            cnx.commit()
            compteur_jrs+=1

    #envoi de courriel d'alerte à l'adresse dans les paramètres si rez facturable
    email_list=[]
    cur.execute("SELECT EmailRezFacturable FROM parametres WHERE IDClient=%s",(client_ident,))
    for item in cur.fetchall():
        email_a=item[0]
        email_list=email_a.split(',')

    if facturable==1:
        yahoo_mail_user = 'condofix.ca@yahoo.com'
        yahoo_mail_password = 'spyvlumgfwscqfkc'

        no_unite = request.form['no_unite']
        date = request.form['date_rez']
        heure = request.form['heure_rez']
        duree = request.form['duree_rez']
        jours = request.form['jrs_consecutifs']
        courriel = request.form['courriel']
        note = request.form['note']
        mode=request.form['mode_paiement']
        cur.execute("SELECT Description FROM modepaiement WHERE IDPaiement=%s AND IDClient=%s",
                    (mode, client_ident))
        for item in cur.fetchall():
            mode_de_paiement = item[0]

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

        html = html.format(desc_ress=desc_ress, no_unite=no_unite, date=date, heure=heure, duree=duree, jours=jours,
                           courriel=courriel, mode_de_paiement=mode_de_paiement, note=note)

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
        return redirect(url_for('bp_reservations.calendrier_rez',usager='proprio'))
    else:
        # pas facturable
        return redirect(url_for('bp_reservations.calendrier_rez', usager='proprio'))

# affichage de la page de 'mes reservations'
@bp_reservations.route("/mes_rez")
def mes_rez():
    """Afficher la page des réservations d'un copropriétaire selon leur numéro d'unité. Permet de supprimer
    une réservation."""
    return render_template('reservations_mon_unite.html')


#fonctions pour afficher les réservations d'une unité
@bp_reservations.route("/reservations_unite", methods=['POST','GET'])
def reservations_unite():
    """Afficher la page des réservations d'un copropriétaire selon leur numéro d'unité. Permet de supprimer
    une réservation."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    no_unite_rez=request.form['unite_no']
    liste_rez_unite=[]
    cur.execute("SELECT IDReservation, IDRessource, IDClient, Date, HeureDebut, DureeHres, NoUnite, Note FROM reservations "
                "WHERE Date>=%s AND NoUnite=%s AND IDClient=%s",(datetime.now().strftime('%Y-%m-%d'),no_unite_rez,client_ident))
    for row in cur.fetchall():
        cur.execute('SELECT Description FROM ressources WHERE IDRessource=%s AND IDClient=%s',(row[1],client_ident))
        for item in cur.fetchall():
            row+=(item)
        liste_rez_unite.append(row)
    cnx.close()
    # trier les réservations selon la date ascendante
    liste_rez_unite.sort( key=lambda tup: tup[3])
    return render_template('reservations_mon_unite.html',liste_rez_unite=liste_rez_unite)


#fonctions pour supprimer une réservations
@bp_reservations.route("/rez_unite_supprime/<id_rez>")
def rez_unite_supprime(id_rez):
    """À partir de la page 'mes réservations' supprimer un enregistrement affiché par un copropriétaire."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')

    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()

    id_ressource=0
    facturable=0
    date=''
    heure=''
    duree=0
    note=str()
    no_unite=0
    email=str()
    desc_ress=str()

    #trouver ressource de la réservation (premier élément des paramètres)
    cur.execute("SELECT IDRessource, Date, HeureDebut, DureeHres, NoUnite, Note from reservations WHERE IDReservation=%s AND IDClient=%s",(int(id_rez),client_ident))
    for item in cur.fetchall():
        id_ressource=item[0]
        date=str(item[1])
        heure=str(item[2])
        duree=str(item[3])
        note=item[5]
        no_unite=item[4]
    #trouver type de réservation (facturable)
    cur.execute("SELECT Facturable,Description from ressources WHERE IDRessource=%s AND IDClient=%s",(id_ressource,client_ident))
    for item_1 in cur.fetchall():
        facturable=item_1[0]
        desc_ress=item_1[1]
    # supprimer la réservation
    cur.execute("DELETE FROM reservations WHERE IDReservation=%s AND IDClient=%s",(int(id_rez),client_ident))
    cnx.commit()
    email_list=[]
    # si réservation est facturable, aviser de la suppression par email
    if facturable==1:
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
    return redirect(url_for('bp_reservations.calendrier_rez',usager='proprio'))


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
