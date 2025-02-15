#ouverture de la base de données principale selon l'environnement
import mysql.connector

def connect_db(mode):
    """Fonction de connexion à la base de données via objet mysql.connector.

    | Requise pour chaque blueprint"""
    if mode=='DEV':
        db=mysql.connector.connect(user='root', password='aholein1', host='127.0.0.1', database='condofix$condofix')
        return db
    if mode=='QA' or mode=='APP':
        db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
        host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$condofix')
        return db
    if mode=='DEMO':
        db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
        host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$demo')
        return db

def chemin_rep(mode):

    if mode== 'DEV':
        return str('C:/Users/Donal/Documents/Projets Programmation/mysite_PA_july11/')

    if mode == 'QA':
        return str('/home/CondoFix/QA/')

    if mode == 'DEMO':
        return str('/home/CondoFix/demo/')

    if mode == 'APP':
        return str('/home/CondoFix/mysite/')

def chemin_factures(mode,option,nom_client):
    if mode== 'DEV':
        if option == 'ocr':
            return 'C:/Users/Donal/Documents/Projets Programmation/mysite_PA_july11/condofix/static/temp_images/'
        if option == 'facture':
            return 'C:/Users/Donal/Documents/Projets Programmation/mysite_PA_july11/documentation/' + nom_client + '_docs/Factures/'

    if mode == 'QA':
        if option == 'ocr':
            return str('/home/CondoFix/QA/condofix/static/temp_images/')
        if option == 'facture':
            return str('/home/CondoFix/QA/documentation/'+nom_client+'_docs/Factures/')

    if mode == 'DEMO':
        if option == 'ocr':
            return str('/home/CondoFix/demos/condofix/static/temp_images/')
        if option == 'facture':
            return str('/home/CondoFix/demos/documentation/'+nom_client+'_docs/Factures/')

    if mode == 'APP':
        if option == 'ocr':
            return str('/home/CondoFix/mysite/condofix/static/temp_images/')
        if option == 'facture':
            return str('/home/CondoFix/mysite/documentation/' + nom_client + '_docs/Factures/')

def chemin_temp_images(mode):

    if mode== 'DEV':
        return str('C:/Users/Donal/Documents/Projets Programmation/mysite_PA_july11/condofix/static/temp_images/')

    if mode == 'QA':
        return str('/home/CondoFix/QA/condofix/static/temp_images/')

    if mode == 'DEMO':
        return str('/home/CondoFix/demo/condofix/static/temp_images/')

    if mode == 'APP':
        return str('/home/CondoFix/mysite/condofix/static/temp_images/')