Text_lower= ['( /)', '(date 18 novembre 2018 /)', '(gem-car - erick /)', '(383 huron st /)', '(stratford, on n5a5t6 /)', '(tel. /)', '((519) 271-4941 /)', '(fax (519) 271-4922 /)', '(hst 101600195rt0001 /)', '(no facture 021687 /)', '(client : 0000000001 /)', '(corporation /)', '(prod qté $ unit. /)', '(pièces /)', '(000000j1 /)', "(changement d'huile (t5} /)", '(02100164 14.72 14.72 /)', '(filtre (proselect) /)', '(eso 105396 5.2 19.33 100.52 /)', '(5w30 mobil1 engine oil /)', '(000000ev 1 /)', '(enviro fee /)', '(0 /)', '(******************** 115.245 tti *** /)', '(sous-total 115.24 /)', '(hst 14.98 /)', '(0.00 /)', '(total /)', '(130.22 /)', '(paiements /)', '(debit card 20.00 /)', '(master card 110.22 /)', '(signature du client :)']
item='novembre'
res_find = filter(lambda x: item in x, Text_lower)
print('res:',list(res_find))
#
# img = Image.open(ch_fichier)
# resized_img = img.thumbnail((624,624))
# #resized_img = img.resize((WIDTH, HEIGHT,))
# ch_resize='photo_Urbano_thumb.jpg'
#resized_img.save(ch_resize)