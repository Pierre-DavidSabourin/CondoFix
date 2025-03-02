import sys

from flask import Blueprint, render_template,session,request,redirect,url_for,flash,json,send_file
from markupsafe import Markup  # Import Markup separately
import mysql.connector
import os
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials
import re
from nltk.tokenize import RegexpTokenizer
from PIL import Image, ImageOps
import time
from datetime import datetime, timedelta
import shutil
import traceback
from mysite_PA_july11.utils import connect_db,chemin_rep,chemin_factures,chemin_temp_images


bp_ocr = Blueprint('bp_ocr', __name__)


"""Traitement pour une facture qui n'est pas rattachée à un ticket. Celui-ci est lancé
à partir de la table des factures avec le bouton 'Scan OCR'.
Étapes:
def lancer_OCR (ouverture de la page pour sélection de facture selon mode 'dropzone' ou 'dnload'
  si un autre usager du même client est en train de numériser une facture :MESSAGE FLASH (en commun avec 'attente')
def upload pour soumettre la facture à l'OCR et soutirer les infos pertinentes (en commun avec 'attente')
def fournisseur si l'usager ajoute un fournisseur à la table 'intervenants' avec le bouton 'Ajouter'
def annulation si facture non soumise par l'usager (en commun avec 'attente')
def facture_ocr si facture est soumise pour sauvegarde incluant numérisation de l'image
"""

"""Lancer le processus OCR"""
@bp_ocr.route('/lancer_OCR',methods=['POST','GET'])
def lancer_OCR():
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    mode_connexion=profile_list[8]
    nom_client=profile_list[7]
    chemin_ocr=chemin_temp_images(mode_connexion)

    # vérifier le statut du fichier de paramètres ocr avant de sauvegarder temporairement
    # le statut est remis à '0' lors du clic de bouton 'soumettre' ou 'annuler' dans la page de saisie OCR
    with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt')) as m:
        contenu_statut = []
        for line in m:
            # Remove linebreak which is the last character of the string
            # curr_place = line[:-1]
            # Add item to the list
            contenu_statut.append(line)
        dateheure = datetime.now()
        dateheure_debut = dateheure - timedelta(minutes=3)

        if contenu_statut[0] != '0':
            # fichier en cours d'utilisation CAR '0' signifie 'libre'
            # on vérifie le délai depuis la dernière opération OCR en comparant dateheure actuel et celui inscrit lors de la dernière saisie
            date_format = '%Y-%m-%d %H:%M:%S.%f'
            dateheure_saisie = datetime.strptime(contenu_statut[0], date_format)

            if dateheure_saisie>=dateheure_debut: # délai de moins de 3 minutes
                diff=dateheure-dateheure_saisie
                min_restantes=round(3-diff.total_seconds()/60,1)
                flash("Un autre usager utilise présentement la fonctionnalité de facture OCR.",'warning')
                flash("Il reste "+str(min_restantes)+" minute(s) avant qu'elle devienne disponible.", 'warning')
                return render_template('OCR_NonDispo.html')
            else:
                # on met la dateheure actuelle
                # modifier le statut du fichier de paramètres ocr pour le rendre accessible
                with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
                    f.write(str(datetime.now()))
        else:
            # on met la dateheure actuelle
            # modifier le statut du fichier de paramètres ocr pour le rendre accessible
            with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
                f.write(str(datetime.now()))

    # selon l'appareil utilisé, on affiche la page de scan appropriée:
    # pour ios: pas de pdf visibles avec dropzone.js alors on utilise l'outil de téléchargement html
    # pour windows: on utilise dropzone.js qui fonctionne avec les pdf
    user_agent = request.headers.get('User-Agent')
    if 'Windows' in user_agent:
        return render_template('facture_ocr_scan_dz.html')
    else:
        return render_template('facture_ocr_scan_dnload.html')

#fonction d'ajout de facture à un ticket existant
@bp_ocr.route('/lancer_facture_attente_ocr/<id_ticket>', methods=['POST','GET'])
def lancer_facture_attente_ocr(id_ticket):

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    mode_connexion = profile_list[8]

    chemin_ocr = chemin_temp_images(mode_connexion)
    # vérifier le statut du fichier de paramètres ocr avant de sauvegarder temporairement
    # le statut est remis à '0' lors du clic de bouton 'soumettre' ou 'annuler'
    with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + profile_list[7] + '.txt')) as m:
        contenu_statut = []
        for line in m:
            # Remove linebreak which is the last character of the string
            # curr_place = line[:-1]
            # Add item to the list
            contenu_statut.append(line)

        # vérifier le statut du fichier de paramètres ocr avant de sauvegarder temporairement
        # le statut est remis à '0' lors du clic de bouton 'soumettre' ou 'annuler' dans la page de saisie OCR
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + profile_list[7] + '.txt')) as m:
            contenu_statut = []
            for line in m:
                # Remove linebreak which is the last character of the string
                # curr_place = line[:-1]
                # Add item to the list
                contenu_statut.append(line)
            dateheure = datetime.now()
            dateheure_debut = dateheure - timedelta(minutes=3)
            print('contenu statut:', contenu_statut)
            if contenu_statut[0] != '0':
                # fichier en cours d'utilisation CAR '0' signifie 'libre'
                # on vérifie le délai depuis la dernière opération OCR en comparant dateheure actuel et celui inscrit lors de la dernière saisie
                date_format = '%Y-%m-%d %H:%M:%S.%f'
                dateheure_saisie = datetime.strptime(contenu_statut[0], date_format)

                if dateheure_saisie >= dateheure_debut:  # délai de moins de 3 minutes
                    diff = dateheure - dateheure_saisie
                    min_restantes=round(3-diff.total_seconds()/60,1)
                    flash("Un autre usager utilise présentement la fonctionnalité de facture OCR.", 'warning')
                    flash(
                        "Il reste au maximum " + str(min_restantes) + " minutes avant qu'elle ne devienne disponible.",
                        'warning')
                    return render_template('OCR_NonDispo_Attente_Facture.html',id_ticket=id_ticket)
                else:
                    # on met la dateheure actuelle
                    # modifier le statut du fichier de paramètres ocr pour le rendre accessible
                    with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + profile_list[7] + '.txt'), 'w') as f:
                        f.write(str(datetime.now()))
            else:
                # on met la dateheure actuelle
                # modifier le statut du fichier de paramètres ocr pour le rendre accessible
                with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + profile_list[7] + '.txt'), 'w') as f:
                    f.write(str(datetime.now()))

    """Afficher les données du ticket pour l'ajout d'une facture"""

    ticket_list=[]
    client_ident=profile_list[0]
    IntervenantNom=str()
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_ticket=[]
    cur.execute("SELECT IDTicket, IDIntervenant, Description_travail, DateComplet, HeuresEstimees, HeuresRequises, "
                      "Nbre_visites,Multitags, IntervenantAutre FROM tickets WHERE IDTicket=%s AND IDClient=%s", (id_ticket,client_ident))
    for row in cur.fetchall():
        #vérifier si rubrique 'IntervenantAutre' est remplie

        cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
                    (row[1], client_ident))
        for item in cur.fetchall():
            if item[0]=='Autre':
                IntervenantNom=row[8]
            else:
                IntervenantNom = item[0]
        row += (IntervenantNom,)

        ticket_list.append(row)
        liste_ticket=[list(row) for row in ticket_list]
        # vérifier si c'est un multitags
        if row[7]==1:
            message=Markup("<b>Ce ticket no."+id_ticket+" est de type 'Multitags' car il s'applique à de multiples équipements.</b><br>") \
                    +Markup("Vous pouvez ainsi partager le montant de la facture avec un ticket dupliqué selon le travail effectué sur chaque équipement.<br>") \
                    +Markup("Un duplicata de ce ticket s'affichera à la fin de cette table dès que vous cliquerez sur 'Dupliquer'.<br>") \
                    +Markup("Lors de l'attribution du numéro de tag et des dépenses sur ces tickets, ne pas oublier de: <br>") \
                    +Markup("- modifier la description <br>") \
                    +Markup("- ajuster les heures requises <br>") \
                    +Markup("- décocher 'multi-tags'")
            flash(message, "warning")
            return redirect(url_for('bp_factures.attente_facture'))

    # selon l'appareil utilisé, on affiche la page de scan appropriée:
    # pour ios: pas de pdf visibles avec dropzone.js alors on utilise l'outil de téléchargement html
    # pour windows: on utilise dropzone.js qui fonctionne avec les pdf
    user_agent = request.headers.get('User-Agent')
    if 'Windows' in user_agent:
        return render_template('facture_ocr_attente_dz.html', mode='dz', id_ticket=id_ticket, bd=profile_list[3])
    else:
        return render_template('facture_ocr_attente_dnload.html', mode='dnload', id_ticket=id_ticket, bd=profile_list[3])


