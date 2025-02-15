from flask import Blueprint, render_template,g,session,url_for,redirect,request
import mysql.connector
import collections
from collections import Counter

bp_sinistres = Blueprint('bp_sinistres', __name__)

#ouverture de la base de données principale
@bp_sinistres.route('/connect_db')
def connect_db():
    """Fonction de connexion à la base de données via objet mysql.connector.

| Requise pour chaque blueprint"""
    db=mysql.connector.connect(user='root', password='aholein1', host='127.0.0.1', database='condofix$condofix')

    #db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
    #host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$condofix')
    return db
#********************SINISTRES****************************************

#page de la liste de sinistres
@bp_sinistres.route("/sinistres_table")
def sinistres_table():
    """afficher la page de la table d'enregistrements
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    fill_sinistres=[]
    Interv=str()
    client_ident=profile_list[0]
    cnx = connect_db()
    cur = cnx.cursor()
    cur.execute("SELECT IDTicket,IDIntervenant, IntervenantAutre, DateCreation, Statut, Description_travail, Emplacement,"
                "DateComplet, DateFermeture, NoFacture, CoutTotalTTC from tickets WHERE TypeTravail=%s AND IDClient=%s",(5,client_ident,))
    for row in cur.fetchall():
        if row[1]==0 or row[1]=='':
            Interv=row[2]
        else:
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s and IDClient=%s",(row[1],client_ident))
            for item in cur.fetchone():
                Interv=item
            row += (Interv,)
        cur.execute("SELECT Description FROM statut WHERE IDStatut=%s",(row[4],))
        for item_1 in cur.fetchone():
            row += (item_1,)

        fill_sinistres.append(row)
    print('sinistres:',fill_sinistres)
    return render_template('sinistres_table.html', fill_sinistres=fill_sinistres,bd=profile_list[3])


