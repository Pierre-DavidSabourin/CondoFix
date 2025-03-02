from flask import Blueprint, render_template,g,session,url_for,redirect,request
import mysql.connector
from io import StringIO
import unicodedata
import csv
from werkzeug.wrappers import Response
from mysite_PA_july11.utils import connect_db

bp_intervenants = Blueprint('bp_intervenants', __name__)

#********************INTERVENANTS****************************************
#page de la liste d'bp_intervenants avec fonction ajout
@bp_intervenants.route("/intervenants")
def intervenants():
    """afficher la page de la table d'enregistrements avec fonction ajout et modif
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    fill_intervenants=[]
    client_ident=profile_list[0]
    version_client = profile_list[6]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    cur.execute("SELECT IDIntervenant, NomIntervenant, IDTypeIntervenant, Contact1, Telephone1, Contact2, Telephone2, Courriel, "
                "Adresse, TelPrincipal, IDCategorie, Actif "
                "from intervenants WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        if row[11]==1:
            actif='oui'
        else:
            actif='non'
        row+=(actif,)
        cur.execute("SELECT Description FROM typeintervenant WHERE IDTypeIntervenant=%s", (row[2],))
        for item in cur.fetchall():
            IntervenantType=item
            row+=(IntervenantType)
        cur.execute("SELECT Description FROM categories WHERE IDCategorie=%s", (row[10],))
        for item in cur.fetchall():
            IntervenantType = item
            row += (IntervenantType)
        fill_intervenants.append(row)
    return render_template('intervenants_table.html', version=version_client, fill_intervenants=fill_intervenants,bd=profile_list[3])

#page enregistrement intervenant (nouveau ou modifier)
@bp_intervenants.route('/intervenant_enreg/<parametre>')
def intervenant_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    version_client = profile_list[6]
    # vérifier type d'usager si autre que 'admin'
    if profile_list[2] >2:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]
    # si nouveau parametre =0, si modif parametre=liste de valeurs de l'enregistrement (item de fill_intervenants)
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    liste_categories = []
    cur.execute("SELECT IDCategorie, Description FROM categories WHERE Actif=1 AND IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        liste_categories.append(row)
    liste_categories.sort(key=lambda tup: tup[1])
    if parametre=='0':
        return render_template('intervenant_ajout.html', liste_categories=liste_categories, version=version_client, bd=profile_list[3])
    else:
        liste_intervenant=[]
        cur.execute("SELECT IDIntervenant, NomIntervenant, IDTypeIntervenant, Courriel, Contact1, Telephone1, Contact2, Telephone2, "
                    "Adresse, TelPrincipal, IDCategorie, Actif "
                    "from intervenants WHERE IDIntervenant=%s AND IDClient=%s",(parametre,client_ident))
        for row in cur.fetchall():
            liste_intervenant.append(row)
        cnx.close()
        print(liste_categories)
        return render_template('intervenant_modif.html', version=version_client, liste_intervenant= liste_intervenant, liste_categories=liste_categories, bd=profile_list[3])

#fonctions pour ajouter ou modifier un intervenant
@bp_intervenants.route("/intervenant_ajout", methods=['POST'])
def intervenant_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    nom_interv=request.form['intervenant_nom']
    cur.execute('INSERT INTO intervenants (IDClient, NomIntervenant, IDTypeIntervenant, Courriel, Contact1, Telephone1, Contact2, Telephone2, '
                'Adresse, TelPrincipal, IDCategorie, Actif) '
                 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                 [client_ident, nom_interv, request.form['intervenant_type'], request.form['email'], request.form['contact_1'],
                  request.form['teleph_1'],request.form['contact_2'],request.form['teleph_2'],request.form['adresse'],
                  request.form['tel_principal'],request.form['id_categorie'],1])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_intervenants.intervenants'))

@bp_intervenants.route('/intervenant_modif/<ident_intervenant>', methods=['POST','GET'])
def intervenant_modif(ident_intervenant):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')

    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1
    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    nom_interv = request.form['intervenant_nom']

    cur.execute("UPDATE intervenants SET NomIntervenant= %s,IDTypeIntervenant= %s, Courriel=%s, Contact1= %s, Telephone1= %s, Contact2= %s, "
                "Telephone2= %s, Adresse= %s, TelPrincipal= %s, IDCategorie= %s, Actif= %s WHERE IDIntervenant = %s AND IDClient=%s",
                 ([nom_interv, request.form['intervenant_type'], request.form['email'], request.form['contact_1'], request.form['teleph_1'],
                   request.form['contact_2'], request.form['teleph_2'], request.form['adresse'], request.form['tel_principal'],
                   request.form['id_categorie'],val_actif,ident_intervenant, client_ident]))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_intervenants.intervenants'))

@bp_intervenants.route('/export_interv_csv/', methods=['POST','GET'])
def export_interv_csv():
    """Permettre l'exportation des enregistrements dans un fichier csv à partir d'une date spécifiée."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2] == 3 or profile_list[2] == 5:
        return redirect(url_for('bp_admin.permission'))

    client_ident=profile_list[0]
    mode_connexion = profile_list[8]
    cnx = connect_db(mode_connexion)
    cur = cnx.cursor()
    list_intervenants=[]
    cur.execute("SELECT NomIntervenant,IDTypeIntervenant, Courriel, Contact1, Telephone1, Contact2, Telephone2, Actif "
                "FROM intervenants WHERE IDClient=%s", (client_ident,))
    for row in cur.fetchall():
        cur.execute("SELECT Description from typeintervenant WHERE IDTypeIntervenant=%s",(row[1],))
        for item in cur.fetchall():
            row+=item
        list_intervenants.append(row)
    print('liste intervenants:',list_intervenants)
    cnx.close()
    def generate():
        data = StringIO()
        w = csv.writer(data)
        # création d'entêtes pour le fichier csv
        entetes=['Nom', 'Type', 'Courriel', 'Contact1', 'Telephone1', 'Contact2', 'Telephone2', 'Actif']
        w.writerow(entetes)
        yield data.getvalue()
        data.seek(0)
        data.truncate(0)
        for item in list_intervenants:
            # supprimer les accents
            type=''.join((c for c in unicodedata.normalize('NFD', item[8]) if unicodedata.category(c) != 'Mn'))
            nom=''.join((c for c in unicodedata.normalize('NFD', item[0]) if unicodedata.category(c) != 'Mn'))
            contact_1 = ''.join((c for c in unicodedata.normalize('NFD', item[3]) if unicodedata.category(c) != 'Mn'))
            contact_2 = ''.join((c for c in unicodedata.normalize('NFD', item[5]) if unicodedata.category(c) != 'Mn'))

            w.writerow([ nom, type, item[2], contact_1, item[4], contact_2, item[6], item[7]])
            yield data.getvalue()
            data.seek(0)
            data.truncate(0)

    # stream the response as the data is generated
    response = Response(generate(), mimetype='text/csv')
    # ajouter nom de fichier
    response.headers.set("Content-Disposition", "attachment", filename="CondoFix_Export_Intervenants.csv")
    return response