@bp_ocr.route('/afficher_OCR/<mode>',methods=['POST','GET'])
def afficher_OCR(mode):
    """Affichage de la page web qui suit 'upload' dans le code 'dropzone' de la page de scan initial
     à partir des données cumulées dans les fichiers texte
    produits par la fonction 'upload' qui suit celle-ci. On lit les fichiers texte pour
    ensuite publier la page. """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    # trouver le mode de connexion (Dev ou PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    chemin_ocr = chemin_temp_images(mode_connexion)

    ch_fichier_jpg_taille_orig=str()
    ch_fichier_pdf=str()
    with open(os.path.join(chemin_ocr, 'ocr_params_'+profile_list[7]+'.txt'), encoding='utf-8') as f:
        #contenu_OCR=f.read()
        #print('type:',contenu_OCR)
        contenu_OCR=[]
        for line in f:
            # Remove linebreak which is the last character of the string
            curr_place = line[:-1]
            # Add item to the list
            contenu_OCR.append(curr_place)

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # vérifier les paramètres d'affichage de la page de résultats

    liste_affichage=[]
    cur.execute("SELECT AfficheOcrTags, AfficheOcrTicketOuvert, Affiche_MDO_MAT FROM parametres WHERE IDClient = %s", (client_ident,))
    for row in cur.fetchall():
        liste_affichage.append(row)
    #print('liste affichage:',liste_affichage)

    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 and IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])

    liste_types_travail = []
    cur.execute("SELECT IDTypeTravail, Description FROM typetravail")
    for row in cur.fetchall():
        liste_types_travail.append(row)

    liste_equipements = []
    cur.execute("SELECT IDEquipement, Nom, IDCategorie,NumTag FROM equipements WHERE Actif=1 AND IDClient=%s",
                (client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)
    list_res = set(map(lambda x: x[2], liste_equipements))
    list_categ_avec_tags = list(list_res)
    list_equip = [[(y[3], y[1]) for y in liste_equipements if y[2] == x] for x in list_categ_avec_tags]

    liste_intervenants = []
    cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE Actif=1 and IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_intervenants.append(row)
    liste_intervenants.sort(key=lambda x: x[1], reverse=False)

    ch_fichier_jpg_taille_orig='../static/temp_images/'+'temp_image_'+profile_list[7]+'.jpg'
    ch_fichier_pdf='../static/temp_images/'+'temp_image_'+profile_list[7]+'.pdf'

    # vérifier si fournisseur trouvé dans la table des intervenants
    if contenu_OCR[3] == 'Autre':
        aff_modif_fournisseur=1
    else:
        aff_modif_fournisseur = 0

    return render_template('facture_ocr_ajout.html',mode=mode, liste_ocr=contenu_OCR, liste_affichage=liste_affichage,
                           list_categ_avec_tags=json.dumps(list_categ_avec_tags), liste_categories=liste_categories,
                           list_equip=json.dumps(list_equip), liste_intervenants=liste_intervenants,liste_types_travail=liste_types_travail,
                           jpg_orig=ch_fichier_jpg_taille_orig, image_pdf=ch_fichier_pdf, affiche_ajouter=aff_modif_fournisseur)


@bp_ocr.route('/upload/<args>', methods=['POST', 'GET'])
def upload(args):
    """Traitement de l'image avec OCR puis sauvegarde des données dans fichier texte.
     1- Sauvegarde des images
     2- Sauvegarde du statut et du type de fichier
     3- Envoi de l'image avec l'API de azure vision et retour des données
     4- Traitement des données OCR pour obtenir les résultats voulus
     5- Sauvegarde des paramètres OCR dans fichier texte identifié au client pour utilisation à
        la fonction 'Affiche_OCR': nom du fournisseur, adresse, code postal, téléphone, no. facture, montants, description
     """
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')

    client_ident=profile_list[0]
    nom_client=profile_list[7]
    # trouver le mode de connexion (Dev ou PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]

    chemin_ocr = chemin_temp_images(mode_connexion)

    string_1 = args.replace('[', '').replace(']', '').replace("'", "")
    list_1 = string_1.split(',')
    mode = list_1[0]
    id_ticket = list_1[1]
    attente = list_1[2] # si OCR à partir de ticket en attente de facture=1

    facture_list = []
    #1*******Sauvegarde des images
    type_fichier = str()
    ch_fichier =str()
    contenu_OCR=[]

    if request.method == 'POST':
        if mode=='dz':
            f = request.files.get('file')
        else:
            f = request.files['fichier']

        nom_fichier = f.filename

        if '.pdf' in nom_fichier:
            ch_fichier=os.path.join(chemin_ocr, 'temp_image_'+nom_client+'.pdf')

            f.save(ch_fichier)
            file_stats = os.stat(ch_fichier)
            taille_pdf = file_stats.st_size
            if taille_pdf > 400000:
                flash("Fichier .pdf plus grand que 400K. L'image ne sera pas sauvegardée.",'warning')
            type_fichier = 'pdf'
        else:
            # fichiers jpg, jpeg, png, bmp seulement acceptés autres non (tif, word, etc.)
            if '.jpg' in nom_fichier or '.jpeg' in nom_fichier or '.png' in nom_fichier or '.bmp' in nom_fichier:

                ch_fichier = os.path.join(chemin_ocr, 'temp_image_' + nom_client+ '.jpg')
                f.save(ch_fichier)
                # vérifier si fichier plus grand que 4MB (limite de computervision pour OCR)
                file_stats = os.stat(ch_fichier)
                taille_fichier = file_stats.st_size
                # print('nom fichier:',nom_fichier)
                # print('taille fichier:',taille_fichier)
                type_fichier = 'image'
                if taille_fichier>3999000:
                    # on réduit la taille du fichier
                    img_reduit = Image.open(ch_fichier)
                    # pour éviter que l'image soit sauvegardée avec rotation de 90 deg.
                    img_reduit = ImageOps.exif_transpose(img_reduit)
                    # Réduire la taille en conservant les proportions pour sauvegarde éventuelle
                    img_reduit.thumbnail((800, 800), Image.ANTIALIAS)
                    img_reduit.convert('RGB').save(ch_fichier)

                    # sauvegarde de l'image en format déjà réduit
                    ch_resize = os.path.join(chemin_ocr, 'resized_image_' + profile_list[7] + '.jpg')
                    # doit convertir image en mode 'RGB' pour sauvegarde format réduit en .jpg
                    img_reduit.convert('RGB').save(ch_resize)
                else:
                    img = Image.open(ch_fichier)
                    # pour éviter que l'image soit sauvegardée avec rotation de 90 deg.
                    img = ImageOps.exif_transpose(img)
                    # Réduire la taille en conservant les proportions pour sauvegarde éventuelle
                    img.thumbnail((800, 800), Image.ANTIALIAS)
                    ch_resize = os.path.join(chemin_ocr, 'resized_image_' + profile_list[7] + '.jpg')
                    # doit convertir image en mode 'RGB' pour sauvegarde format réduit en .jpg
                    img.convert('RGB').save(ch_resize)

            else:
                flash("Seuls les fichiers jpg, png, bmp et pdf sont traités. Cliquez sur 'Annuler' pour numériser une autre facture. ", 'warning')
                return ''

    # 2*******Sauvegarde du statut et du type de fichier
    statut=1 # pour éviter qu'un autre usager du client utilise cette fonctionnalité SIMULTANÉMENT
    # statut sera remis à '0' une fois que la facture OCR a été traitée voir ligne 421
    contenu_OCR.append(statut)
    contenu_OCR.append(type_fichier)


    try:
        # 3*******Envoi de l'image avec l'API de azure vision et retour des données
        # clé d'accès au service OCR de Azure et création d'un client
        subscription_key = "2992d159662044dcba4b47eb3da311fb"
        endpoint = "https://instance-condo.cognitiveservices.azure.com/"

        computervision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))

        #print("===== Read File - local =====")
        # Get image path
        read_image_path = ch_fichier
        # Open the image
        read_image = open(read_image_path, "rb")

        # Call API with image and raw response (allows you to get the operation location)
        read_response = computervision_client.read_in_stream(read_image, raw=True)
        # Get the operation location (URL with ID as last appendage)
        read_operation_location = read_response.headers["Operation-Location"]
        # Take the ID off and use to get results
        operation_id = read_operation_location.split("/")[-1]

        # Call the "GET" API and wait for it to retrieve the results
        while True:
            read_result = computervision_client.get_read_result(operation_id)
            if read_result.status not in ['notStarted', 'running']:
                break
            time.sleep(1)
        text_str=str()
        text_list=[]
        # Print the detected text, line by line
        if read_result.status == OperationStatusCodes.succeeded:
            for text_result in read_result.analyze_result.read_results:
                last_line = ''
                last_y_coord = float()
                complete_line = ''
                text_list = []
                text_str = str()
                for line in text_result.lines:
                    #print(line.text)
                    # print('x:',line.bounding_box[4],'y:',line.bounding_box[5])

                    # on prend les coordonnées y les plus basses de la boîte [1] avec une marge de 0.04
                    if (last_y_coord - (0.01 * last_y_coord)) < line.bounding_box[5] < (
                            last_y_coord + (0.01 * last_y_coord)):
                        complete_line = complete_line + " " + line.text
                    else:
                        # print(complete_line)
                        complete_line = complete_line + ' /'
                        line_formated = "(" + complete_line + ")"
                        text_list.append(line_formated)
                        text_str = text_str + " " + complete_line#  +str(line.bounding_box)
                        complete_line = line.text
                    last_y_coord = line.bounding_box[5]
                    last_line = line.text
                #print(complete_line)# pour imprimer dernière ligne
                line_formated = "(" + complete_line + ")"
                text_list.append(line_formated)
                text_str = text_str + " " + complete_line
            #print(text_list)
            #print(text_str)
    except:
        flash("Outil en ligne OCR non disponible en ce moment.",'warning')
        return ''

    # vérifier si c'est une photo sans texte
    if len(text_list) < 10:  # il se pourrait que du texte soit dans la photo donc 10 items max.
        flash("Problème de traitement: l'image est probablement une photo, pas une facture.", 'warning')

    # 4*******Traitement des données OCR pour obtenir les résultats voulus
    # 4a Recherche du fournisseur dans la bd
    liste_fournisseurs = []
    liste_fournisseurs_txt = []
    id_fournisseur_autre=int()
    chaine_interv = str()
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT IDIntervenant, NomIntervenant, Adresse, TelPrincipal, IDCategorie FROM intervenants WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        if row[1]=='Autre':
            id_fournisseur_autre=row[0]
        liste_fournisseurs.append(row)
        chaine_interv=str(row[1]).lower()+' '+str(row[2]).lower()+' '+str(row[3])
        liste_fournisseurs_txt.append(chaine_interv)
    cnx.close()
    #Coord_fournisseur_chaine = Coord_fournisseur_chaine.lower()
    # Utilisation de NTLK pour comparer les chaînes fournisseur et facture
    # comparer tokens du fournisseur avec celui du texte de la facture
    tokenizer = RegexpTokenizer('\w+')
    contenu = text_str.lower()
    tokens_contenu = tokenizer.tokenize(contenu)
    score=float()
    id_intervenant = 0
    nom_intervenant=str()
    id_categ_intervenant = 0
    items_trouves=0
    tokens_fournisseur=0
    i=0
    for item in liste_fournisseurs_txt:

        tokens_fournisseur = tokenizer.tokenize(item)
        items_trouves = 0
        for element in tokens_fournisseur:
            if element in tokens_contenu:
                #print(element + ' trouvé')
                items_trouves += 1
        score=round(items_trouves / len(tokens_fournisseur), 3)
        if score>0.70:
            #print('interv et categ:',item)
            id_intervenant=liste_fournisseurs[i][0]
            nom_intervenant=liste_fournisseurs[i][1]
            id_categ_intervenant=liste_fournisseurs[i][4]
            break
        i += 1

    #print('Score fournisseur: ', round(items_trouves / len(tokens_fournisseur), 3))

    # SI PAS TROUVÉ AVEC SCORE OK: 'AUTRE'
    liste_mots_cles_fourniss = ['élect', 'plomb','chauffage','climatisation','ventil','ascenseur','déneigement','elect','excav','const',
                                'entrep','répar','instal','service','équipement','entretien','consult','produits','quincaill',
                                'centre','rénov','alarme','incendie','sécur','bell','hydro-québec','énergir','vidéotron','canadian tire','walmart','home depot','home hardware','rona','reno-depôt','canac','bmr',
                                'simplex','inc.',' ltée',' limitée',' enr','société','.ca','.com']

    fournisseur_OCR=str()
    if score<=0.70:
        id_intervenant=id_fournisseur_autre
        nom_intervenant='Autre'
        # convertir la chaîne (majuscules et minuscules) en liste
        liste_contenu = text_str.lower().split('/')
        # on prend les premiers 15 éléments pour chercher le nom du fournisseur
        liste_courte=liste_contenu[:15]
        # trouver nom du fournisseur dans résultat OCR:
        trouve=False
        #print(liste_courte)
        for item in liste_mots_cles_fourniss:
            if trouve==True:
                break
            res = [i for i in liste_courte if item in i]
            if res != []:
                fournisseur_OCR=res[0].upper()
                # enlever espace au début
                fournisseur_OCR=fournisseur_OCR[1:]
                trouve=True

        if trouve==False:
            # pas de correspondance, on prend donc l'élément de liste précédant l'Adresse (celle contenant un chiffre)
            i=1
            for item in liste_contenu:
                #print(item)
                if any(char.isdigit() for char in item)==True:
                    # on choisit l'élément précédant l'adresse
                    if i>2:
                        fournisseur_OCR = liste_contenu[i-2].upper()
                        break
                    else: break
                i += 1

    else:
        fournisseur_OCR =''

    contenu_OCR.append(id_intervenant)#2
    contenu_OCR.append(nom_intervenant)
    contenu_OCR.append(id_categ_intervenant)
    contenu_OCR.append(fournisseur_OCR)

    #4b traitement de l'adresse et code postal
    cherche_code = re.findall('[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]', text_str)
    adresse_OCR=str()
    if len(cherche_code) != 0:
        liste_adresse = re.findall('\d+\D+[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]', text_str)
        adresse = liste_adresse[0]
        adresse_OCR = adresse.replace('/', '')
        #print('Adresse:', adresse_OCR)
    else:
        print('Adresse: pas trouvée')

    #4c trouver no. de téléphone
    phone_no = str()
    # trouver téléphone du fournisseur
    liste_tel = re.findall('\D*([2-9]\d{2})(\D*)([2-9]\d{2})(\D*)(\d{4})\D* ', text_str)
    if len(liste_tel) > 0:
        for item in liste_tel[0]:
            if item.isdigit() == True:
                if len(phone_no) == 0:
                    phone_no = phone_no + item
                else:
                    phone_no = phone_no + '-' + item
            #if len(phone_no) == 12:
            #    print('phone_no:', phone_no)


    contenu_OCR.append(adresse_OCR)
    contenu_OCR.append(phone_no)

    #4d traitement pour numéro de facture
    # convertir toute la chaîne en minuscules pour trouver 'facture'
    chaine_contenu = text_str.lower()
    # convertir en liste
    liste_contenu = chaine_contenu.split('/')
    no_facture=str()
    res_list=[]
    i=0
    for item in text_list:
        if 'facture' in item.lower():
            # on cherche une série de 3 et plus (pour éviter dates comme "2019/06/09") à 12 chiffres
            res_list = re.findall('\d{3,12}\s', item)
            if len(res_list) > 0:
                # on imprime cette première ligne puis on quitte la boucle
                no_facture=res_list[0]
                break
            # on cherche dans les 2 éléments suivants
            if i < len(liste_contenu) - 1:  # pour éviter d'appeler un élément qui dépasse la longueur de la liste
                next_elem_1=text_list[i+1]
                res_suiv_1=re.findall('\d{3,12}\s', next_elem_1)
                if len(res_suiv_1) > 0:
                    # on imprime cette première ligne puis on quitte la boucle
                    no_facture = res_suiv_1[0]
                    break
            if i < len(liste_contenu) - 2:  # pour éviter d'appeler un élément qui dépasse la longueur de la liste
                next_elem_2 = text_list[i + 2]
                res_suiv_2 = re.findall('\d{3,12}\s', next_elem_2)
                if len(res_suiv_2) > 0:
                    # on imprime cette première ligne puis on quitte la boucle
                    no_facture = res_suiv_2[0]
                    break
        i+=1
    if no_facture=='':
        contenu_OCR.append('')
    else:
        # on vérifie si l'année de la facture a été choisie
        if 1990<int(no_facture)<2030:
            contenu_OCR.append('')
        else:
            contenu_OCR.append(no_facture)

    # trouver la date de la facture
    # 1- avec un format YYYY/MM/DD ou YYYY-MM-DD
    date_list=re.findall('\d{4}[(\/.-]\d{2}[(\/.-]\d{2}', text_str)
    #print(text_str)
    #print(text_list)

    # on choisit le premier élément de la liste
    date_fin=str()
    if date_list!= []:
        if '/' in date_list[0]:
            # on remplace les slashes par des tirets
            date_fin=date_list[0].replace('/','-')
        else:  date_fin=date_list[0]
    else:
        # 2- avec un format DD/MM/YYYY ou DD-MM-YYYY
        date_list = re.findall('\d{2}[(\/.-]\d{2}[(\/.-]\d{4}', text_str)
        # on choisit le premier élément de la liste
        if date_list != []:
            if '/' in date_list[0]:
                # on remplace les slashes par des tirets
                date_res = date_list[0].replace('/', '-')
            else:
                date_res=  date_list[0]
            # convertir en format YYYY/MM/DD mais attention aux erreurs si OCR lit mal ou caractères trop petits
            try:
                date_fin = datetime.strptime(date_res, "%d-%m-%Y").strftime("%Y-%m-%d")
            except:
                date_fin=''
        else:
            # 3- avec un format écrit avec le mois (ex. 15 mai 2019 ou 15 mai,2019)
            date_list = re.findall('\d{1,2}\s\w+[\s\,]\s*\d{4}',text_str.lower())
            # # on choisit le premier élément de la liste
            if date_list != []:
                res = date_list[0]
                liste_mois = ['jan', 'fev', 'mars', 'avril', 'mai', 'juin', 'juill', 'ao', 'sept', 'oct', 'nov','dec','déc']
                for item in liste_mois:
                    if item in res:
                        mois = int(liste_mois.index(item))
                        if mois < 9:
                            mois_str = '0' + str(mois+1)
                        elif mois==12:# si 'déc' et non 'dec'
                            mois_str = '12'
                        else: mois_str= str(mois+1)
                        jour_brut=int(res[:2])
                        if jour_brut<10:
                            #on ajoute un 0 devant le jour pour bien formatter la date finale
                            jour_fin='0'+str(jour_brut)
                        else: jour_fin=res[:2]
                        date_fin = res[-4:] + '-' + mois_str + '-' + jour_fin
            else:
                date_fin=''
    # la date Str() doit être de format 0000-00-00
    contenu_OCR.append(date_fin)#time.strftime('%Y-%m-%d'))

    #4e recherche des montants
    tot_facture = 0
    res_list = []
    list_trouves=[]
    res=str()
    tot_traite=str()

    i=0
    for item in liste_contenu:
        if ' total' in item or ' montant' in item:
            # enlever les signes '$' dans l'item
            item_net=item.replace('$',' ').replace(' ', '  ')
            #print(item_net)
            #  pour trouver les montants avec ',' et avec ','dans l'item
            #res_list = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{0,3},*[\.\,]\d{2}\s', item_net)
            # recherche des chaines avec montant sans espace entre les chiffres pour les milliers
            res_list = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{0,3},*[\.\,]\d{2}', item_net)
            if len(res_list)>0:
                ##########on doit passer à travers tous les résultats, non seulement le premier!!
                for index, x in enumerate(res_list):
                    # on enlève tous les espaces, virgules et points décimaux
                    res=int(res_list[index].replace(' ','').replace('.','').replace(',',''))
                    # on divise le montant entier par 100 pour obtenir deux décimales
                    total_trouve=format(res / 100.0, '.02f')
                    list_trouves.append(total_trouve)
            #else:  # on cherche dans les 2 éléments suivants
            if i<len(liste_contenu)-1: # pour éviter d'appeler un élément qui dépasse la longueur de la liste
                next_elem_1 = liste_contenu[i + 1]
                #print('item suivant:', next_elem_1)
                # enlever les signes '$'
                next_elem_1_net = next_elem_1.replace('$', ' ').replace(' ', '  ')
                res_suiv_1 = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{0,3},*[\.\,]\d{2}', next_elem_1_net)
                if len(res_suiv_1) > 0:
                    ##########on doit passer à travers tous les résultats, non seulement le premier!!
                    for index, x in enumerate(res_suiv_1):
                        # on enlève tous les espaces, virgules et points décimaux
                        res = int(res_suiv_1[index].replace(' ', '').replace('.', '').replace(',', ''))
                        # on divise le montant entier par 100 pour obtenir deux décimales
                        total_trouve = format(res / 100.0, '.02f')
                        list_trouves.append(total_trouve)
                #else:

            if i < len(liste_contenu) - 2:  # pour éviter d'appeler un élément qui dépasse la longueur de la liste
                next_elem_2 = liste_contenu[i + 2]
                #print('item suivant 2:', next_elem_2)
                # enlever les signes '$' et les espaces dans l'item
                next_elem_2_net = next_elem_2.replace('$', ' ').replace(' ', '  ')
                res_suiv_2 = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{0,3},*[\.\,]\d{2}', next_elem_2_net)
                if len(res_suiv_2) > 0:
                    ##########on doit passer à travers tous les résultats, non seulement le premier!!
                    for index, x in enumerate(res_suiv_2):
                        # on enlève tous les espaces, virgules et points décimaux
                        res = int(res_suiv_2[index].replace(' ', '').replace('.', '').replace(',', ''))
                        # on divise le montant entier par 100 pour obtenir deux décimales
                        total_trouve = format(res / 100.0, '.02f')
                        list_trouves.append(total_trouve)
        i+=1
    #print('totaux trouvés:', list_trouves)

    list_trouves_float=[]
    # on cherche le montant le plus élevé de la liste des items trouvés
    liste_trouves_triee=[]
    if len(list_trouves)== 0:
        tot_facture = 0
    elif len(list_trouves)== 1:
        tot_facture=list_trouves[0]
    elif len(list_trouves)>1:
        list_trouves_float = [float(x) for x in list_trouves]
        #print('listes float:',list_trouves_float)
        list_trouves_float.sort(reverse=True)
        #print('liste_triée:', list_trouves_float)
        tot_facture=list_trouves_float[0]

    # # si les mots 'total' ou 'montant' non présents, on initie un traitement différent
    # # c'est la recherche des montants avec deux décimales
    # liste_montants_float = []
    # if tot_facture==0:
    #     contenu=text_str
    #     liste_traitee = []
    #     # vérifier si les décimales des montants utilisent une virgule
    #     #liste_montants_virg = re.findall('[\d]+\,\d{2} ', contenu)
    #     liste_montants_virg = re.findall('[0-9]{1,3}[,\s]*[0-9]{1,6},*\,[0-9][0-9]', contenu)
    #     # montants avec point décimale sans séparateurs de milliers
    #     # liste_montants_pt = re.findall('[\d]+\.\d{2} ', contenu)
    #     liste_montants_pt = re.findall('[0-9]{1,3}[,\s]*[0-9]{1,3},*\.[0-9][0-9]', contenu)
    #     liste_montants_pt_1 = re.findall('\s[0-9]{1,3},*\.[0-9][0-9]', contenu)
    #     # print('virg:',liste_montants_virg)
    #     # print('pts:', liste_montants_pt)
    #
    #     if len(liste_montants_pt) > len(liste_montants_virg):
    #         liste_montants = liste_montants_pt
    #     else:
    #         liste_montants = liste_montants_virg
    #     #print('liste montants:', liste_montants)
    #     i = 0
    #     for item in liste_montants:
    #         # print(item)
    #         liste_montants[i] = liste_montants[i].replace(' ', '')
    #         cars_tot = len(item)
    #         # print('index:', item.index(','), 'len:', cars_tot)
    #         # séparateur de millier en virgule remplacé par aucun espace
    #         if ',' in item:
    #             # séparateur de millier en virgule remplacé par aucun espace
    #             if item.index(',') != (cars_tot - 3):
    #                 ind = int(item.index(','))
    #                 liste_montants[i] = liste_montants[i][:ind - 1] + liste_montants[i][ind:]
    #             # séparateur de décimale en virgule remplacé par un point
    #             liste_montants[i] = liste_montants[i].replace(',', '.')
    #         i += 1

        # #print(liste_montants)
        # liste_montants_float = [float(x) for x in liste_montants]
        # liste_montants_float.sort(reverse=True)
        # #print('liste montants float:',liste_montants_float)
        # # calcul TPS TVQ possible à partir du grand total et vérification des totaux
        # tot_facture = 0
        # if len(liste_montants_float)>0:
        #     tot_facture = liste_montants_float[0]

    # calcul des taxes
    tps=0
    tvq=0
    if tot_facture!=0:
        val_tps = float(tot_facture) * 0.043487
        for item in list_trouves_float:
            if val_tps - (0.001*val_tps) < item < val_tps + (0.001*val_tps):
                tps=item

        val_tvq = float(tot_facture) * 0.08675
        for item in list_trouves_float:
            if val_tvq - (0.001*val_tvq) < item < val_tvq + (0.001*val_tvq):
                tvq=item

    else:
        tps=0
        tvq=0

    contenu_OCR.append(tot_facture)
    contenu_OCR.append(tps)#TPS
    contenu_OCR.append(tvq)#tvq


    #4f Tenter de trouver une description************ mis de côté: ignoré dans la page de résultat de scan
    # Mots clés pour description auto:
    mots_desc='aménag, adapt, arrang, change, confection, corrig, colmat, déménage, entretien, faire, fourni, honoraires, implant, inspect, ' \
              'install, lav, modif, nett, peintur, pose, refaire, remplace, renouvel, replac, renov, répar, replac, trav'
    liste_mots_cles=mots_desc.split(',')
    desc_ocr=str()
    desc_brut=str()

    # convertir tous les caractères de la liste en minuscules
    #text_list_lower=list(map(lambda x: x.lower(), text_list))
    text_list_lower=[x.lower() for x in text_list]
    # rechercher lignes dans la liste contenant un des mots clés
    for item in liste_mots_cles:
        res_find = filter(lambda x: item in x, text_list_lower)
        listing=list(res_find)
        if len(listing)>0:
            # on sélectionne l'élément trouvé plus la ligne suivante
            desc_brut = listing[0]
            desc_ocr=desc_brut.replace('(','').replace(')','').replace('/','')
            break
    contenu_OCR.append(desc_ocr)

    #5 sauvegarde des paramètres dans fichier texte identifié au client
    with open(os.path.join(chemin_ocr, 'ocr_params_'+nom_client +'.txt'), 'w+', encoding='utf-8') as f:
        #f.write(type_fichier)
        for listitem in contenu_OCR:
             f.write(f'{listitem}\n')
    if mode=='dz':
        # étant donné que la suite du traitement est définie avec le code js dans la page facture_scan_ocr pour 'dropzone'
        # le système ira à la fonction bp_ocr.affiche_OCR
        return ''
    else:
        if int(attente)==1:
            return redirect(url_for('bp_ocr.afficher_OCR_attente', args=['dnload', id_ticket]))
        else:
            return redirect(url_for('bp_ocr.afficher_OCR', mode='dnload'))

