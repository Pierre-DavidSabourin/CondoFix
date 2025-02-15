from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from azure.cognitiveservices.vision.computervision.models import VisualFeatureTypes
from msrest.authentication import CognitiveServicesCredentials
import re
from nltk.tokenize import RegexpTokenizer
from array import array
import os
from PIL import Image
import sys
import time

'''
Authenticate
Authenticates your credentials and creates a client.
'''
def ocr_doc(nom_fichier):
    # vérifier taille minimale du fichier
    file_stats = os.stat(nom_fichier)
    if file_stats.st_size > 3000000:
        print('Fichier trop grand pour scan')
    subscription_key = "2992d159662044dcba4b47eb3da311fb"
    endpoint = "https://instance-condo.cognitiveservices.azure.com/"

    computervision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))
    '''
    END - Authenticate
    '''

    '''
    OCR: Read File using the Read API, extract text - remote
    This example will extract text in an image, then print results, line by line.
    This API call can also extract handwriting style text (not shown).
    '''

    print("===== Read File - local =====")
    # Get image path
    read_image_path = nom_fichier
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
                #print('x:',line.bounding_box[4],'y:',line.bounding_box[5])

                # on prend les coordonnées y les plus basses de la boîte [1] avec une marge de 0.04
                if (last_y_coord - (0.01*last_y_coord)) < line.bounding_box[5] < (last_y_coord + (0.01*last_y_coord)):
                    complete_line = complete_line + " " + line.text
                else:
                    # print(complete_line)
                    complete_line = complete_line + ' /'
                    line_formated = "(" + complete_line + ")"
                    text_list.append(line_formated)
                    text_str = text_str + " " + complete_line#+str(line.bounding_box)
                    complete_line = line.text
                last_y_coord = line.bounding_box[5]
                last_line = line.text
            # print(complete_line)# pour imprimer dernière ligne
            line_formated = "(" + complete_line + ")"
            text_list.append(line_formated)
            text_str = text_str + " " + complete_line
            #print(text_list)
            print(text_str)
            score_fournisseur(text_str)
            recherche_texte(text_str)
            recherche_montants(text_str)

def score_fournisseur(contenu):
    #Coord_fournisseur_chaine = 'CondoSys 506-255 rue Bellevue Sherbrooke Québec J1J 0B1 819-620-3167'
    #Coord_fournisseur_chaine ='Carl Greer Inc. 912 rue Fluet Valleyfield Québec J6S 0E1 450-374-1860'
    #Coord_fournisseur_chaine ='VISION 12420, 94e avenue, Montréal, (Québec) H1C 1H7 Téléphone: 514-664-0901'
    #Coord_fournisseur_chaine ='TECHNI - TELPRO INC. 515 rue du Colibri, Saint Calixte Québec JOK 1Z0 TÉL.: 514 - 974 - 6500'
    #Coord_fournisseur_chaine ='ÉPOXY GOUPIL INC. 380 rue Ruisseaux Pintendre QC G6C 1P9 418 - 835 - 1020'
    Coord_fournisseur_chaine ='Corest Consultant Bureau: 579-381-9802 5096 Chemin Salaberry, Carignan (Québec) J3L OK4'
    Coord_fournisseur_chaine=Coord_fournisseur_chaine.lower()
    # Utilisation de NTLK pour comparer les chaînes fournisseur et facture
    # comparer tokens du fournisseur avec celui du texte de la facture
    tokenizer = RegexpTokenizer('\w+')
    contenu=contenu.lower()
    tokens_contenu = tokenizer.tokenize(contenu)
    # print(tokens_contenu)
    tokens_fournisseur = tokenizer.tokenize(Coord_fournisseur_chaine)
    items_trouves = 0
    for item in tokens_fournisseur:
        if item in tokens_contenu:
            print(item + ' trouvé')
            items_trouves += 1
    print('Score fournisseur: ', round(items_trouves / len(tokens_fournisseur), 3))

