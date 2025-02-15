import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_dropzone import Dropzone
basedir = os.path.abspath(os.path.dirname(__file__))
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials
import re
from nltk.tokenize import RegexpTokenizer
from PIL import Image
import time
import mysql.connector
import traceback
from datetime import datetime, date

app = Flask(__name__)
app.config.update(
    UPLOADED_PATH= os.path.join(basedir,'static/temp_images'),
    DROPZONE_MAX_FILE_SIZE = 3,
    DROPZONE_TIMEOUT = 5*60*1000,
    DROPZONE_DEFAULT_MESSAGE = 'Glisser le fichier ici ou cliquer pour télécharger')

dropzone = Dropzone(app)
@app.route('/',methods=['POST','GET'])
def home():
    return render_template('index_1.html')

def connect_db():
    """Fonction de connexion à la base de données via objet mysql.connector.

| Requise pour chaque blueprint"""
    db=mysql.connector.connect(user='root', password='aholein1', host='127.0.0.1', database='condofix$condofix')

    #db=mysql.connector.connect(user='CondoFix', password='LacNations_1999',
    #host='CondoFix.mysql.pythonanywhere-services.com', database='CondoFix$condofix')
    return db

    # """Affichage de la table des tickets en attente de facture"""
    # if session.get('ProfilUsager') is None:
    #     # probablement délai de session atteint
    #     return render_template('session_ferme.html')
    # profile_list=session.get('ProfilUsager')
    # # vérifier type d'usager
    # if profile_list[2]==3 or profile_list[2]==5 :# pas accessible par l'employé ou le proprio
    #     return redirect(url_for('bp_admin.permission'))


@app.route('/affiche_OCR',methods=['POST','GET'])
def affiche_OCR():
    with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_params_clientname.txt')) as f:
        #contenu_OCR=f.read()
        #print('type:',contenu_OCR)
        contenu_OCR=[]
        for line in f:
            # Remove linebreak which is the last character of the string
            curr_place = line[:-1]
            # Add item to the list
            contenu_OCR.append(curr_place)

        cnx = connect_db()
        cur = cnx.cursor()
        # liste_intervenants=[]
        # cur.execute("SELECT IDIntervenant, NomIntervenant FROM intervenants WHERE IDClient=%s",(1,))
        # for row in cur.fetchall():
        #     liste_intervenants.append(row)
        # print('interv:',liste_intervenants)
        liste_categories=[]
        cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 and IDClient=%s",(1,))
        for row in cur.fetchall():
            liste_categories.append(row)

        liste_equipements = []
        cur.execute("SELECT IDEquipement, NumTag, Descriptif FROM equipements WHERE Actif=1 and IDClient=%s", (1,))
        for row in cur.fetchall():
            liste_equipements.append(row)

        # vérifier le statut du fichier de paramètres ocr avant de sauvegarder temporairement
        # le statut est remis à '0' lors du clic de bouton 'soumettre' ou 'annuler'
        with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_en_usage_clientname.txt'), 'r') as m:
            contenu_statut = []
            for line in m:
                # Remove linebreak which is the last character of the string
                #curr_place = line[:-1]
                # Add item to the list
                contenu_statut.append(line)
            #print('statut:',int(contenu_statut[0]))
            if int(contenu_statut[0])==1:
                # fichier en cours d'utilisation
                flash("Un autre usager utilise présentement cette fonctionnalité. Veuillez revenir plus tard.",
                      'warning')
                return redirect (url_for('home'))

        # noter que le fichier temporaire est présentement occupé par un autre usager
        with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_en_usage_clientname.txt'), 'w') as f:
            f.write('1')

    return render_template('index_2.html',liste_ocr=contenu_OCR, liste_categories=liste_categories, liste_equipements=liste_equipements)