@bp_ocr.route('/reset/<args>', methods=['POST', 'GET'])
def reset(args):

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    nom_client=profile_list[7]
    mode_connexion=profile_list[8]
    chemin_ocr = chemin_temp_images(mode_connexion)

    # modifier le statut du fichier 'en usage' pour le rendre accessible (statut =0)
    with open(os.path.join(chemin_ocr, 'ocr_en_usage_'+nom_client+'.txt'), 'w') as f:
        f.write('0')
    # # vider le fichier de paramètres ocr
    # with open(os.path.join(chemin_ocr, 'ocr_params_' + profile_list[7] + '.txt'), 'w+') as m:
    #     m.write('')
    # # supprimer les fichiers images temporaires du client
    # if os.path.exists(os.path.join(chemin_ocr, 'resized_image_' + profile_list[7] + '.jpg')):
    #     os.remove(os.path.join(chemin_ocr, 'resized_image_' + profile_list[7] + '.jpg'))
    # if os.path.exists(os.path.join(chemin_ocr, 'temp_image_' + profile_list[7] + '.pdf')):
    #     os.remove(os.path.join(chemin_ocr, 'temp_image_' + profile_list[7] + '.pdf'))

    string_1=args.replace('[','').replace(']','').replace("'","")
    list=string_1.split(',')
    mode=list[0]
    id_ticket=list[1]

    # # pour facture NON rattachée à un ticket existant
    if int(id_ticket)==0 :
        if mode == 'dz':
            return render_template('facture_ocr_scan_dz.html',  version_client=version_client)
        else:
            return render_template('facture_ocr_scan_dnload.html',  version_client=version_client)

    # # pour facture rattachée à un ticket existant
    else:
        if mode=='dz':
            return render_template('facture_ocr_attente_dz.html', id_ticket=id_ticket, version_client=version_client)
        else:
            return render_template('facture_ocr_attente_dnload.html', id_ticket=id_ticket, version_client=version_client)

