from flask import Blueprint, render_template,g,session,request,redirect,url_for
import mysql.connector
from io import StringIO
import unicodedata
import csv
from werkzeug.wrappers import Response
from utils import connect_db

bp_equipements = Blueprint('bp_equipements', __name__)

#********************EQUIPEMENTS****************************************
#page de la liste d'équipements avec fonction ajout
@bp_equipements.route("/equipements")
def equipements():
    """afficher la page de la liste d'équipements avec fonction ajout et modif
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager est copropriétaire
    if profile_list[2]==5:
        return redirect(url_for('bp_admin.permission'))
    fill_equipements=[]
    client_ident=profile_list[0]
    mode_connexion=profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT IDEquipement, Nom, Descriptif, IDCategorie, Emplacement, DateInstallation, ValeurRemplacement_$, "
    "DateRemplacement, Actif, NumTag FROM equipements WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        if row[8]==1:
            actif='oui'
        else:
            actif='non'
        row+=(actif,)#10
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s AND IDClient=%s", (row[3],client_ident))
        for item in cur.fetchall():
            nom_categorie=item
            row+=(nom_categorie)#11
        fill_equipements.append(row)
    fill_equipements.sort(key=lambda x: x[9], reverse=False)
    cnx.commit()
    cnx.close()
    return render_template('equipements_table.html', fill_equipements=fill_equipements,bd=profile_list[3])

#page enregistrement(nouveau ou modifier)
@bp_equipements.route("/equipement_enreg/<parametre>")
def equipement_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""
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
    liste_categories=[]
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    # si nouveau parametre =0, si modif parametre=liste de valeurs de l'enregistrement (item de fill_equipement)
    if parametre=='0':
        cnx.close()
        return render_template('equipement_ajout.html', liste_categories=liste_categories,bd=profile_list[3])
    else:
        liste_equipement=[]
        cur.execute("SELECT IDEquipement, NumTag, Nom, Descriptif, IDCategorie, Emplacement, DateInstallation, ValeurRemplacement_$, "
                    "DateRemplacement, Actif FROM equipements WHERE IDEquipement=%s AND IDClient=%s",(parametre,client_ident))
        for row in cur.fetchall():
            liste_equipement.append(row)
        cnx.close()
        return render_template('equipement_modif.html', liste_equipement= liste_equipement,liste_categories=liste_categories,bd=profile_list[3])

#fonctions pour ajouter ou modifier un équipement
@bp_equipements.route("/equipement_ajout", methods=['POST'])
def equipement_ajout():
    """Ajouter un équipement dans la table mysql suivi par retour à la table des équipements"""
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
    max_num_tag=int()
    cur.execute("SELECT MAX(NumTag) FROM equipements WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchone():
        if row!=None:
            max_num_tag=int(row)
        else:
            max_num_tag=0
    new_num_tag=max_num_tag+1
    cur.reset()
    cur.execute('INSERT INTO equipements (IDClient, NumTag, Nom, Descriptif, IDCategorie, Emplacement,  DateInstallation, ValeurRemplacement_$, '
                 'DateRemplacement, Actif) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                 [client_ident, new_num_tag, request.form['equipement_nom'], request.form['equipement_desc'], request.form['equipement_cat'],
                  request.form['emplacement'], request.form['date_install'], request.form['equipement_val'], request.form['date_rempl'], 1])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_equipements.equipements'))

@bp_equipements.route('/equipement_modif/<ident_equipement>', methods=['POST'])
def equipement_modif(ident_equipement):
    """Modifier un équipement dans la table mysql (ident_equipement) suivi par retour à la table des équipements"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non..admin syndicat non admis
    if profile_list[2] > 2 :
        return redirect(url_for('bp_admin.permission'))
    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("UPDATE equipements SET Nom=%s, Descriptif=%s, IDCategorie=%s, Emplacement=%s,  DateInstallation=%s, ValeurRemplacement_$=%s, DateRemplacement=%s, Actif=%s WHERE IDEquipement=%s AND IDClient=%s",
                 [request.form['equipement_nom'], request.form['equipement_desc'], request.form['equipement_cat'], request.form['emplacement'],
                  request.form['date_install'], request.form['equipement_val'], request.form['date_rempl'], val_actif, ident_equipement,client_ident])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_equipements.equipements'))


@bp_equipements.route('/export_csv', methods=['POST','GET'])
def export_csv():
    """Exporter les données des équipements dans un fichier CSV"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non..admin syndicat non admis
    if profile_list[2] > 2 :
        return redirect(url_for('bp_admin.permission'))
    equip_list=[]
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT NumTag, Nom, Descriptif, IDCategorie, Emplacement, DateInstallation, ValeurRemplacement_$, DateRemplacement, Actif "
               "FROM equipements WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        cur.execute("SELECT Description From categories WHERE IDCategorie=%s", (row[3],))
        for item in cur.fetchall():
            row+=(item)
        equip_list.append(row)
    cnx.close()
    equip_list.sort(key=lambda x: x[0], reverse=False)
    def generate():
        data = StringIO()
        w = csv.writer(data)
        # création d'entêtes pour le fichier csv
        entetes=['Tag', 'Nom', 'Descriptif', 'IDCategorie', 'Emplacement', 'DateInstallation', 'ValeurRemplacement_$', 'DateRemplacement', 'Actif', 'Categorie']
        w.writerow(entetes)
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        for item in equip_list:
           # supprimer les accents
            nom = ''.join((c for c in unicodedata.normalize('NFD', item[1]) if unicodedata.category(c) != 'Mn'))
            descriptif = ''.join((c for c in unicodedata.normalize('NFD', item[2]) if unicodedata.category(c) != 'Mn'))
            emplacement= ''.join((c for c in unicodedata.normalize('NFD', item[4]) if unicodedata.category(c) != 'Mn'))
            categorie= ''.join((c for c in unicodedata.normalize('NFD', item[9]) if unicodedata.category(c) != 'Mn'))

            w.writerow([item[0],nom,descriptif,item[3],emplacement,item[5],item[6],item[7],item[8],categorie])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    # stream the response as the data is generated
    response = Response(generate(), mimetype='text/csv')
    # ajouter nom de fichier
    response.headers.set("Content-Disposition", "attachment", filename="CondoFix_Export_Equipements.csv")
    return response
