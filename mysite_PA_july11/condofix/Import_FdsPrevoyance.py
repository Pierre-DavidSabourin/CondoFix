# -*- coding: utf-8 -*-

__author__ = 'donald'

import sqlite3
import csv
import mysql.connector

# def connect_db():
#     # db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
#     # host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$condofix')
#     db = mysql.connector.connect(user='root', password='aholein1', host='127.0.0.1', database='condofix$condofix')
#
#     return db

# attention: sauvegarder le fichier Excel en fichier .csv (comma delimited) et non csv (DOS) pour garder accents
# import chardet
# with open('/home/CondoFix/mysite/condofix/ImportUrbano.csv', 'rb') as rawdata:
#     result = chardet.detect(rawdata.read(100000))
#     print( result)

# import and calculate from csv
# with open('/home/CondoFix/mysite/condofix/ImportUrbano.csv', 'r',encoding="windows-1252") as csvfile:
# with open("C:/Users\DOnal\Documents\Projets Programmation\mysite_PA_july11/condofix/Import_fds_prevoyance_Urbano.csv", 'r', encoding="windows-1252") as csvfile:
# def importation():
#     with open("C:/Users\DOnal\Documents\CondoFix\Clients\ClubMemphre2\Import_ Interventions_2112.csv",'r', encoding="windows-1252") as csvfile:
#
#     #read csv file
#     file_reader = csv.reader(csvfile, delimiter=';')
#     nbr_rows=0
#     # profile_list=session.get('ProfilUsager')
#     # client_ident=profile_list[0]
#     #cnx = connect_db()
#     #cur = cnx.cursor()
#     id_client=1
#
#     for row in file_reader:
#         nbr_rows += 1
#         # pour ne pas sauvegarder les étiquettes du csv
#         if nbr_rows==1:
#             continue
#         print(row)
#         if nbr_rows==4:
#            break
#
#         #cur.execute("INSERT INTO fondsprevoyance (IDClient, DescriptionDepense, TypeMtceRempl, IDCategorie, RefGroupeUniformat, RefAnalyse, CodeElementUniformat,"
#            # " ValeurActuelleInterv, FrequenceAns, IDEquipement, IDIntervenant, PartSyndicat, AnProchain, Inflation5ans, Inflation6a15ans, InflationPlus15ans, Actif) "
#            # "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
#            # [id_client, row[5], row[4], row[2], row[3], row[0], row[1], row[6], row[10], row[16], row[14], row[7], row[9], row[11], row[12],row[13],1])
#     # cnx.commit()
#     # cnx.close()
#     message=str('import complet:'+str(nbr_rows)+' enregistrements')
#
#     return message
