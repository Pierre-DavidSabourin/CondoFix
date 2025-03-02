# -*- coding: utf-8 -*-
import sys

from flask import Blueprint, render_template,redirect,url_for,g,session,flash,request,redirect,send_from_directory
import csv
from tabulate import tabulate
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import traceback
import mysql.connector
from datetime import datetime,date
from mysite_PA_july11.utils import connect_db, chemin_rep

bp_rapports = Blueprint('bp_rapports', __name__)

# envoi du rapport d'activité
@bp_rapports.route("/envoi_rapport_activite/<dernier_envoi>/<type_usager>")
def envoi_rapport_activite(dernier_envoi,type_usager):
    """Préparation du rapport d'activité à partir de la table de tickets.

    * Sauvegarde de chacune des 3 parties du rapport en fichier csv
    * Préparation d'un fichier d'envoi sous forme html contenant les infos sommarisées
    * Envoi du rapport aux destinataires spécifiés dans les paramètres"""
    profile_list=session.get('ProfilUsager')
    client_ident= profile_list[0]
    mode = profile_list[8]
    nom_client =  profile_list[7]
    cnx = connect_db(mode)
    cur = cnx.cursor()

   #********************** table_1 *****************************************

    #tickets créés
    cur.execute("SELECT IDTicket, DateCreation, Description_travail FROM tickets WHERE DateCreation>%s AND IDClient=%s",(dernier_envoi,client_ident,))
    list_crees=[]
    for row in cur.fetchall():
        list_crees.append(row[0])
    tickets_crees=len(list_crees)

    #tickets complétés
    cur.execute("SELECT IDTicket FROM tickets WHERE DateComplet>%s AND IDClient=%s",(dernier_envoi,client_ident,))
    list_completes=[]
    for row in cur.fetchall():
        list_completes.append(row[0])
    tickets_completes=len(list_completes)

    #tickets_fermés
    cur.execute("SELECT IDTicket FROM tickets WHERE DateFermeture>%s AND IDClient=%s",(dernier_envoi,client_ident,))
    list_fermes=[]
    for row in cur.fetchall():
        list_fermes.append(row[0])
    tickets_fermes=len(list_fermes)

    #ouvrir un fichier csv en mode écriture pour chaque table du courriel ('w')

    f = open(chemin_rep(mode)+'documentation/'+ nom_client + '_docs'+'/statut_1.csv', 'w')
    # créer le writer
    writer = csv.writer(f)

    #insertion dans le fichier csv
    entete=['Créés','Complétés','Fermés']
    writer.writerow(entete)
    donnees=[tickets_crees,tickets_completes,tickets_fermes]
    writer.writerow(donnees)
    f.close()

        #*************** table 2  **********************
    cnx = connect_db(mode)
    cur = cnx.cursor()
    ticket_priorite_list = []
    count_prior1 = 0
    count_prior2 = 0
    count_prior3 = 0
    count_prior4 = 0
    count_tot_encours = 0
    cum_jrs_prior1 = 0
    cum_jrs_prior2 = 0
    cum_jrs_prior3 = 0
    cum_jrs_prior4 = 0
    cum_jrs_encours = 0
    moy_jrs_prior1 = 0
    moy_jrs_prior2 = 0
    moy_jrs_prior3 = 0
    moy_jrs_prior4 = 0
    cum_tot_tickets_1 = 0
    cum_tot_tickets_2 = 0
    cum_tot_tickets_3 = 0
    cum_tot_tickets_4 = 0
    cur.execute("SELECT Priorite, DatePrevue, Statut, IDTicket FROM tickets WHERE Statut=%s AND IDClient=%s", (2, client_ident,))
    for row in cur.fetchall():
        ticket_priorite_list.append(row)

    for item in ticket_priorite_list:
        # calcul du nombre de jours depuis date prévue
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

    if count_prior1 != 0:
        moy_jrs_prior1 = round(cum_jrs_prior1 / count_prior1, 1)
    if count_prior2 != 0:
        moy_jrs_prior2 = round(cum_jrs_prior2 / count_prior2, 1)
    if count_prior3 != 0:
        moy_jrs_prior3 = round(cum_jrs_prior3 / count_prior3, 1)
    if count_prior4 != 0:
        moy_jrs_prior4 = round(cum_jrs_prior4 / count_prior4, 1)
    if count_tot_encours != 0:
        moy_jrs_encours = int(cum_jrs_encours / count_tot_encours)

    #ouvrir un fichier csv en mode écriture pour chaque table du courriel ('w')
    f = open(chemin_rep(mode)+'documentation/'+ nom_client + '_docs'+'/statut_2.csv', 'w')
    # créer le writer
    writer = csv.writer(f)

    #insertion dans le fichier csv
    entete=[' ',' Tickets en cours ',' Dépassement moyen (j.) ']
    writer.writerow(entete)
    donnees_1=['Critique (4 h.)',cum_tot_tickets_1,moy_jrs_prior1]
    writer.writerow(donnees_1)
    donnees_2=['Élevée (48 h.)',cum_tot_tickets_2,moy_jrs_prior2]
    writer.writerow(donnees_2)
    donnees_3=['Moyenne (5 j.)',cum_tot_tickets_3,moy_jrs_prior3]
    writer.writerow(donnees_3)
    donnees_4=['Non prioritaire (15 j.)',cum_tot_tickets_4,moy_jrs_prior4]
    writer.writerow(donnees_4)
    f.close()

        # ***************************** table 3 ****************************
    cum_importants=0
    liste_importants=[]
    for item in ticket_priorite_list:
        # on va voir dans la première priorité
        if cum_importants<6:
            if item[0]==1:
                cum_importants+=1
                liste_importants.append(item[3])
    if cum_importants<6:
        # on va voir dans la deuxième priorité (Élevée)
        for item in ticket_priorite_list:
            if item[0]==2:
                cum_importants+=1
                liste_importants.append(item[3])
    if cum_importants<6:
        # on va voir dans la troisième priorité (moyenne)
        for item in ticket_priorite_list:
            if item[0]==3:
                cum_importants+=1
                liste_importants.append(item[3])
        # on ignore la quatrième priorité (non prioritaire)
    interv_nom=()
    list_tickets_importants=[]
    for item_1 in liste_importants:
        cur.execute("SELECT IDTicket, Description_travail, Emplacement, IDIntervenant, Priorite, DatePrevue FROM tickets WHERE IDTicket=%s AND IDClient=%s",(item_1,client_ident,))
        for row_1 in cur.fetchall():
            if row_1[3]!=None:
                cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s",(row_1[3],))
                for item in cur.fetchall():
                    interv_nom=item
            else:
                interv_nom =('Aucun',)
            row_1+=(interv_nom)
            cur.execute("SELECT Description FROM priorite WHERE IDPriorite=%s",(row_1[4],))
            for item in cur.fetchall():
                priorite_nom=item
                row_1+=(priorite_nom)
            list_tickets_importants.append(row_1)

    #ouvrir un fichier csv en mode écriture pour chaque table du courriel ('w')
    f = open(chemin_rep(mode)+'documentation/'+ nom_client + '_docs'+'/statut_3.csv', 'w')
    # créer le writer
    writer = csv.writer(f)
    #insertion dans le fichier csv
    entete=['No.','Description','Emplacement','Intervenant','Priorité','Date prévue']
    writer.writerow(entete)

    for item in list_tickets_importants:
        ligne_contenu=(item[0],item[1],item[2],item[6],item[7],item[5])
        writer.writerow(ligne_contenu)
    f.close()

    #aller chercher les tables csv créées pour insérer dans rapport
    with open(chemin_rep(mode)+'documentation/'+ nom_client + '_docs'+'/statut_1.csv') as input_file:
        reader_1 = csv.reader(input_file, delimiter=',')
        data_1 = list(reader_1)

    with open(chemin_rep(mode)+'documentation/'+ nom_client + '_docs'+'/statut_2.csv') as input_file:
        reader_2 = csv.reader(input_file, delimiter=',')
        data_2 = list(reader_2)

    with open(chemin_rep(mode)+'documentation/'+ nom_client + '_docs'+'/statut_3.csv') as input_file:
        reader_3 = csv.reader(input_file, delimiter=',')
        data_3 = list(reader_3)

    email_listing=str()
    cur.execute("SELECT EmailsRapport FROM parametres WHERE IDClient=%s",(client_ident,))
    for item in cur.fetchall():
        email_listing=item[0]

    yahoo_mail_user = 'condofix.ca@yahoo.com'
    yahoo_mail_password = 'spyvlumgfwscqfkc'

    email_list=email_listing.split(',')

    #Créer le 'container' du message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Rapport d'activité CondoFix pour "+profile_list[3]
    msg['From'] = 'condofix.ca@yahoo.com'

    html = """
    <html><body>
    <p>Rapport généré automatiquement par CondoFix</p>

    <h3 style="display:inline-block">Activité</h3>&nbsp;<p style="display:inline-block">Tickets depuis dernier rapport du {date_maj}:</p>
    <div style="border:black; border-width:1px; border-style:solid;">
    {table_1}
    </div>
    <h3 style="display:inline-block">Dépassement de délai prescrit</h3><p style="display:inline-block">&nbsp;Selon la date prévue:</p>
    <div style="border:black; border-width:1px; border-style:solid;">
    {table_2}
    </div>
    <h3>Pour action immédiate:</h3>
    <div style="border:black; border-width:1px; border-style:solid;">
    {table_3}
    </div>
    </body></html>
    """

    html = html.format(date_maj=dernier_envoi,table_1=tabulate(data_1, headers="firstrow", tablefmt="html",numalign="center"),
                       table_2=tabulate(data_2, headers="firstrow", tablefmt="html",numalign="center"),
                       table_3=tabulate(data_3, headers="firstrow", tablefmt="html",numalign="center"))
    # enregistrer le MIME pour l'HTML
    contenu=MIMEText(html,'html')
    # attacher le contenu au 'container' du message
    msg.attach(contenu)

    try:
        server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
        server.ehlo()
        server.login(yahoo_mail_user, yahoo_mail_password)
        # message MIME doit être expédié un destinataire à la fois (modifs serveur Yahoo fev 2024)
        print('email list:',email_list)
        for i in range(len(email_list)):
            print(email_list[i])
            server.sendmail(yahoo_mail_user, email_list[i], msg.as_string())
        server.close()

        #si l'envoi a réussi on met à jour la date dans les paramètres
        date_format = "%Y-%m-%d"
        date_now=str(date.today())
        date_envoye = datetime.strptime(date_now, date_format)
        #date_envoye = datetime.now().date
        cur.execute("UPDATE parametres SET DateRapportActivite=%s WHERE IDClient=%s", (date_envoye,client_ident))
        cnx.commit()
        cnx.close()

    except:
        print(traceback.format_exc())
    # coproprio
    if type_usager==5:
        return redirect(url_for('bp_documentation.docs_table_proprios'))
        #return redirect(url_for('bp_reservations.calendrier_rez',usager='proprio'))
    else:
        return redirect(url_for('bp_tickets.en_cours'))

