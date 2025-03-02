from flask import Blueprint, render_template, session, request, redirect, url_for, flash
import mysql.connector
from io import StringIO
import unicodedata
import csv
from werkzeug.wrappers import Response
from werkzeug.utils import secure_filename
from datetime import datetime,timedelta
import os
import traceback
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from mysite_PA_july11.utils import connect_db, chemin_rep

bp_signalements = Blueprint('bp_signalements', __name__)

#page de la liste de signalements avec fonction 'créer ticket'
@bp_signalements.route("/signalements_table")
def signalements_table():
    """afficher la page de la table de signalements avec fonction de création de ticket à partir du signalement
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    fill_contacts=[]
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    # # sélectionner enregistrements des 2 derniers mois
    # dateheure = datetime.now()
    # date_debut = dateheure - timedelta(days=60)
    #date_hre = datetime.strptime(str(date_debut),"%Y-%m-%d")
    # sélection des enregistrements avec 'Actif'=1
    fill_signalements=[]
    cur.execute("SELECT IDSignalement, DateHeureSoumis, IDSujetSignalement, Unite, Courriel, Emplacement, Description, IDTicket, Actif from signalements "
        "WHERE Actif= %s AND IDClient=%s", (1, client_ident))
    for row in cur.fetchall():
        cur.execute("SELECT Description FROM sujetsignalement WHERE IDSujetSignalement=%s",(row[2],))
        for item in cur.fetchall():
            row+=item
        fill_signalements.append(row)
    return render_template('signalements_table.html', fill_signalements=fill_signalements, date_debut='', bd=profile_list[3])

#fonctions pour ajouter un signalement
@bp_signalements.route("/fiche_signalement")
def fiche_signalement():
    """Ouvrir la page de création d'un signalement par le copropriétaire"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    mode=profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    client_ident = profile_list[0]
    no_tel_1 = str()
    no_tel_2 = str()
    no_tel_3 = str()
    cur.execute("SELECT TelUrgence1, TelUrgence2, TelUrgence3 FROM parametres WHERE IDClient=%s",(client_ident,))
    for item in cur.fetchall():
        if item[0]!=None:
            no_tel_1=item[0]
        else:  no_tel_1=''
        if item[1] != None:
            no_tel_2 = item[1]
        else:
            no_tel_2 = ''
        if item[2]!=None:
            no_tel_3=item[2]
        else:  no_tel_3=''

    return render_template('signalement.html', no_tel_1=no_tel_1, no_tel_2=no_tel_2, no_tel_3=no_tel_3, bd=profile_list[3])

#fonctions pour ajouter un signalement
@bp_signalements.route("/signalement_ajout", methods=['POST'])
def signalement_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page de documentation"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident = profile_list[0]
    mode=profile_list[8]
    nom_client=profile_list[7]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    # sauvegarder le signalement
    date_hre = datetime.now() - timedelta(hours=5)
    date_hre = date_hre.strftime("%Y-%m-%d %H:%M")
    cur.execute(
        'INSERT INTO signalements (IDClient, DateHeureSoumis, IDSujetSignalement, Unite, Courriel, Emplacement, Description, Actif) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        [client_ident, date_hre, request.form['options_demande'], request.form['no_unite'], request.form['courriel'],
         request.form['emplacement'], request.form['desc_signalement'],1])
    cnx.commit()
    sujet=str()
    # description du sujet du signalement
    cur.execute("SELECT Description FROM sujetsignalement WHERE IDSujetSignalement=%s",(request.form['options_demande'],))
    for item in cur.fetchall():
        sujet=item[0]

    # vérifier paramètre d'envoi email pour chaque signalement
    envoi_email = int()
    email_list = []
    cur.execute("SELECT EnvoiEMailSignal,EmailSignalement FROM parametres WHERE IDClient=%s", (client_ident,))
    for item in cur.fetchall():
        envoi_email = item[0]
        email_a = item[1]
        email_list = email_a.split(',')
    cnx.close()

    if envoi_email==1: #paramètre activé
        no_unite=request.form['no_unite']
        emplacement=request.form['emplacement']
        description=request.form['desc_signalement']

        # préparation email


        yahoo_mail_user = 'condofix.ca@yahoo.com'
        yahoo_mail_password = 'spyvlumgfwscqfkc'
        #utiliser le mode 'mixed' au lieu de 'related' pour que les images jointes s'affichent dans IOS
        msg = MIMEMultipart('mixed')
        msg['Subject'] = "Signalement"
        msg['From'] = yahoo_mail_user

        html = """
        <html><body>
        <p><b>Catégorie du signalement:</b>&nbsp;{sujet}<br/>
        <b>Soumis par unité:</b>&nbsp;{no_unite}<br/>
        <b>Emplacement:</b>&nbsp;{emplacement}<br/>
        <b>Description:</b>&nbsp;{description}</p>
        </body></html>
        """

        html = html.format(sujet=sujet,no_unite=no_unite,emplacement=emplacement,description=description)

        # enregistrer le MIME pour l'HTML
        contenu = MIMEText(html, 'html')
        # attacher le contenu au 'container' du message
        msg.attach(contenu)

        # envoi du email
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

    return redirect(url_for('bp_documentation.docs_table_proprios'))