@bp_ocr.route('/annulation/<args>', methods=['POST', 'GET'])
def annulation (args):

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    nom_client = profile_list[7]
    mode_connexion = profile_list[8]
    chemin_ocr = chemin_temp_images(mode_connexion)

    string_1 = args.replace('[', '').replace(']', '').replace("'", "")
    list = string_1.split(',')
    mode = list[0]

    id_ticket = list[1]

    # modifier le statut du fichier 'en usage' pour le rendre accessible (statut =0)
    with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
        f.write('0')
    # vider le fichier de paramètres ocr
    with open(os.path.join(chemin_ocr, 'ocr_params_' + nom_client + '.txt'), 'w+') as m:
        m.write('')
    # supprimer les fichiers images temporaires du client
    if os.path.exists(os.path.join(chemin_ocr, 'resized_image_' + nom_client + '.jpg')):
        os.remove(os.path.join(chemin_ocr, 'resized_image_' + nom_client + '.jpg'))
    if os.path.exists(os.path.join(chemin_ocr, 'temp_image_' + nom_client + '.pdf')):
        os.remove(os.path.join(chemin_ocr, 'temp_image_' + nom_client + '.pdf'))
    if int(id_ticket)==0:
        if mode == 'dz':
             return render_template('facture_ocr_scan_dz.html', version_client=version_client)
        else:
             return render_template('facture_ocr_scan_dnload.html', version_client=version_client)
    else: # via attente de factures (facture avec ticket)
        return redirect(url_for('bp_factures.attente_facture'))

