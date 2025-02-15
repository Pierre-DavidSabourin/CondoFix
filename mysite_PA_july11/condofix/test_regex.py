import re

# text_list='/ ST # #33 SHERBROOKE KING.O / 3070 RUE KING O / SHERBROOKE QC J1LIC9 / Table 116 / Terminal / 59819019 / Facture / 7254077 / Séquence / 767 / Employé(e) / 152 / Carte / **** 8236 / Credit/MasterCard C / 2022/11/17 / 19.16:09 / VENTE / MONTANT $51.05 / POURBOIRE $5.30 / TOTAL $56.35 / AUTO # 08356Z / Lot 0070 / HTS 20221117191611 / TRANSACTION '
# res=re.findall('\d{4}[(\/.-]\d{2}[(\/.-]\d{2}', text_list)
# print(res)
# date_facture='2022/11/17'
# res=date_facture.replace('/','-')
# print(res)
#
# from datetime import datetime
# date='2023-01-12'
# date_hre = datetime.strptime(date, "%Y-%m-%d")
# print(date_hre.date())

# text="LES ENFANTS TERRIBLES M / 803 RUE PRINCIPALE O, / MAGOG QC J1X2B4 / Table 215 / Terminal 42850600 / Facture 339689 / Séquence 1706 / Caissier 004 / Carte / **** 8236"
# liste_adr=re.findall('\d+\D+[A-Z][0-9O][A-Z]\s?[0-9O][A-Z][0-9O]', text)
# print(liste_adr)
#
# text='je suis arrivé à Magog le 15 Juin 2018'
# date_list=re.findall('\d{1,2}\s\w+[\s\,]\d{4}',text.lower())
# liste_mois=['jan','fev','mars','avril','mai','juin','juill','aout','août','sept','oct','nov','dec']
#
# res= date_list[0]
# for item in liste_mois:
#      if item in res:
#         print('index:', liste_mois.index(item))
#         mois=int(liste_mois.index(item))+1
#         if mois<10:
#             mois_str='0'+str(mois)
#         date=res[-4:]+'/'+mois_str+'/'+res[:2]
# print(date)

#
# text='je suis arrivé à Magog le 15 Novembre, 2018'
# date_fin=str()
# date_list = re.findall('\d{1,2}\s\w+[\s\,]\s*\d{4}',text.lower())
# # # on choisit le premier élément de la liste
# print(date_list)
# if date_list != []:
#     res = date_list[0]
#     liste_mois = ['jan', 'fev', 'mars', 'avril', 'mai', 'juin', 'juill', 'août', 'sept', 'oct', 'nov', 'dec']
#     for item in liste_mois:
#         if item in res:
#             print('index:', liste_mois.index(item))
#             mois = int(liste_mois.index(item)) + 1
#             if mois < 10:
#                 mois_str = '0' + str(mois)
#             else: mois_str= str(mois)
#             date_fin = res[-4:] + '-' + mois_str + '-' + res[:2]
# print(date_fin)

list_trouves=[]
next_elem_2=" 189,98 9.50 4 018.95 1,218.43 "
#next_elem_2=" je ne suis pas 789,34 "
next_elem_2_net = next_elem_2.replace('$', ' ').replace(' ', '  ')
#res_suiv_2 = re.findall('[\,\d]+[\.\,]\d{2}',next_elem_2_net)
#res_suiv_2 = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{1,3},*[\.\,\s]*[0-9][0-9]\s', next_elem_2_net)
#res_suiv_2 = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{1,3},*[\.\,]\d{2}\s', next_elem_2_net)

res_suiv_2 = re.findall('\s[0-9]{1,3}[,\s]*[0-9]{0,3},*[\.\,]\d{2}\s', next_elem_2_net)

if len(res_suiv_2) > 0:
    ##########on doit passer à travers tous les résultats, non seulement le premier!!
    for index, x in enumerate(res_suiv_2):
        # on enlève tous les espaces, virgules et points décimaux
        res = int(res_suiv_2[index].replace(' ', '').replace('.', '').replace(',', ''))
        # on divise le montant entier par 100 pour obtenir deux décimales
        total_trouve = format(res / 100.0, '.02f')
        list_trouves.append(total_trouve)

print(list_trouves)