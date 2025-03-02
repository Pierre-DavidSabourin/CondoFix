from flask import Blueprint, render_template,json,session,request,redirect,url_for, flash
import mysql.connector
from io import StringIO
import unicodedata
import csv
from werkzeug.wrappers import Response
import traceback
from mysite_PA_july11.utils import connect_db

bp_preventif = Blueprint('bp_preventif', __name__)

#********************PREVENTIF****************************************
#page de la liste d'activités du calendrier d'entretien avec fonction ajout/modif
@bp_preventif.route("/preventif")
def preventif():
    """Afficher la table contenant toutes les activités d'entretien régulier et préventif via le
    calendrier d'entretien.

    |Ces enregistrements permettent de générer automatiquement un ticket à la date 'prochain' spécifiée."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager
    if profile_list[2]==3 or profile_list[2]==5 :# pas accessible par l'employé ou le proprio
        return redirect(url_for('bp_admin.permission'))

    client_ident=profile_list[0]
    version_client=profile_list[6]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    cur.execute(
        "SELECT IDPreventif, Description, Emplacement, HresEstimees, IDIntervenant, IDEquipement, IDCategorie, FreqAns, DateProchain,ReferenceCarnet, IDTypeTravail,"
        "Janv, Fev, Mars, Avril, Mai, Juin, Juil, Aout, Sept, Oct, Nov, `Dec`  FROM preventif WHERE IDClient=%s",
        (client_ident,))
    liste_preventif = []
    for row in cur.fetchall():
        # si pas de IDEquipement
        if row[5] == None or row[5] == 0:
            row += ('',)
        else:
            cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s", (row[5], client_ident))
            for item in cur.fetchall():
                row += (str(item[0])+', '+item[1],)  # 23
        cur.execute("SELECT NomIntervenant From intervenants WHERE IDIntervenant=%s AND IDClient=%s",
                    (row[4], client_ident))
        for item_1 in cur.fetchall():
            row += (item_1[0],)  # 24
        cur.execute("SELECT Description From categories WHERE IDCategorie=%s AND IDClient=%s", (row[6], client_ident))
        for item_2 in cur.fetchall():
            row += (item_2[0],)  # 25
        cur.execute("SELECT Description From typetravail WHERE IDTypeTravail=%s", (row[10],))
        for item_3 in cur.fetchall():
            row += (item_3[0],)  # 26
        liste_preventif.append(row)
    cnx.close()
    liste_preventif.sort(key=lambda x: x[0], reverse=False)

    return render_template('preventif_table.html', version=version_client, fill_preventif=liste_preventif,bd=profile_list[3])

#fonctions pour ajouter ou modifier un entretien préventif
@bp_preventif.route('/preventif_enreg/<parametre>')
def preventif_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    version_client = profile_list[6]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()

    liste_intervenants=[]
    cur.execute("SELECT IDIntervenant, NomIntervenant, IDCategorie FROM intervenants WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_intervenants.append(row)
    liste_intervenants.sort(key=lambda tup: tup[1])
    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    liste_equipements=[]
    cur.execute("SELECT IDEquipement, Nom, IDCategorie,NumTag FROM equipements WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_equipements.append(row)
    list_res = set(map(lambda x:x[2], liste_equipements))
    list_categ_avec_tags=list(list_res)
    list_equip = [[(y[3],y[1]) for y in liste_equipements if y[2]==x] for x in list_categ_avec_tags]
    id_categorie=0
    # si nouveau parametre =0, si modif parametre=liste de valeurs de l'enregistrement (item de fill_preventifs)
    if parametre=='0':
        cnx.close()
        return render_template('preventif_ajout.html',version=version_client,liste_intervenants=liste_intervenants,
                               list_categ_avec_tags=json.dumps(list_categ_avec_tags),liste_categories=liste_categories,
                               list_equip=json.dumps(list_equip), bd=profile_list[3])

    else:
        cur.execute("SELECT IDPreventif, Description, Emplacement, HresEstimees, IDIntervenant, IDEquipement, IDCategorie, FreqAns, DateProchain,"
                    "ReferenceCarnet, IDTypeTravail,Janv, Fev, Mars, Avril, Mai, Juin, Juil, Aout, Sept, Oct, Nov, `Dec`  FROM preventif "
                    "WHERE IDPreventif=%s AND IDClient=%s",(parametre,client_ident))
        liste_preventif=[]
        tag_desc = str()
        tag_id = 0
        for row in cur.fetchall():
            if row[5] == None:
                row += ('',)
            else:
                cur.execute("SELECT NumTag, Nom FROM equipements WHERE IDEquipement=%s AND IDClient=%s",
                            (row[5], client_ident))
                for item in cur.fetchall():
                    tag_desc = str(item[0]) + ', ' + item[1]
                    tag_id = item[0]
            liste_preventif.append(row)
            id_categorie = row[6]
        liste_equipements = []
        liste_equip_en_cours = []
        cur.execute("SELECT NumTag, Nom, IDCategorie FROM equipements WHERE Actif=1 AND IDClient=%s", (client_ident,))
        for row in cur.fetchall():
            liste_equipements.append(row)
            if row[2] == id_categorie:
                liste_equip_en_cours.append(row)
        # pour afficher les tags et descriptions correctement
        liste_equip_actuel = [(y[0], y[1], y[2]) for y in liste_equip_en_cours]

        list_res_2 = set(map(lambda x: x[2], liste_equipements))
        list_categ_avec_tags = list(list_res_2)
        cnx.close()
        list_equip = [[(y[0], y[1]) for y in liste_equipements if y[2] == x] for x in list_categ_avec_tags]
        cnx.close()

        return render_template('preventif_modif.html', version=version_client, liste_preventif= liste_preventif, liste_categories=liste_categories,
                               liste_intervenants=liste_intervenants,list_categ_avec_tags=json.dumps(list_categ_avec_tags),
                               list_equip=json.dumps(list_equip), liste_equip_en_cours=liste_equip_actuel,tag_desc=tag_desc, tag_id=tag_id,
                               bd=profile_list[3])

@bp_preventif.route("/preventif_ajout", methods=['POST','GET'])
def preventif_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident = profile_list[0]
    version_client = profile_list[6]
    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    # éviter erreur si IDEquipement=Null et pour tenir compte de checkbox 'aucun tag' et pour convertir NumTag en IDEquipement
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    args_interv = request.form['ident_intervenant'].replace('(', '').replace(')', '').split(',')
    id_interv = args_interv[0]

    no_equip=int()
    if request.form.get('aucun_tag')==None:
        if request.form.get('tag')==None or request.form.get('tag')=='':
            no_equip=0
        else:
            cur.execute("SELECT IDEquipement FROM equipements WHERE NumTag=%s AND IDClient=%s", (request.form['tag'], client_ident))
            for item in cur.fetchall():
                no_equip = item[0]
    if request.form.get('aucun_tag')=="1":
        no_equip=0
   # gestion des cases de mois
    cum_mois=0
    if request.form.get('Janv')==None:
        val_janv=0
    else:
        val_janv=1
        cum_mois+=1
    if request.form.get('Fev')==None:
        val_fev=0
    else:
        val_fev=1
        cum_mois+=1
    if request.form.get('Mars')==None:
        val_mars=0
    else:
        val_mars=1
        cum_mois+=1
    if request.form.get('Avril')==None:
        val_avril=0
    else:
        val_avril=1
        cum_mois+=1
    if request.form.get('Mai')==None:
        val_mai=0
    else:
        val_mai=1
        cum_mois+=1
    if request.form.get('Juin')==None:
        val_juin=0
    else:
        val_juin=1
        cum_mois+=1
    if request.form.get('Juil')==None:
        val_juil=0
    else:
        val_juil=1
        cum_mois+=1
    if request.form.get('Aout')==None:
        val_aout=0
    else:
        val_aout=1
        cum_mois+=1
    if request.form.get('Sept')==None:
        val_sept=0
    else:
        val_sept=1
        cum_mois+=1
    if request.form.get('Oct')==None:
        val_oct=0
    else:
        val_oct=1
        cum_mois+=1
    if request.form.get('Nov')==None:
        val_nov=0
    else:
        val_nov=1
        cum_mois+=1
    if request.form.get('Dec')==None:
        val_dec=0
    else:
        val_dec=1
        cum_mois+=1

    # seulement 1 mois peut être coché si fréquence ans >1
    if int(cum_mois)>1 and int(request.form['freq'])>1:
        flash("Veuillez sélectionner SEULEMENT un mois lorsque la fréquence annuelle excède 1 an.","warning")
        return redirect(url_for('bp_preventif.preventif_enreg',parametre=0))
    if int(cum_mois)==0:
        flash("Veuillez sélectionner au moins un mois pour l'entretien préventif.","warning")
        return redirect(url_for('bp_preventif.preventif_enreg',parametre=0))
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]

    # dans mysql, 'Dec' est un mot réservé qui donne l'erreur 1064 lorsqu'utilisé. Ajout de guillements inversés `Dec` pour régler le problème
    cur.execute("INSERT INTO preventif (IDClient,Description, Emplacement, HresEstimees, IDIntervenant, IDEquipement, IDCategorie, ReferenceCarnet,"
                " DateProchain, FreqAns, IDTypeTravail, Janv, Fev, Mars, Avril, Mai, Juin, Juil, Aout, Sept, Oct, Nov,`Dec`) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [client_ident, request.form['description'], request.form['emplacement'], request.form['hres_est'], id_interv,
                 no_equip,request.form['ident_categ'], request.form['reference'], request.form['date_proch'], request.form['freq'],request.form['type_travail'],
                 val_janv, val_fev, val_mars, val_avril, val_mai, val_juin, val_juil, val_aout, val_sept, val_oct, val_nov, val_dec])

    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_preventif.preventif'))

@bp_preventif.route('/preventif_modif/<ident_preventif>', methods=['POST','GET'])
def preventif_modif(ident_preventif):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')

    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    # gestion des cases de mois
    cum_mois=0
    if request.form.get('Janv')==None:
        val_janv=0
    else:
        val_janv=1
        cum_mois+=1
    if request.form.get('Fev')==None:
        val_fev=0
    else:
        val_fev=1
        cum_mois+=1
    if request.form.get('Mars')==None:
        val_mars=0
    else:
        val_mars=1
        cum_mois+=1
    if request.form.get('Avril')==None:
        val_avril=0
    else:
        val_avril=1
        cum_mois+=1
    if request.form.get('Mai')==None:
        val_mai=0
    else:
        val_mai=1
        cum_mois+=1
    if request.form.get('Juin')==None:
        val_juin=0
    else:
        val_juin=1
        cum_mois+=1
    if request.form.get('Juil')==None:
        val_juil=0
    else:
        val_juil=1
        cum_mois+=1
    if request.form.get('Aout')==None:
        val_aout=0
    else:
        val_aout=1
        cum_mois+=1
    if request.form.get('Sept')==None:
        val_sept=0
    else:
        val_sept=1
        cum_mois+=1
    if request.form.get('Oct')==None:
        val_oct=0
    else:
        val_oct=1
        cum_mois+=1
    if request.form.get('Nov')==None:
        val_nov=0
    else:
        val_nov=1
        cum_mois+=1
    if request.form.get('Dec')==None:
        val_dec=0
    else:
        val_dec=1
        cum_mois+=1

    # seulement 1 mois peut être coché si fréquence ans >1
    if int(cum_mois)>1 and int(request.form['freq'])>1:
        flash("Veuillez sélectionner SEULEMENT un mois lorsque la fréquence annuelle excède 1 an.","warning")
        return redirect(url_for('bp_preventif.preventif_enreg',parametre=ident_preventif))
    if int(cum_mois)==0:
        flash("Veuillez sélectionner au moins un mois pour l'entretien préventif.","warning")
        return redirect(url_for('bp_preventif.preventif_enreg',parametre=ident_preventif))
    # case 'actif'
    if request.form.get('actif')==None:
        val_actif=0
    else: val_actif=1

    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    version_client = profile_list[6]
    try:
        mode_connexion = profile_list[8]
        cnx = connect_db(mode_connexion)
        cur = cnx.cursor()
        if version_client==1:
            tag_no=0
            # pour tenir compte de checkbox 'aucun tag'
            if request.form.get('aucun_tag')==None:
                if request.form.get('tag')==None or request.form.get('tag')=='':
                    tag_no=0
                else:
                    tag_no=request.form['tag']
            if request.form.get('aucun_tag')=="1":
                tag_no=0

            # pour s'assurer que la catégorie corresponde au tag sélectionné s'il y a lieu
            no_equip=0
            id_categorie=0
            if tag_no == 0:
                id_categorie = request.form['categorie']
            else:
                cur.execute("SELECT IDCategorie, IDEquipement from equipements WHERE NumTag=%s AND IDClient=%s",(tag_no, client_ident))
                for item in cur.fetchall():
                    id_categorie = item[0]
                    no_equip=item[1]
        else:
            no_equip=None
            id_categorie=request.form['categorie']
        cur.execute("UPDATE preventif SET Description=%s, Emplacement=%s, HresEstimees=%s, IDIntervenant=%s, IDEquipement=%s, IDCategorie=%s, "
                    "IDTypeTravail=%s, ReferenceCarnet=%s, DateProchain=%s, FreqAns=%s, Janv=%s, Fev=%s, "
                     "Mars=%s, Avril=%s, Mai=%s, Juin=%s, Juil=%s, Aout=%s, Sept=%s, Oct=%s, Nov=%s, `Dec`=%s WHERE IDPreventif = %s AND IDClient=%s",
                     [request.form['description'], request.form['emplacement'], request.form['hres_est'], request.form['ident_intervenant'],
                      no_equip, id_categorie, request.form['type_travail'], request.form['reference'], request.form['date_proch'],
                        request.form['freq'],val_janv, val_fev, val_mars, val_avril, val_mai, val_juin, val_juil, val_aout,
                      val_sept, val_oct, val_nov, val_dec, ident_preventif,client_ident,])
        cnx.commit()
        cnx.close()

        return redirect(url_for('bp_preventif.preventif'))
    except:
        print(traceback.format_exc())

#fonction pour supprimer preventif
@bp_preventif.route("/supprimer/<id_preventif>", methods=['POST','GET'])
def supprimer(id_preventif):
    """Supprimer un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("DELETE FROM preventif WHERE IDPreventif=%s AND IDClient=%s",(id_preventif,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_preventif.preventif'))

@bp_preventif.route('/export_csv_4', methods=['POST','GET'])
def export_csv_4():
    """Exporter les données des préventifs dans un fichier CSV"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non..admin syndicat non admis
    if profile_list[2] > 2 :
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute(
        "SELECT IDPreventif, Description, Emplacement, HresEstimees, IDIntervenant, IDEquipement, IDCategorie, FreqAns, DateProchain,ReferenceCarnet, IDTypeTravail,"
        "Janv, Fev, Mars, Avril, Mai, Juin, Juil, Aout, Sept, Oct, Nov, `Dec`  FROM preventif WHERE IDClient=%s",(client_ident,))
    liste_preventif = []
    for row in cur.fetchall():
        # si pas de IDEquipement
        if row[5]==None or row[5]==0:
            row += ('',)
        else:
            cur.execute("SELECT NumTag FROM equipements WHERE IDEquipement=%s AND IDClient=%s", (row[5], client_ident))
            for item in cur.fetchall():
                row += (item[0],)#22
        cur.execute("SELECT NomIntervenant From intervenants WHERE IDIntervenant=%s AND IDClient=%s", (row[4],client_ident))
        for item_1 in cur.fetchall():
            row += (item_1[0],)#23
        cur.execute("SELECT Description From categories WHERE IDCategorie=%s AND IDClient=%s", (row[6],client_ident))
        for item_2 in cur.fetchall():
            row += (item_2[0],)#24
        cur.execute("SELECT Description From typetravail WHERE IDTypeTravail=%s", (row[10],))
        for item_3 in cur.fetchall():
            row += (item_3[0],)#25
        print(row)
        liste_preventif.append(row)
    cnx.close()
    liste_preventif.sort(key=lambda x: x[0], reverse=False)
    #print('Liste préventif:',liste_preventif)
    def generate():
        data = StringIO()
        w = csv.writer(data)
        # création d'entêtes pour le fichier csv
        entetes=['IDPreventif', 'Description', 'Emplacement', 'HresEstimees', 'Intervenant', 'Tag Equipement', 'Categorie', 'FreqAns',
                 'DateProchain', 'ReferenceCarnet', 'TypeTravail', 'Janv', 'Fev', 'Mars', 'Avril', 'Mai', 'Juin', 'Juil', 'Aout',
                 'Sept', 'Oct', 'Nov', 'Dec']
        w.writerow(entetes)
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        for item in liste_preventif:
           # supprimer les accents
            description= ''.join((c for c in unicodedata.normalize('NFD', item[1]) if unicodedata.category(c) != 'Mn'))
            emplacement= ''.join((c for c in unicodedata.normalize('NFD', item[2]) if unicodedata.category(c) != 'Mn'))
            intervenant = ''.join((c for c in unicodedata.normalize('NFD', item[23]) if unicodedata.category(c) != 'Mn'))
            categorie= ''.join((c for c in unicodedata.normalize('NFD', item[24]) if unicodedata.category(c) != 'Mn'))
            type_travail = ''.join((c for c in unicodedata.normalize('NFD', item[25]) if unicodedata.category(c) != 'Mn'))

            w.writerow([item[0],description,emplacement,item[3],intervenant,item[22],categorie,item[7],item[8],item[9],
                        type_travail,item[11],item[12],item[13],item[14],item[15],item[16],item[17],item[18],item[19],item[20],
                        item[21],item[22]])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    # stream the response as the data is generated
    response = Response(generate(), mimetype='text/csv')
    # ajouter nom de fichier
    response.headers.set("Content-Disposition", "attachment", filename="CondoFix_Export_Calendrier_Entretien.csv")
    return response