def recherche_texte (text_str):
    liste_totaux=[]
    liste_tps= []
    liste_tvq=[]
    # trouver adresse avant de former la liste
    # chercher les lettres 'O' pour convertir en zéros '0' (codes postaux, montants, tel etc)
    #contenu=contenu_brut.replace('O','0')
    cherche_code=re.findall('[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]',text_str)
    if len(cherche_code)!=0:
        liste_adresse = re.findall('\d+\D+[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]', text_str)
        adresse = liste_adresse[0]
        adresse = adresse.replace('/', '')
        print('Adresse:', adresse)
    else:
        print('Adresse: pas trouvée')

    # convertir la chaîne (majuscules et minuscules) en liste
    liste_contenu = text_str.split('/')
    # trouver nom du fournisseur: habituellement le 2ème item
    print('Nom fournisseur:', liste_contenu[1])

    # convertir toute la chaîne en minuscules
    chaine_contenu = text_str.lower()
    liste_contenu=chaine_contenu.split('/')
    #print(liste_contenu)

    phone_no=str()
    # trouver téléphone du fournisseur
    liste_tel=re.findall('\D*([2-9]\d{2})(\D*)([2-9]\d{2})(\D*)(\d{4})\D* ',text_str)
    if len(liste_tel)>0:
        for item in liste_tel[0]:
            if item.isdigit()==True:
                if len(phone_no) == 0:
                    phone_no = phone_no+ item
                else:
                    phone_no = phone_no + '-' + item
            if len(phone_no)==12:
                print('phone_no:',phone_no)

    for item in liste_contenu:
        if 'facture' in item:
            res_list=re.findall('\s\d{2,12}\s', item)
            if len(res_list)>0:
                # on imprime cette première ligne puis on quitte la boucle
                print('facture no:',res_list[0])
                break

#**********APPROCHE AVEC RECHERCHE DE MONTANTS*************
def recherche_montants(contenu):
    liste_traitee=[]
    # vérifier si les décimales des montants utilisent une virgule
    #liste_montants_virg = re.findall('[\d]+\,\d{2} ', contenu)
    liste_montants_virg = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{1,6},*\,[0-9][0-9]',contenu)
    # montants avec point décimale sans séparateurs de milliers
    #liste_montants_pt = re.findall('[\d]+\.\d{2} ', contenu)
    liste_montants_pt = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{1,3},*\.[0-9][0-9]',contenu)
    liste_montants_pt_1 = re.findall('\s[0-9]{1,3},*\.[0-9][0-9]', contenu)
    print(liste_montants_pt_1)

    if len(liste_montants_pt) > len(liste_montants_virg):
        liste_montants=liste_montants_pt
    else:
        liste_montants= liste_montants_virg
    print('liste montants:',liste_montants)
    i = 0
    for item in liste_montants:
        #print(item)
        liste_montants[i] = liste_montants[i].replace(' ', '')
        cars_tot = len(item)
        #print('index:', item.index(','), 'len:', cars_tot)
        # séparateur de millier en virgule remplacé par aucun espace
        if ',' in item:
            # séparateur de millier en virgule remplacé par aucun espace
            if item.index(',') != (cars_tot - 3):
                ind = int(item.index(','))
                liste_montants[i] = liste_montants[i][:ind-1] + liste_montants[i][ind:]
            # séparateur de décimale en virgule remplacé par un point
            liste_montants[i] = liste_montants[i].replace(',','.')
        i += 1

    print(liste_montants)
    liste_montants_float = [float(x) for x in liste_montants]
    liste_montants_float.sort(reverse=True)
    #print(liste_montants_float)
    # calcul TPS TVQ possible à partir du grand total et vérification des totaux
    tot_facture=liste_montants_float[0]
    print('Total:',tot_facture)
    val_tps=tot_facture*0.043487
    for item in liste_montants_float:
        if val_tps-0.35<item<val_tps+0.35:
            print('TPS:',item)
    val_tvq = tot_facture * 0.08675
    for item in liste_montants_float:
        if val_tvq - 1.25 < item < val_tvq + 1.25:
            print('TVQ:', item)

ocr_doc("../Specimens_factures/CCG.png")