@app.route('/upload', methods=['POST', 'GET'])
def upload():
    type_fichier = str()
    chemin_fichier =str()
    contenu_OCR=[]
    if request.method == 'POST':
        f = request.files.get('file')
        nom_fichier = f.filename
        if '.pdf' in nom_fichier:
            chemin_fichier=os.path.join(app.config['UPLOADED_PATH'], 'temp_image_test.pdf')
            f.save(chemin_fichier)
            type_fichier = 'pdf'
        else:
            f.save(os.path.join(app.config['UPLOADED_PATH'], 'temp_image_test.jpg'))
            chemin_fichier=os.path.join(app.config['UPLOADED_PATH'], 'temp_image_test.jpg')
            type_fichier = 'image'
            # standardiser taille de l'image pour visualiser dans page OCR
            file_stats = os.stat(chemin_fichier)
            taille_originale = file_stats.st_size
            WIDTH = 624
            HEIGHT = 792
            img = Image.open(chemin_fichier)
            resized_img = img.resize((WIDTH, HEIGHT,))
            resized_img.save(os.path.join(app.config['UPLOADED_PATH'],"resized_image.jpg"))
            # vérifier taille minimale du fichier
            #file_stats = os.stat(os.path.join(app.config['UPLOADED_PATH'],"resized_image.jpg"))
            #print('Taille du fichier:', 'Originale:', taille_originale, 'Finale:', file_stats.st_size)

    statut=1 # pour éviter qu'un autre usager du client utilise cette fonctionnalité SIMULTANÉMENT
    # statut sera remis à '0' une fois que la facture OCR a été traitée voir ligne 421
    contenu_OCR.append(statut)
    contenu_OCR.append(type_fichier)

    # clé d'accès au service OCR de Azure et création d'un client
    subscription_key = "2992d159662044dcba4b47eb3da311fb"
    endpoint = "https://instance-condo.cognitiveservices.azure.com/"

    computervision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))

    print("===== Read File - local =====")
    # Get image path
    read_image_path = chemin_fichier
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
                # print(line.text)
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
            # print(complete_line)# pour imprimer dernière ligne
            line_formated = "(" + complete_line + ")"
            text_list.append(line_formated)
            text_str = text_str + " " + complete_line
            # print(text_list)
            #print(text_str)

    # vérifier que la facture s'adresse au bon syndicat




    # recherche du fournisseur dans la bd
    liste_fournisseurs = []
    liste_fournisseurs_txt = []
    chaine_interv = str()
    cnx = connect_db()
    cur = cnx.cursor()
    cur.execute("SELECT IDIntervenant, NomIntervenant, Adresse, TelPrincipal, IDCategorie FROM intervenants WHERE IDClient=%s", (1,))
    for row in cur.fetchall():
        liste_fournisseurs.append(row)
        chaine_interv=str(row[1]).lower()+' '+str(row[2]).lower()+' '+str(row[3])
        liste_fournisseurs_txt.append(chaine_interv)

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
    if score<=0.70:
        nom_intervenant='Autre'
        # convertir la chaîne (majuscules et minuscules) en liste
        liste_contenu = text_str.split('/')
        # trouver nom du fournisseur dans résultat OCR: habituellement le 2ème item
        fournisseur_OCR = liste_contenu[1]
    else:
        fournisseur_OCR =''

    contenu_OCR.append(id_intervenant)
    contenu_OCR.append(nom_intervenant)
    contenu_OCR.append(id_categ_intervenant)

    # trouver les infos pertinentes dans le scan OCR
    cherche_code = re.findall('[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]', text_str)
    adresse_OCR=str()
    if len(cherche_code) != 0:
        liste_adresse = re.findall('\d+\D+[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]', text_str)
        adresse = liste_adresse[0]
        adresse_OCR = adresse.replace('/', '')
        #print('Adresse:', adresse_OCR)
    else:
        print('Adresse: pas trouvée')

    # trouver no. de téléphone
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
            if len(phone_no) == 12:
                print('phone_no:', phone_no)

    contenu_OCR.append(fournisseur_OCR)
    contenu_OCR.append(adresse_OCR)
    contenu_OCR.append(phone_no)

    # convertir toute la chaîne en minuscules pour trouver 'facture'
    chaine_contenu = text_str.lower()
    liste_contenu = chaine_contenu.split('/')
    no_facture=str()
    for item in liste_contenu:
        if 'facture' in item:
            res_list = re.findall('\s\d{2,12}\s', item)
            if len(res_list) > 0:
                # on imprime cette première ligne puis on quitte la boucle
                no_facture=res_list[0]
                #print('facture no:', no_facture)
                contenu_OCR.append(no_facture)
                break
    if no_facture=='':
        contenu_OCR.append('')

    # ajout de la date d'aujourd'hui
    contenu_OCR.append(time.strftime('%Y-%m-%d'))

    # recherche des montants
    liste_traitee = []
    # vérifier si les décimales des montants utilisent une virgule
    # liste_montants_virg = re.findall('[\d]+\,\d{2} ', contenu)
    liste_montants_virg = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{1,6},*\,[0-9][0-9]', contenu)
    # montants avec point décimale sans séparateurs de milliers
    # liste_montants_pt = re.findall('[\d]+\.\d{2} ', contenu)
    liste_montants_pt = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{1,3},*\.[0-9][0-9]', contenu)
    liste_montants_pt_1 = re.findall('\s[0-9]{1,3},*\.[0-9][0-9]', contenu)
    #print(liste_montants_pt_1)

    if len(liste_montants_pt) > len(liste_montants_virg):
        liste_montants = liste_montants_pt
    else:
        liste_montants = liste_montants_virg
    #print('liste montants:', liste_montants)
    i = 0
    for item in liste_montants:
        # print(item)
        liste_montants[i] = liste_montants[i].replace(' ', '')
        cars_tot = len(item)
        # print('index:', item.index(','), 'len:', cars_tot)
        # séparateur de millier en virgule remplacé par aucun espace
        if ',' in item:
            # séparateur de millier en virgule remplacé par aucun espace
            if item.index(',') != (cars_tot - 3):
                ind = int(item.index(','))
                liste_montants[i] = liste_montants[i][:ind - 1] + liste_montants[i][ind:]
            # séparateur de décimale en virgule remplacé par un point
            liste_montants[i] = liste_montants[i].replace(',', '.')
        i += 1

    #print(liste_montants)
    liste_montants_float = [float(x) for x in liste_montants]
    liste_montants_float.sort(reverse=True)
    #print('liste montants float:',liste_montants_float)
    # calcul TPS TVQ possible à partir du grand total et vérification des totaux
    tot_facture = 0
    if len(liste_montants_float)>0:
        tot_facture = liste_montants_float[0]
    contenu_OCR.append(tot_facture)

    val_tps = tot_facture * 0.043487
    for item in liste_montants_float:
        if val_tps - (0.001*val_tps) < item < val_tps + (0.001*val_tps):
            tps=item
            contenu_OCR.append(tps)
            print('TPS:', item)
    val_tvq = tot_facture * 0.08675
    for item in liste_montants_float:
        if val_tvq - (0.001*val_tvq) < item < val_tvq + (0.001*val_tvq):
            tvq=item
            contenu_OCR.append(tvq)
            print('TVQ:', tvq)

    #Mots clés pour description auto en ordre de fréquence probable dans les factures
    replac = 'répar, modif, travaux, travail, change, remplace, nett, peintur, pose, entretien, install, lav, faire, fourni, honoraires,' \
             'refaire, corrig, inspect, renov, replac, aménag, adapt, arrang, confection,  colmat, déménage, implant, renouvel'
    mots_desc= replac
    liste_mots_cles=mots_desc.split(',')
    desc_ocr=str()
    desc_brut=str()
    # convertir tous les caractères de la liste en minuscules
    text_list_lower=list(map(lambda x: x.lower(), text_list))
    # rechercher lignes dans la liste contenant un des mots clés
    for item in liste_mots_cles:
        res = list(filter(lambda x: item in x, text_list_lower))
        if len(res)>0:
            # on sélectionne l'élément trouvé plus la ligne suivante
            desc_brut = res[0]
            desc_ocr=desc_brut.replace('(','').replace(')','').replace('/','')
            break
    contenu_OCR.append(desc_ocr)

    # sauvegarde des paramètres dans fichier texte identifié au client pour utiliser dans l'appel de def 'permission'
    with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_params_clientname.txt'), 'w+') as f:
        #f.write(type_fichier)
        for listitem in contenu_OCR:
             f.write(f'{listitem}\n')

    return ''