# lorsque l'usager soumet une facture à partir de la page facture_ocr_ajout.html
# (sans passer par factures en attente...pas rattaché à un ticket)
@bp_ocr.route('/facture_ocr/<mode>', methods=['POST', 'GET'])
def facture_ocr(mode):
    """SAISIE DE FACTURE AVEC TICKET INEXISTANT
    Sauvegarde de la facture (données et image) avec création de ticket
    1- Sauvegarde de l'image (temp_image) si statut=1 pour ocr_en_usage (telle quelle pour pdf si <500K et format réduit pour .png et .jpg)
    2- Si sauvegarde image possible et ok: création de ticket avec statut 'Complété'
    3- Création de facture en ajoutant la référence au IDTicket créé
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    # trouver le mode de connexion (Dev ou PA)
    profile_list = session.get('ProfilUsager')
    mode_connexion = profile_list[8]
    nom_client= profile_list[7]
    chemin_db=str()
    chemin_ocr = chemin_temp_images(mode_connexion)

    # sauvegarde de l'image dans la documentation
    try:
        # vérifier si le temps de 3 minutes pour effectuer la transaction est dépassé
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt')) as m:
            contenu_statut = []
            for line in m:
                # Remove linebreak which is the last character of the string
                # curr_place = line[:-1]
                # Add item to the list
                contenu_statut.append(line)
            # dateheure = datetime.now()
            # dateheure_debut = dateheure - timedelta(minutes=3)

            if contenu_statut[0] != '0':
                # fichier en cours d'utilisation CAR '0' signifie 'libre'
                # on vérifie le délai depuis la dernière opération OCR en comparant dateheure actuel et celui inscrit lors de la dernière saisie
                date_format = '%Y-%m-%d %H:%M:%S.%f'
                dateheure_debut = datetime.strptime(contenu_statut[0], date_format)

                if datetime.now()>= dateheure_debut + timedelta(minutes=3):  # délai de moins de 3 minutes toléré
                    # on refuse la transaction
                    flash("Vous avez excédé le délai de 3 minutes pour la saisie de facture OCR.", 'warning')
                    flash(
                        "Aucun ticket ni aucune facture ont été créés.",'warning')
                    return render_template('OCR_NonDispo.html')

        if request.form['type_fichier']=='pdf':
            # taille max. 0,4MB pour .pdf. Les fichiers images .jpg ont déjà été réduits.
            chemin_fichier = os.path.join(chemin_ocr, 'temp_image_'+nom_client+'.pdf')
            file_stats = os.stat(chemin_fichier)
            taille_pdf = file_stats.st_size

            if taille_pdf>400000:
                flash('Fichier pdf trop grand pour être sauvegardé (maximum de 400K permis).','warning')
            else:
                source_path=chemin_fichier
                nom_fichier_brut = datetime.today().strftime(
                    '%Y-%m-%d') + 'Facture' + datetime.today().strftime('%H:%M:%S') + '.pdf'
                nom_fichier = nom_fichier_brut.replace(':', '')
                dest_path = os.path.join(chemin_factures(mode_connexion,'facture',nom_client), nom_fichier)
                shutil.move(source_path, dest_path)
                chemin_db='documentation/'+nom_client+'_docs/Factures/'+nom_fichier

        else:# c'est un fichier image

            chemin_fichier = os.path.join(chemin_ocr, 'resized_image_' + nom_client + '.jpg')
            source_path = chemin_fichier
            nom_fichier_brut = datetime.today().strftime(
                '%Y-%m-%d') + 'Facture' + datetime.today().strftime('%H:%M:%S') + '.jpg'
            nom_fichier = nom_fichier_brut.replace(':', '')
            dest_path = os.path.join(chemin_factures(mode_connexion,'facture',nom_client), nom_fichier)
            shutil.move(source_path, dest_path)
            chemin_db = 'documentation/' + nom_client + '_docs/Factures/' + nom_fichier

        # ajout du ticket
        IDTicket=0
        # on s'assure que '0' soit inséré dans la bd si 'MDO' ou 'MAT' sont vides dans la page de saisie
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        # vérifier les paramètres
        cur.execute("SELECT  Affiche_MDO_MAT FROM parametres WHERE IDClient = %s",(client_ident,))
        for row in cur.fetchone():
            if row==1:
                if request.form['mdo'] == '':
                    val_mdo = 0
                else:
                    val_mdo = float(request.form['mdo'])
                if request.form['mat'] == '':
                    val_mat = 0
                else:
                    val_mat = float(request.form['mat'])
            else:
                val_mdo=0
                val_mat=0

        try:
            # vérifier si intervenant a un ID
            IDIntervenant = request.form['fourn_select']
            cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",(request.form['fourn_select'],client_ident ))
            for row_1 in cur.fetchone():
                if row_1=='Autre':
                    IntervAutre = request.form['fourn_autre']
                else: # mettre la rubrique 'Autre' à vide
                    IntervAutre = ''

            id_equip=0
            # pour tenir compte de checkbox 'aucun tag'
            if request.form.get('aucun_tag') == "1":
                id_equip = 0
            else:
                id_equip = request.form.get('id_equipement')

            # case cochée ou non pour 'fermer le ticket'
            if request.form.get('ouvert_ticket') == None:
                statut = 4
            else:
                statut = 3
            if request.form['hres_req'] == '':
                hres_req = 0
            else:
                hres_req = request.form['hres_req']
            cur.execute(
                'INSERT INTO tickets (IDClient, IDUsager, IDIntervenant, IntervenantAutre, DateCreation, DatePrevue,'
                'DateFermeture, Statut, Priorite, TypeTravail, Description_travail, Emplacement, IDCategorie, IDEquipement,'
                'CoutTotalTTC, CoutMainOeuvre, CoutMateriel, DateComplet, HeuresRequises, HeuresEstimees, Nbre_visites) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                [client_ident, profile_list[1], IDIntervenant,
                 IntervAutre, time.strftime('%Y-%m-%d %H:%M'),
                 request.form['date'], request.form['date'], statut, 4, request.form['type_travail'], request.form['desc_travail'],
                 request.form['emplacement'], request.form['categorie'], id_equip, request.form['total_facture_taxes'],
                 val_mdo, val_mat, request.form['date'], hres_req,0,0])
            cnx.commit()
            cur.execute("SELECT @@IDENTITY AS ID;")
            IDTicket = cur.fetchone()[0]
            # noter ID du nouveau ticket pour la facture
        except:
            print(traceback.format_exc())
            # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
            with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + profile_list[7] + '.txt'), 'w') as f:
                f.write('0')
            flash("Problème de traitement: le ticket n'a pas été ajouté.", 'warning')
            if mode == 'dz':
                return render_template('facture_ocr_scan_dz.html', version_client=version_client)
            else:
                return render_template('facture_ocr_scan_dnload.html', version_client=version_client)
        # attribution du fournisseur
        cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",(request.form['fourn_select'],client_ident))
        for item in cur.fetchall():
            if item[1]=='Autre':
                fournisseur=request.form['fourn_autre']
            else:
                fournisseur=item[1]

        cur.execute('INSERT INTO factures (IDClient,DateSaisie,Fournisseur,NoFacture,TotalAvecTx, MDO_HT, MAT_HT, CheminPath,IDTicket) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',[client_ident, request.form['date'],fournisseur,request.form['no_facture'],
                 request.form['total_facture_taxes'], val_mdo, val_mat, chemin_db, IDTicket])
        cnx.commit()
        # ajout du idfacture dans le ticket
        cur.execute("UPDATE tickets SET NoFacture=%s WHERE IDTicket = %s AND IDClient=%s",(request.form['no_facture'],IDTicket,client_ident,))
        cnx.commit()
        cnx.close()
        flash("La facture et le nouveau ticket ont été créés avec succès.", 'warning')

        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_'+profile_list[7]+'.txt'), 'w') as f:
            f.write('0')
        # retour à la page de sélection de fichier pour OCR
        if mode == 'dz':
            return render_template('facture_ocr_scan_dz.html', version_client=version_client)
        else:
            return render_template('facture_ocr_scan_dnload.html', version_client=version_client)
    except:
        print(traceback.format_exc())
        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + profile_list[7] + '.txt'), 'w') as f:
            f.write('0')
        flash("Problème de traitement: la facture n'a pas été ajoutée.", 'warning')
        if mode == 'dz':
            return render_template('facture_ocr_scan_dz.html', version_client=version_client)
        else:
            return render_template('facture_ocr_scan_dnload.html', version_client=version_client)

@bp_ocr.route('/ajout_fournisseur<mode>/', methods=['POST', 'GET'])
def ajout_fournisseur(mode):


    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    # trouver le mode de connexion (Dev ou PA)
    mode_connexion = profile_list[8]
    chemin_ocr = chemin_rep(mode_connexion)
    nom_client=profile_list[7]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    try:
        cur.execute(
            'INSERT INTO intervenants (IDClient, NomIntervenant, IDTypeIntervenant, IDCategorie, Adresse, TelPrincipal, Actif) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            [client_ident, request.form['fourn_new'], 2, request.form['categorie_new'], request.form['adresse_new'],
             request.form['tel_new'], 1])
        cnx.commit()
        cur.execute("SELECT @@IDENTITY AS ID;")
        IDInterv = cur.fetchone()[0]
        cur.reset()
        cur.execute(
            "SELECT IDIntervenant, NomIntervenant, IDCategorie FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
            (IDInterv, client_ident))
        id_fournisseur = 0
        nom_fournisseur = str()
        id_categ = 0
        for row in cur.fetchall():
            id_fournisseur = row[0]
            nom_fournisseur = row[1]
            id_categ = row[2]

        # modifier le statut du fichier 'en usage' pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
            f.write('0')

        # on réaffiche la page de résultats avec le fichier existant et les réglages du nouvel intervenant
        with open(os.path.join(chemin_ocr, 'ocr_params_'+nom_client+'.txt')) as f:
            # contenu_OCR=f.read()
            # print('type:',contenu_OCR)
            contenu_OCR = []
            for line in f:
                # Remove linebreak which is the last character of the string
                curr_place = line[:-1]
                # Add item to the list
                contenu_OCR.append(curr_place)
            #print(contenu_OCR)
            # on remplace les données touchant le fournisseur avec les nouvelles
            contenu_OCR[2] = id_fournisseur
            contenu_OCR[3] = nom_fournisseur
            contenu_OCR[4] = id_categ
            contenu_OCR[5] = ''

            liste_categories = []
            cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 and IDClient=%s", (client_ident,))
            for row in cur.fetchall():
                liste_categories.append(row)

            liste_equipements = []
            cur.execute("SELECT IDEquipement, NumTag, Descriptif FROM equipements WHERE Actif=1 and IDClient=%s", (client_ident,))
            for row in cur.fetchall():
                liste_equipements.append(row)
            cnx.close()

        # ch_fichier_jpg_reduit='../static/temp_images/'+'temp_image_'+nom_client+'.jpg'
        # ch_fichier_pdf=os.path.join(chemin_ocr,'temp_image_'+profile_list[7]+'.pdf')
        # return render_template('facture_ocr_ajout.html', liste_ocr=contenu_OCR, liste_categories=liste_categories,
        #                       liste_equipements=liste_equipements, jpg_reduit=ch_fichier_jpg_reduit, image_pdf=ch_fichier_pdf, version_client=version_client)

        flash("Le fournisseur a été ajouté avec succès. Veuillez reprendre la sélection de la facture.", 'warning')

        if mode=='dz':
            return render_template('facture_ocr_scan_dz.html', version_client=version_client)
        else:
            return render_template('facture_ocr_scan_dnload.html', version_client=version_client)

    except:
        print(traceback.format_exc())
        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
            f.write('0')
        flash("Problème de traitement: le fournisseur n'a PAS été ajouté.", 'warning')
        if mode == 'dz':
            return render_template('facture_ocr_scan_dz.html', version_client=version_client)
        else:
            return render_template('facture_ocr_scan_dnload.html', version_client=version_client)




@bp_ocr.route('/afficher_OCR_attente/<args>',methods=['POST','GET'])
def afficher_OCR_attente(args):
    """Affichage de la page web qui suit 'upload' dans le code 'dropzone' de la page de scan initial
     à partir des données cumulées dans les fichiers texte
    produits par la fonction 'upload' qui suit celle-ci. On lit les fichiers texte pour
    ensuite publier la page.
    Traitement pour une facture qui est rattachée à un ticket. Celui-ci est lancé
    à partir de la table 'tickets en attente de facture' avec le bouton 'Ajouter une facture' et
    une réponse 'Oui' à la boîte de dialogue 'Voulez-vous numériser cette facture?'.
    Étapes:
    def lancer_OCR (ouverture de la page pour sélection de facture selon mode 'dropzone' ou 'dnload'
    def reset si un autre usager du même client est en train de numériser une facture
    def upload (partagée avec traitement SANS ticket associé) pour soumettre la facture à l'OCR et soutirer les infos pertinentes
    def fournisseur si l'usager ajoute un fournisseur à la table 'intervenants' avec le bouton 'Ajouter'
    def annulation si facture non soumise par l'usager
    def facture_ocr si facture est soumise pour sauvegarde incluant numérisation de l'image
    """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    # trouver le mode de connexion (Dev ou PA)
    nom_client=profile_list[7]
    mode_connexion = profile_list[8]
    chemin_ocr=chemin_temp_images(mode_connexion)

    ch_fichier_jpg_taille_orig=str()
    ch_fichier_pdf=str()

    # pour aller chercher les paramètres
    string_1 = args.replace('[', '').replace(']', '').replace("'", "")
    list_1 = string_1.split(',')
    mode = list_1[0]
    id_ticket = list_1[1]

    with open(os.path.join(chemin_ocr, 'ocr_params_'+nom_client+'.txt'), encoding='utf-8') as f:
        #contenu_OCR=f.read()
        #print('type:',contenu_OCR)
        contenu_OCR=[]
        for line in f:
            # Remove linebreak which is the last character of the string
            curr_place = line[:-1]
            # Add item to the list
            contenu_OCR.append(curr_place)

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    # vérifier les paramètres d'affichage de la page de résultats

    liste_affichage=[]
    cur.execute("SELECT AfficheOcrTags, AfficheOcrTicketOuvert, Affiche_MDO_MAT FROM parametres WHERE IDClient = %s", (client_ident,))
    for row in cur.fetchall():
        liste_affichage.append(row)
    #print('liste affichage:',liste_affichage)

    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 and IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)

    liste_intervenants = []
    cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE Actif=1 and IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_intervenants.append(row)
    liste_intervenants.sort(key=lambda x: x[1], reverse=False)

    liste_equipements = []
    cur.execute("SELECT IDEquipement, NumTag, Descriptif FROM equipements WHERE Actif=1 and IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)

    # ch_fichier_jpg_taille_orig=chemin_ocr+'temp_image_'+nom_client+'.jpg'
    # ch_fichier_pdf=chemin_ocr+'temp_image_'+nom_client+'.pdf'
    ch_fichier_jpg_taille_orig = '../static/temp_images/' + 'temp_image_' + profile_list[7] + '.jpg'
    ch_fichier_pdf = '../static/temp_images/' + 'temp_image_' + profile_list[7] + '.pdf'
    liste_ticket = []
    ticket_list = []
    IntervenantNom=str()
    cur.execute("SELECT IDTicket, IDIntervenant, Description_travail, DateComplet, HeuresEstimees, HeuresRequises, "
    "Nbre_visites,Multitags, IntervenantAutre FROM tickets WHERE IDTicket=%s AND IDClient=%s",(id_ticket, client_ident))
    for row in cur.fetchall():
        # vérifier si rubrique 'IntervenantAutre' est remplie
        cur.execute("SELECT NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
                    (row[1], client_ident))
        for item in cur.fetchall():
            if item[0] == 'Autre':
                IntervenantNom = row[8]
            else:
                IntervenantNom = item[0]
        row += (IntervenantNom,)

        ticket_list.append(row)
        #liste_ticket = [list(row) for row in ticket_list]
        # vérifier si c'est un multitags
        if row[7] == 1:
            message = Markup(
                "<b>Ce ticket no." + id_ticket + " est de type 'Multitags' car il s'applique à de multiples équipements.</b><br>") \
                      + Markup(
                "Vous pouvez ainsi partager le montant de la facture avec un ticket dupliqué selon le travail effectué sur chaque équipement.<br>") \
                      + Markup(
                "Un duplicata de ce ticket s'affichera à la fin de cette table dès que vous cliquerez sur 'Dupliquer'.<br>") \
                      + Markup(
                "Lors de l'attribution du numéro de tag et des dépenses sur ces tickets, ne pas oublier de: <br>") \
                      + Markup("- modifier la description <br>") \
                      + Markup("- ajuster les heures requises <br>") \
                      + Markup("- décocher 'multi-tags'")
            flash(message, "warning")
            return redirect(url_for('bp_factures.attente_facture', version=version_client))
    cnx.close()

    # vérifier si fournisseur trouvé dans la table des intervenants
    if contenu_OCR[3] == 'Autre':
        aff_modif_fournisseur = 1
    else:
        aff_modif_fournisseur = 0

    return render_template('facture_ocr_attente_ajout.html',liste_ticket=ticket_list[0], mode=mode, liste_ocr=contenu_OCR,
                           liste_affichage=liste_affichage, liste_categories=liste_categories, liste_intervenants=liste_intervenants,
                           jpg_orig=ch_fichier_jpg_taille_orig, image_pdf=ch_fichier_pdf, affiche_ajouter=aff_modif_fournisseur)

# lorsque l'usager soumet une facture à partir de la page facture_ocr_attente_ajout.html
# (la facture est rattachée à un ticket déjà existant)
@bp_ocr.route('/facture_ocr_attente/<args>', methods=['POST', 'GET'])
def facture_ocr_attente(args):
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    facture_list=[]
    client_ident=profile_list[0]
    version_client=profile_list[6]
    nom_client=profile_list[7]
    # trouver le mode de connexion (Dev ou PA)
    mode_connexion = profile_list[8]
    chemin_ocr=chemin_temp_images(mode_connexion)
    chemin_db=str()

    # pour aller chercher les paramètres
    string_1 = args.replace('[', '').replace(']', '').replace("'", "")
    list_1 = string_1.split(',')
    mode = list_1[0]
    id_ticket = list_1[1]

    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    # modifier le ticket
    try:
        # case cochée ou non pour 'fermer le ticket'
        if request.form.get('ouvert_ticket')==None:
            statut=3
        else:
            statut=4
        if request.form.get('hres_req')==None:
            hres_req=0
        else:
            hres_req=int(request.form.get('hres_req'))
        # obtenir les valeurs actuelles pour TTC, MDO ET MAT du ticket
        cum_TTC=0
        cum_MDO=0
        cum_MAT=0
        nos_factures=''
        cur.execute("SELECT CoutTotalTTC, CoutMainOeuvre, CoutMateriel, NoFacture FROM tickets WHERE IDTicket=%s and IDClient=%s",(id_ticket, client_ident))
        for row in cur.fetchall():
            cum_TTC = row[0]
            cum_MDO = row[1]
            cum_MAT = row[2]
            nos_factures = row[3]
        # ajout des valeurs du scan OCR
        if cum_TTC is not None:
            cum_TTC = float(cum_TTC) + float(request.form.get('total_facture_taxes'))
        else:
            cum_TTC = float(request.form.get('total_facture_taxes'))

        if cum_MDO is not None:
            if request.form.get('mdo') != None:
                if request.form.get('mdo') != '':
                    cum_MDO = float(cum_MDO) + float(request.form.get('mdo'))
        else:
            if request.form.get('mdo') != None:
                if request.form.get('mdo') != '':
                    cum_MDO = float(request.form.get('mdo'))

        if cum_MAT is not None:
            if request.form.get('mat') != None:
                if request.form.get('mat') != '':
                    cum_MAT = float(cum_MAT) + float(request.form.get('mat'))
        else:
            if request.form.get('mat') != None:
                if request.form.get('mat') != '':
                    cum_MAT = float(request.form.get('mat'))

        cur.execute("UPDATE tickets SET CoutTotalTTC=%s, CoutMainOeuvre=%s, CoutMateriel=%s WHERE IDTicket=%s AND IDClient=%s",
                (cum_TTC, cum_MDO, cum_MAT, int(id_ticket), client_ident))
        cnx.commit()

    except:
        print(traceback.format_exc())
        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
            f.write('0')
        flash("Problème de traitement: le ticket n'a pas été ajouté.", 'warning')
        return redirect(url_for('bp_factures.attente_facture'))

    # ajout de facture
    try:

        if request.form['type_fichier']=='pdf':
            # taille max. 0,4MB pour .pdf. Les fichiers images .jpg ont déjà été réduits.
            chemin_fichier = os.path.join(chemin_ocr, 'temp_image_'+nom_client+'.pdf')
            file_stats = os.stat(chemin_fichier)
            taille_pdf = file_stats.st_size

            if taille_pdf>400000:
                flash('Fichier pdf trop grand pour être sauvegardé (maximum de 400K permis).','warning')
            else:
                source_path=chemin_fichier
                nom_fichier_brut = datetime.today().strftime(
                    '%Y-%m-%d') + 'Facture' + datetime.today().strftime('%H:%M:%S') + '.pdf'
                nom_fichier = nom_fichier_brut.replace(':', '')
                dest_path = os.path.join(chemin_factures(mode_connexion,'facture',nom_client), nom_fichier)
                shutil.move(source_path, dest_path)
                chemin_db='documentation/'+profile_list[7]+'_docs/Factures/'+nom_fichier

        else:# c'est un fichier image

            chemin_fichier = os.path.join(chemin_ocr, 'resized_image_' + nom_client+ '.jpg')
            source_path = chemin_fichier
            nom_fichier_brut = datetime.today().strftime(
                '%Y-%m-%d') + 'Facture' + datetime.today().strftime('%H:%M:%S') + '.jpg'
            nom_fichier = nom_fichier_brut.replace(':', '')
            dest_path = os.path.join(chemin_factures(mode_connexion,'facture',nom_client), nom_fichier)
            shutil.move(source_path, dest_path)
            chemin_db = 'documentation/' + nom_client + '_docs/Factures/' + nom_fichier

        val_mdo=float()
        val_mat=float()
        # vérifier les paramètres pour les valeurs de mdo et matériel
        cur.execute("SELECT  Affiche_MDO_MAT FROM parametres WHERE IDClient = %s", (client_ident,))
        for row in cur.fetchone():
            if row == 1:
                if request.form['mdo'] == '':
                    val_mdo = 0
                else:
                    val_mdo = float(request.form['mdo'])
                if request.form['mat'] == '':
                    val_mat = 0
                else:
                    val_mat = float(request.form['mat'])
            else:
                val_mdo = 0
                val_mat = 0

        # attribution du fournisseur
        cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",
            (request.form['fourn_select'], client_ident))
        for item in cur.fetchall():
            if item[1] == 'Autre':
                fournisseur = request.form['fourn_autre']
            else:
                fournisseur = item[1]

        cur.execute('INSERT INTO factures (IDClient,DateSaisie,Fournisseur,NoFacture,TotalAvecTx, MDO_HT, MAT_HT, CheminPath,IDTicket) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)',[client_ident, request.form['date'], fournisseur, request.form['no_facture'],
                 request.form['total_facture_taxes'], val_mdo, val_mat, chemin_db, id_ticket])
        cnx.commit()
        # ajout du idfacture dans le ticket
        if nos_factures is not None:
            nos_factures=str(nos_factures)+','+str(request.form['no_facture'])
        else:
            nos_factures =  str(request.form['no_facture'])
        cur.execute("UPDATE tickets SET NoFacture=%s WHERE IDTicket = %s AND IDClient=%s",(nos_factures, id_ticket, client_ident))
        cnx.commit()
        cnx.close()
        flash("La facture a été créée et le ticket mis à jour avec succès.", 'warning')

        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_'+nom_client+'.txt'), 'w') as f:
            f.write('0')
        # retour à la page des tickets en attente
        return redirect(url_for('bp_factures.attente_facture'))

    except:
        print(traceback.format_exc())
        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(chemin_ocr, 'ocr_en_usage_' + nom_client + '.txt'), 'w') as f:
            f.write('0')
        flash("Problème de traitement: la facture n'a pas été ajoutée.", 'warning')
        return redirect(url_for('bp_factures.attente_facture'))

