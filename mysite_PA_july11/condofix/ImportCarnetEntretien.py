# -*- coding: utf-8 -*-

__author__ = 'donald'

import sqlite3
import csv
import mysql.connector

def connect_db():
    db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
    host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$condofix')
    return db

# attention: sauvegarder le fichier Excel en fichier .csv (comma delimited) et non csv (DOS) pour garder accents
import chardet
with open('/home/CondoFix/mysite/condofix/ImportUrbano.csv', 'rb') as rawdata:
    result = chardet.detect(rawdata.read(100000))
    print( result)

#SC Tract Population 2010
# import and calculate from csv
with open('/home/CondoFix/mysite/condofix/ImportUrbano.csv', 'r',encoding="windows-1252") as csvfile:
    #read csv file
    file_reader = csv.reader(csvfile, delimiter=';')
    nbr_rows=0
    # profile_list=session.get('ProfilUsager')
    # client_ident=profile_list[0]
    cnx = connect_db()
    cur = cnx.cursor()
    id_client=3
    id_intervenant=0
    # ****ATTENTION: id_concierge et intervenant 'autre' diffèrent selon client
    id_concierge=31
    # insérer indice de l'intervenant 'autre' de la bd du client:
    id_interv_autre=29
    hres_estimees=0
    for row in file_reader:
        nbr_rows += 1
        # pour ne pas sauvegarder les étiquettes du csv
        if nbr_rows==1:
            continue
        #if nbr_rows==4:
        #    break

        # pour importer équipements;
        # cur.execute("INSERT INTO equipements (IDClient, IDEquipement, Description, IDCategorie, Emplacement, ValeurRemplacement_$, DateInstallation, DateRemplacement, Actif) values (%s, %s, %s, %s, %s, %s, %s, %s, %s,)",(id_client,row[0], row[1], row[2], row[3], row[4], row[5], row[6], 1))

        # pour importer cahier d'entretien préventif
        # le fichier csv ne peut avoir des valeurs dans les colonnes 'employé' et 'fournisseur' en même temps..si oui, créer un autre enregistrement
        if row[17]!='':
            id_intervenant=id_concierge
            hres_estimees=row[17]
        elif row[18]!='':
            id_intervenant=id_interv_autre
            hres_estimees=row[18]

        # print(id_client, row[1],hres_estimees,id_intervenant,row[2],row[0],row[16],row[3],3,int(row[4]),int(row[5]),int(row[6]),
        #       int(row[7]),int(row[8]),int(row[9]),int(row[10]),int(row[11]),int(row[12]),int(row[13]),int(row[14]),int(row[15]))
        cur.execute("INSERT INTO preventif (IDClient,Description, HresEstimees, IDIntervenant, IDCategorie, ReferenceCarnet,"
                        " DateProchain, FreqAns, IDTypeTravail, Janv, Fev, Mars, Avril, Mai, Juin, Juil, Aout, Sept, Oct, Nov,`Dec`) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [id_client, row[1],hres_estimees,id_intervenant,row[2],row[0],row[16],row[3],3,int(row[4]),int(row[5]),int(row[6]),
                         int(row[7]),int(row[8]),int(row[9]),int(row[10]),int(row[11]),int(row[12]),int(row[13]),int(row[14]),int(row[15])])
        cnx.commit()
    cnx.close()