@app.route('/reset', methods=['POST', 'GET'])
def reset():
    # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
    with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_en_usage_clientname.txt'), 'w') as f:
        f.write('0')
    return render_template('index_1.html')

@app.route('/annulation', methods=['POST', 'GET'])
def annulation():
    # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
    with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_en_usage_clientname.txt'), 'w') as f:
        f.write('0')
    return render_template('index_1.html')

@app.route('/facture_ocr', methods=['POST', 'GET'])
def facture_ocr():
    IDTicket=0
    cnx = connect_db()
    cur = cnx.cursor()
    # créer un ticket
    try:
        # case cochée ou non pour 'fermer le ticket'
        if request.form.get('ferme_ticket')==None:
            statut=3
        else:
            statut=4

        cur.execute('INSERT INTO tickets (IDClient, IDUsager, IDIntervenant, IntervenantAutre, DateCreation, '
                    'Statut, Priorite, TypeTravail, Description_travail, Emplacement, IDCategorie, IDEquipement, '
                    'CoutTotalTTC, DateComplet, HeuresRequises) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                    [1, 1, request.form['id_fournisseur'],
                     request.form['fourn_autre'],
                     time.strftime('%Y-%m-%d %H:%M'),statut, 4,request.form['type_travail'], request.form['desc_travail'],
                     request.form['emplacement'], request.form['categorie'], request.form['id_equipement'],request.form['total_facture_taxes'],
                     request.form['date'], request.form['hres_req']])
        cnx.commit()
        # trouver identifiant de l'enregistrement créé plus haut
        cur.execute("SELECT @@IDENTITY AS ID;")
        IDTicket= cur.fetchone()[0]
        # noter ID du nouveau ticket pour la facture
    except:
        print(traceback.format_exc())
        flash("Problème de traitement: le ticket n'a pas été ajouté.", 'warning')
        return render_template('index_1.html')

    # ajout de facture
    try:
        # sauvegarder image dans la documentation
        # s'assurer que l'image temporaire est toujours la bonne
        with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_en_usage_clientname.txt'), 'r') as m:
            contenu_statut = []
            for line in m:
                # Remove linebreak which is the last character of the string
                # curr_place = line[:-1]
                # Add item to the list
                contenu_statut.append(line)
            # print('statut:',int(contenu_statut[0]))
            if int(contenu_statut[0]) == 0:
                # fichier a été réinitialisé
                flash("Un autre usager a réinitialisé la saisie de facture. Le fichier ne sera pas sauvegardé.",
                      'warning')
            # else:
            #     if request.form['type_fichier']=='pdf':
            #         # taille max. 0,7MB pour .pdf. Les fichiers images .jpg ont déjà été réduits.
            #         chemin_fichier = os.path.join(app.config['UPLOADED_PATH'], 'temp_image_test.pdf')
            #         file_stats = os.stat(chemin_fichier)
            #         taille_pdf = file_stats.st_size
            #         print('taille pdf:',taille_pdf)
            #         if taille_pdf>500000:
            #             flash('Fichier pdf trop grand pour être sauvegardé (maximum de 500K permis).','warning')
            #         # pour éviter de mêler les fichiers lors de l'affichage
            #         # ajout d'un time stamp avec secondes au titre 'Facture.pdf ou 'Facture.jpg'
            #         # f.save temp_image_test.pdf ex. '2022-11-25 15:35 Facture.pdf' dans documentation/Client_docs/Factures
            #         chemin_db=''
            #     else:# c'est un fichier image
            #         chemin_db = ''
        chemin_db = ''
        cur.execute('INSERT INTO factures (IDClient,DateSaisie,Fournisseur,NoFacture,TotalAvecTx,CheminPath,IDTicket) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s)',[1, request.form['date'],request.form['fournisseur'],request.form['no_facture'],
                 request.form['total_facture_taxes'], chemin_db, IDTicket])
        cnx.commit()
        # ajout du idfacture dans le ticket
        cur.execute("UPDATE tickets SET NoFacture=%s WHERE IDTicket = %s AND IDClient=%s",(request.form['no_facture'],IDTicket,1,))
        cnx.commit()
        cnx.close()
        flash("La facture et le nouveau ticket ont été créés avec succès.", 'warning')

        # modifier le statut du fichier de paramètres ocr pour le rendre accessible (statut =0)
        with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_en_usage_clientname.txt'), 'w') as f:
            f.write('0')

        return render_template('index_1.html')
    except:
        print(traceback.format_exc())
        flash("Problème de traitement: la facture n'a pas été ajoutée.", 'warning')
        return render_template('index_1.html')