@bp_signalements.route('/creation_ticket_signalement/<id_signalement>', methods=['GET','POST'])
def creation_ticket_signalement(id_signalement):
    """Créer un ticket dans la table mysql suivi par retour à la page affichant les signalements"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    list_signalement=[]
    cur.execute("SELECT DateHeureSoumis, IDSujetSignalement, Unite, Courriel, Emplacement, Description from signalements "
                "WHERE IDSignalement=%s AND IDClient=%s",(id_signalement,client_ident))
    for row in cur.fetchall():
        list_signalement.append(row)
    date_prevue= datetime.now()+timedelta(days=6)
    cur.execute('INSERT INTO tickets (IDClient, Statut, Priorite, DatePrevue, IDSignalement, DateCreation, IDUsager, Emplacement, TypeTravail, Description_travail) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                 [client_ident, 2, 3, date_prevue.date(), id_signalement, datetime.now().date(), profile_list[1], list_signalement[0][4], 1, list_signalement[0][5]])
    cnx.commit()
    ident_ticket =int()
    # trouver le IDTicket de cet enregistrement (dernier dans la table)
    cur.execute("SELECT max(IDTicket) FROM tickets")
    for item in cur.fetchall():
        ident_ticket=item[0]

    # modifier le signalement pour ajouter le no. de ticket
    cur.execute("UPDATE signalements SET IDTicket=%s WHERE IDSignalement=%s AND IDClient=%s",[ident_ticket,id_signalement,client_ident])
    cnx.commit()
    cnx.close()

    return redirect(url_for('bp_tickets.affiche_ticket_en_cours',id_ticket=ident_ticket))

@bp_signalements.route('/archiver_signalement/<id_signalement>', methods=['GET','POST'])
def archiver_signalement(id_signalement):
    """rendre un signalement inactif  dans la table mysql suivi par retour à la page affichant les signalements"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    client_ident = profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("UPDATE signalements SET Actif=%s WHERE IDSignalement=%s AND IDClient=%s",[0,id_signalement,client_ident])
    cnx.commit()
    cnx.close()

    return redirect(url_for('bp_signalements.signalements_table'))

# affichage de la liste de signalements avec 'à partir de'
@bp_signalements.route("/afficher_de_date_2", methods=['POST','GET'])
def afficher_de_date_2():
    """afficher la page de la table de signalements à partir de date spécifiée
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident = profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    # # sélectionner enregistrements depuis date demandée
    date = request.form['date_debut']
    if date == '':
        flash('Vous devez sélectionner une date de début des signalements.', "warning")
        return redirect(url_for('bp_signalements.signalements_table'))
    # convertir date en datetime
    date_hre = datetime.strptime(date, "%Y-%m-%d")

    client_ident = profile_list[0]
    cnx = connect_db()
    cur = cnx.cursor()
    list_signalements = []
    cur.execute(
        "SELECT IDSignalement, DateHeureSoumis, IDSujetSignalement, Unite, Courriel, Emplacement, Description, IDTicket, Actif "
        "FROM signalements WHERE DateHeureSoumis>=%s AND IDClient=%s", (date_hre, client_ident))
    for row in cur.fetchall():
        cur.execute("SELECT Description from sujetsignalement WHERE IDSujetSignalement=%s", (row[2],))
        for item in cur.fetchall():
            row += item
        list_signalements.append(row)

    return render_template('signalements_table.html', fill_signalements=list_signalements, date_debut=date, bd=profile_list[3])