@app.route('/ajout_fournisseur', methods=['POST', 'GET'])
def ajout_fournisseur():
    cnx = connect_db()
    cur = cnx.cursor()
    try:
        cur.execute(
        'INSERT INTO intervenants (IDClient, NomIntervenant, IDTypeIntervenant, IDCategorie, Adresse, TelPrincipal, Actif) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s)',
        [1, request.form['fourn_new'], 2, request.form['categorie_new'],request.form['adresse_new'],request.form['tel_new'], 1])
        cnx.commit()
        cur.execute("SELECT @@IDENTITY AS ID;")
        IDInterv = cur.fetchone()[0]
        cur.reset()
        cur.execute("SELECT IDIntervenant, NomIntervenant, IDCategorie FROM intervenants WHERE IDIntervenant=%s AND IDClient=%s",(IDInterv,1))
        id_fournisseur=0
        nom_fournisseur=str()
        id_categ=0
        for row in cur.fetchall():
            id_fournisseur=row[0]
            nom_fournisseur=row[1]
            id_categ=row[2]

        # on réaffiche la page de résultats avec le fichier existant et les réglages du nouvel intervenant
        with open(os.path.join(app.config['UPLOADED_PATH'], 'ocr_params_clientname.txt')) as f:
            # contenu_OCR=f.read()
            # print('type:',contenu_OCR)
            contenu_OCR = []
            for line in f:
                # Remove linebreak which is the last character of the string
                curr_place = line[:-1]
                # Add item to the list
                contenu_OCR.append(curr_place)
            print(contenu_OCR)
            # on remplace les données touchant le fournisseur avec les nouvelles
            contenu_OCR[2]=id_fournisseur
            contenu_OCR[3]=nom_fournisseur
            contenu_OCR[4]=id_categ
            contenu_OCR[5] = ''

            liste_categories = []
            cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 and IDClient=%s", (1,))
            for row in cur.fetchall():
                liste_categories.append(row)

            liste_equipements = []
            cur.execute("SELECT IDEquipement, NumTag, Descriptif FROM equipements WHERE Actif=1 and IDClient=%s", (1,))
            for row in cur.fetchall():
                liste_equipements.append(row)
            cnx.close()
        return render_template('index_2.html', liste_ocr=contenu_OCR, liste_categories=liste_categories,
                               liste_equipements=liste_equipements)

    except:
        print(traceback.format_exc())
        flash("Problème de traitement: le fournisseur n'a PAS été ajouté.", 'warning')
        return render_template('index_1.html')


if __name__ == '__main__':
    app.secret_key = 'super secret key'
    app.run(debug=True)