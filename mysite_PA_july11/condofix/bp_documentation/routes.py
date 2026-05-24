import sys

from flask import Blueprint, render_template,g,session,request,redirect,url_for,flash,send_file
import mysql.connector
import os
import inspect
from pathlib import Path
from werkzeug.utils import secure_filename
import traceback
import shutil
from datetime import datetime
from utils import connect_db,chemin_rep

bp_documentation = Blueprint('bp_documentation', __name__)

#affichage de la table de documentation pour admin
# affichage de la table de documentation pour admin
@bp_documentation.route('/docs_table', methods=['POST', 'GET'])
def docs_table():
    """Afficher la page de la table d'enregistrements avec fonction ajout et modif réservée aux admin."""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # vérifier type d'usager (Admin syst.-1, admin syndicat - 4 et gestionnaire - 2 seulement)
    if profile_list[2] == 3:
        return redirect(url_for('bp_admin.permission'))

    fill_documents = []
    client_ident = profile_list[0]

    mode = profile_list[8]
    cnx = connect_db(mode)
    nom_client = profile_list[7]
    path_folder = chemin_rep(mode) + 'documentation/' + nom_client + '_docs'

    # Capacité maximale du répertoire de documentation
    storage_limit_bytes = 2_000_000_000  # 2 Go, cohérent avec l'ancienne jauge "2GB max."
    total_size = 0
    storage_file_count = 0
    storage_folder_exists = os.path.isdir(path_folder)

    if storage_folder_exists:
        for root, dirs, files in os.walk(path_folder):
            for file_name in files:
                itempath = os.path.join(root, file_name)
                if os.path.isfile(itempath):
                    try:
                        total_size += os.path.getsize(itempath)
                        storage_file_count += 1
                    except OSError:
                        # Si un fichier est temporairement inaccessible, on l'ignore pour ne pas bloquer la page.
                        pass

    def format_storage_size(size_bytes):
        if size_bytes <= 0:
            return "0 Mo"
        if size_bytes >= 1_000_000_000:
            return f"{size_bytes / 1_000_000_000:.2f} Go"
        if size_bytes >= 1_000_000:
            return f"{size_bytes / 1_000_000:.1f} Mo"
        if size_bytes >= 1_000:
            return f"{size_bytes / 1_000:.1f} Ko"
        return f"{size_bytes} o"

    storage_used_pct = round((total_size / storage_limit_bytes) * 100, 1) if storage_limit_bytes else 0
    storage_used_pct_capped = min(storage_used_pct, 100)
    storage_available_bytes = max(storage_limit_bytes - total_size, 0)

    if storage_used_pct >= 90:
        storage_status_level = "danger"
        storage_status_label = "Limite bientôt atteinte"
    elif storage_used_pct >= 70:
        storage_status_level = "warning"
        storage_status_label = "Surveillance recommandée"
    else:
        storage_status_level = "healthy"
        storage_status_label = "Capacité saine"

    # Ancienne variable conservée au cas où une autre partie du template y ferait encore référence.
    jauge_val = total_size / storage_limit_bytes if storage_limit_bytes else 0

    cur = cnx.cursor()

    # mettre profil d'immeuble sous forme de liste pour vérifier rapports obligatoires
    liste_profil = []
    cur.execute(
        "SELECT LieuSauvegardeNumeric, NbreEtages, NbreAscenseurs, StationnementUnEtage, StationnementMultiEtages, "
        "Gicleurs, SystLavageVitres, Generatrice FROM parametres WHERE IDClient=%s",
        (client_ident,)
    )
    for item in cur.fetchall():
        liste_profil.append(item)

    cur.execute(
        "SELECT IDDoc, IDTypeDoc, Description, FrequenceAns, Fournisseur, Montant$HT, DateProchain "
        "FROM documentation WHERE IDClient=%s",
        (client_ident,)
    )
    for row in cur.fetchall():
        cur.execute("SELECT Description FROM typesdocs WHERE IDTypeDoc=%s", (row[1],))
        for item_1 in cur.fetchall():
            typedoc = item_1[0]
            row += (typedoc,)
        fill_documents.append(row)

    cnx.close()

    return render_template(
        'documentation_table.html',
        fill_documents=fill_documents,
        jauge_val=jauge_val,
        storage_used_label=format_storage_size(total_size),
        storage_limit_label=format_storage_size(storage_limit_bytes),
        storage_available_label=format_storage_size(storage_available_bytes),
        storage_used_pct=storage_used_pct,
        storage_used_pct_capped=storage_used_pct_capped,
        storage_status_level=storage_status_level,
        storage_status_label=storage_status_label,
        storage_file_count=storage_file_count,
        storage_folder_exists=storage_folder_exists,
        bd=profile_list[3]
    )


#affichage de la table de documentation pour proprios
# affichage de la table de documentation pour proprios
@bp_documentation.route('/docs_table_proprios', methods=['POST', 'GET'])
def docs_table_proprios():
    """Afficher la table de documentation en consultation seulement pour copropriétaires."""

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    mode = profile_list[8]

    fill_documents = []
    cnx = connect_db(mode)

    try:
        cur = cnx.cursor()
        cur.execute(
            """
            SELECT
                d.IDDoc,
                d.IDTypeDoc,
                d.Description,
                d.FrequenceAns,
                d.Fournisseur,
                d.Montant$HT,
                d.DateProchain,
                td.Description AS TypeDescription
            FROM documentation d
            LEFT JOIN typesdocs td
                ON td.IDTypeDoc = d.IDTypeDoc
            WHERE d.IDClient = %s
            ORDER BY d.Description
            """,
            (client_ident,)
        )

        fill_documents = cur.fetchall()

    finally:
        cnx.close()

    return render_template(
        'documentation_proprios.html',
        fill_documents=fill_documents,
        bd=profile_list[3]
    )
# @bp_documentation.route('/docs_table_proprios', methods=['POST','GET'])
# def docs_table_proprios():
#     """afficher la page de la table d'enregistrements SANS fonction ajout et modif pour copropriétaires
# """
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     fill_documents=[]
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#
#     cur = cnx.cursor()
#     cur.execute("SELECT IDDoc,IDTypeDoc,Description,Fournisseur,Montant$HT FROM documentation WHERE IDClient=%s",(client_ident,))
#     for row in cur.fetchall():
#         cur.execute("SELECT Description FROM typesdocs WHERE IDTypeDoc=%s", (row[1],))
#         for item_1 in cur.fetchall():
#             typedoc=item_1[0]
#             row+=(typedoc,)
#         fill_documents.append(row)
#     cnx.close()
#     return render_template('documentation_proprios.html',fill_documents=fill_documents,bd=profile_list[3])

@bp_documentation.route('/doc_enreg/<parametre>")', methods=['POST','GET'])
def doc_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)

    cur = cnx.cursor()
    liste_types_docs=[]
    cur.execute("SELECT IDTypeDoc,Description FROM typesdocs")
    for row in cur.fetchall():
        if row[0]!=1: #on ne permet pas de modifier le type des documents de type 'rapport obligatoire'
            liste_types_docs.append(row)
    #tri par ordre alpha
    liste_types_docs.sort(key = lambda x: x[1], reverse=False)

    if parametre=='0':
        cnx.close()
        return render_template('doc_ajout.html', liste_types_docs=liste_types_docs,bd=profile_list[3])
    else:
        liste_document=[]
        cur.execute("SELECT IDDoc,IDTypeDoc,Description, CheminPath, FrequenceAns,Fournisseur,Montant$HT,DateProchain FROM documentation WHERE IDDoc=%s AND IDClient=%s",(parametre,client_ident))
        for row in cur.fetchall():
            # si rapport obligatoire (IDTypeDoc=1), la liste des types contient seulement ce type de rapport
            if row[1]==1:
                liste_types_docs=[(1,'Rapport obligatoire')]
            # conserver seulement dernière partie du chemin
            if row[3]==None or row[3]=='':
                titre_fichier=''
            else:
                titre_fichier=os.path.basename(os.path.normpath(row[3]))
            row+=(titre_fichier,)
            liste_document.append(row)
        cnx.close()
        return render_template('doc_modif.html', liste_document=liste_document,liste_types_docs=liste_types_docs,bd=profile_list[3])

@bp_documentation.route("/doc_ajout", methods=['POST','GET'])
def doc_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements

    |* Vérifier format du doc (doit être .pdf)
    * Vérifier si répertoire de documents du client dépasse 1GB
    * Vérifier si champs obligatoires sont remplis et éviter de sauvegarder '' dans rubrique 'INT'
           """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    nom_client = profile_list[7]
    folder = chemin_rep(mode)+'documentation/'+nom_client+'_docs'

    cur = cnx.cursor()
    doc=request.files['fichier']
    titre=doc.filename
    # s'assurer que le titre est sécuritaire (ex: remplace espaces par '_')
    nom_fichier = secure_filename(titre)

    # vérifier extension permise (.pdf seulement)
    ext_permis=["pdf"]
    if not "." in titre:
        return "format incorrect: manque un point avant 'pdf'"
    ext = titre.rsplit(".", 1)[1]
    if ext in ext_permis:
        # vérifier si répertoire des docs excède 2GB
        #folder= chemin_rep(mode, nom_client)

        total_size = os.path.getsize(folder)
        for item in os.listdir(folder):
            itempath = os.path.join(folder, item)
            if os.path.isfile(itempath):
                total_size += os.path.getsize(itempath)
        if total_size>2000000000:
            flash('Vous avez excédé la capacité du répertoire (2Gb). Veuillez communiquer avec CondoFix pour augmenter la capacité.')
            return redirect(url_for('bp_documentation.docs_table'))
        else:
            #ajout du chemin du fichier recherché
            chemin_db = 'documentation/'+nom_client+'_docs/'+ nom_fichier

            #sauvegarder doc dans répertoire 'documentation'
            doc.save(chemin_rep(mode)+chemin_db)
            type_doc=int(request.form['type_doc'])

            # vérifier si champs obligatoires sont remplis et éviter de sauvegarder '' dans rubrique 'INT'
            if request.form['freq']=='':
                if 0<type_doc<5:
                    flash("Le champ 'fréquence' doit avoir une valeur",'warning')
                    return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
                freq=None
            else: freq=request.form['freq']
            if request.form['fournisseur']=='':
                # pour rapports et contrats seulement
                if 0<type_doc<5:
                    flash("Le champ 'fournisseur' doit avoir une valeur",'warning')
                    return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
                fournisseur=None
            else: fournisseur=request.form['fournisseur']
            if request.form['montant_HT']=='':
                # pour contrats seulement
                if 2<type_doc<5:
                    flash("Le champ 'montant $HT' doit avoir une valeur",'warning')
                    return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
                montant=None
            else: montant=request.form['montant_HT']
            if request.form['date_proch']=='':
                # pour rapports obligatoires
                if 0<type_doc<2:
                    flash("Le champ 'date prochain' doit avoir une valeur",'warning')
                    return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
                date=None
            else: date=request.form['date_proch']
            IDUsager=profile_list[1]
            if int(request.form['type_doc'])<5: # pour rapports et contrats, on sauvegarde tous les champs
                cur.execute('INSERT INTO documentation (IDClient,IDUsager,IDTypeDoc,Description,CheminPath,FrequenceAns,Fournisseur,Montant$HT,DateProchain) '
                           'values (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
                           [client_ident, IDUsager, request.form['type_doc'], request.form['desc_doc'], chemin_db, freq, fournisseur,
                            montant, date])
            else:
                cur.execute('INSERT INTO documentation (IDClient,IDUsager,IDTypeDoc,Description,CheminPath) '
                            'values (%s, %s, %s, %s, %s)',
                            [client_ident, IDUsager, request.form['type_doc'], request.form['desc_doc'], chemin_db])

            cnx.commit()
            cnx.close()
            return redirect(url_for('bp_documentation.docs_table'))

    else:
        flash("Format de fichier .pdf permis seulement.'",'warning')
        return redirect(url_for('bp_documentation.doc_enreg',parametre=0))

@bp_documentation.route('/doc_modif/<id_doc>', methods=['POST','GET'])
def doc_modif(id_doc):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements

    |* Vérifier format du doc (doit être .pdf)
    * Vérifier si répertoire de documents du client dépasse 1GB
    * Vérifier si champs obligatoires sont remplis et éviter de sauvegarder '' dans rubrique 'INT'
     """

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    nom_client = profile_list[7]
    folder = chemin_rep(mode)+'documentation/'+nom_client+'_docs'

    cur = cnx.cursor()
    doc=request.files['fichier_choisi']
    titre=doc.filename
    # s'assurer que le titre est sécuritaire
    nom_fichier = secure_filename(titre)
    ch_path_direct = 'documentation/' + nom_client + '_docs/'+nom_fichier
    try:
        type_doc=int()
        chemin_db=str()
        if titre!='':   #l'usager a sélectionné un fichier à télécharger
            # vérifier extension permise (.pdf seulement)
            ext_permis=["pdf"]
            if not "." in titre:
                flash("Format de fichier incorrect: il manque un point avant 'pdf'",'warning')
                return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))
            ext = titre.rsplit(".", 1)[1]
            if ext in ext_permis:
                # vérifier si répertoire des docs excède 1GB
                total_size = os.path.getsize(folder)
                for item in os.listdir(folder):
                    itempath = os.path.join(folder, item)
                    if os.path.isfile(itempath):
                        total_size += os.path.getsize(itempath)
                if total_size>2000000000:
                    flash('Vous avez excédé la capacité du répertoire (2Gb).')
                    return redirect(url_for('bp_documentation.docs_table'))
                else:
                    #ajout du chemin du fichier recherché
                    chemin_db=folder+'/'+nom_fichier

                    # supprimer le fichier précédent associé à ce document
                    if request.form['doc_titre']!='':
                        chemin_ex_doc=folder+'/'+request.form['doc_titre']
                        if os.path.exists(chemin_ex_doc):
                            os.remove(chemin_ex_doc)

                    #sauvegarder doc dans répertoire 'documentation'
                    doc.save(chemin_db)
                    type_doc=int(request.form['type_doc'])
            else:
                flash("Format de fichier .pdf permis seulement.'",'warning')
                return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))

        # vérifier si champs obligatoires sont remplis et éviter de sauvegarder '' dans rubrique 'INT'
        if request.form['freq']=='':
            if 0<type_doc<5:
                flash("Le champ 'fréquence' doit avoir une valeur",'warning')
                return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))
            freq=None
        else: freq=request.form['freq']

        if request.form['fournisseur']=='':
            # pour rapports et contrats seulement
            if 0<type_doc<5:
                flash("Le champ 'fournisseur' doit avoir une valeur",'warning')
                return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))
            fournisseur=None
        else: fournisseur=request.form['fournisseur']

        if request.form['montant_HT']=='':
            # pour contrats seulement
            if 2<type_doc<5:
                flash("Le champ 'montant $HT' doit avoir une valeur",'warning')
                return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))
            montant=None
        else: montant=request.form['montant_HT']

        if request.form['date_proch']=='':
            # pour rapports obligatoires
            if 0<type_doc<2:
                flash("Le champ 'date prochain' doit avoir une valeur",'warning')
                return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))
            date=None
        else: date=request.form['date_proch']

        if int(request.form['type_doc'])<5: # pour rapports et contrats, on sauvegarde tous les champs
            #mise à jour de l'enregistrement avec ou sans modif du chemin du fichier
            if titre !='':
                cur.execute("UPDATE documentation SET IDTypeDoc=%s,Description=%s,CheminPath=%s,FrequenceAns=%s,Fournisseur=%s,Montant$HT=%s,DateProchain=%s "
                                "WHERE IDDoc= %s AND IDClient=%s",[request.form['type_doc'],request.form['desc_doc'],ch_path_direct, freq, fournisseur,
                            montant, date,int(id_doc),client_ident])
            else: # CheminPath non modifié
                cur.execute("UPDATE documentation SET IDTypeDoc=%s,Description=%s,FrequenceAns=%s,Fournisseur=%s,Montant$HT=%s,DateProchain=%s"
                            "WHERE IDDoc= %s AND IDClient=%s",[request.form['type_doc'],request.form['desc_doc'], freq, fournisseur, montant, date,id_doc,client_ident])
        else:
            if titre !='':
                cur.execute("UPDATE documentation SET IDTypeDoc=%s,Description=%s,CheminPath=%s"
                            "WHERE IDDoc= %s AND IDClient=%s",[request.form['type_doc'],request.form['desc_doc'],ch_path_direct,id_doc,client_ident])
            else: # CheminPath non modifié
                cur.execute("UPDATE documentation SET IDTypeDoc=%s,Description=%s"
                    "WHERE IDDoc= %s AND IDClient=%s",[request.form['type_doc'],request.form['desc_doc'],id_doc,client_ident])

        cnx.commit()
        cnx.close()
        return redirect(url_for('bp_documentation.docs_table'))
    except:
        print(traceback.format_exc())
        return redirect(url_for('bp_documentation.docs_table'))


@bp_documentation.route('/doc_affiche_admin/<int:id_doc>', methods=['GET'])
def doc_affiche_admin(id_doc):
    """Afficher le document PDF dans le navigateur."""
    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    mode = profile_list[8]

    cnx = connect_db(mode)

    try:
        cur = cnx.cursor()
        cur.execute(
            "SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",
            (id_doc, client_ident)
        )
        row = cur.fetchone()
    finally:
        cnx.close()

    if not row or not row[0]:
        return redirect(url_for('bp_documentation.docs_table'))

    stored_path = row[0]
    base_folder = chemin_rep(mode)

    if os.path.isabs(stored_path):
        chemin_doc = stored_path
    else:
        chemin_doc = os.path.normpath(os.path.join(base_folder, stored_path))

    if not os.path.isfile(chemin_doc):
        print("Document introuvable:", chemin_doc)
        return redirect(url_for('bp_documentation.docs_table'))

    titre = os.path.basename(chemin_doc)

    send_file_params = inspect.signature(send_file).parameters

    if 'download_name' in send_file_params:
        return send_file(
            chemin_doc,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=titre,
            max_age=0
        )

    return send_file(
        chemin_doc,
        mimetype='application/pdf',
        as_attachment=False,
        attachment_filename=titre,
        cache_timeout=0
    )
# @bp_documentation.route('/doc_affiche_admin/<id_doc>")', methods=['POST','GET'])
# def doc_affiche_admin(id_doc):
#     """afficher le document pdf"""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     nom_client = profile_list[7]
#     folder = chemin_rep(mode)
#
#     cur = cnx.cursor()
#     chemin_doc=str()
#     cur.execute("SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_doc,client_ident))
#     titre=str()
#     for item in cur.fetchall():
#         # #trouver répertoire de base
#         # base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#         # #enlever le mot 'condofix' pour se retrouver au niveau de 'mysite'
#         # modified_dir=base_dir.replace('condofix', '')
#         #ajout du chemin du fichier recherché
#         if item[0]==None or item[0]=='':
#             return redirect(url_for('bp_documentation.docs_table'))
#         chemin_doc=folder+item[0]
#         #pour obtenir le titre du doc seulement
#         titre=item[0].split("docs/",1)[1]
#         print('titre affiche:',titre)
#         cnx.close()
#     return send_file(chemin_doc,attachment_filename=titre,cache_timeout=0)


# @bp_documentation.route('/doc_affiche_proprios/<id_doc>")', methods=['POST','GET'])
# def doc_affiche_proprios(id_doc):
#     """Afficher le document pdf sélectionné dans la table des copropriétaires"""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     mode = profile_list[8]
#     cnx = connect_db(mode)
#     cur = cnx.cursor()
#     chemin_doc=str()
#     titre=str()
#     cur.execute("SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_doc,client_ident))
#     for item in cur.fetchall():
#         if item[0]==None:
#             return redirect(url_for('bp_documentation.docs_table_proprios'))
#
#         chemin_doc=chemin_rep(mode)+item[0]
#         #pour obtenir le titre du doc seulement
#         titre=item[0].split("docs/",1)[1]
#         print('titre:',titre)
#         cnx.close()
#     return send_file(chemin_doc,attachment_filename=titre)

@bp_documentation.route('/doc_affiche_proprios/<int:id_doc>', methods=['GET'])
def doc_affiche_proprios(id_doc):
    """Afficher le document PDF sélectionné dans la table des copropriétaires."""

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')
    client_ident = profile_list[0]
    mode = profile_list[8]

    cnx = connect_db(mode)

    try:
        cur = cnx.cursor()
        cur.execute(
            "SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",
            (id_doc, client_ident)
        )
        row = cur.fetchone()

    finally:
        cnx.close()

    if not row or not row[0]:
        return redirect(url_for('bp_documentation.docs_table_proprios'))

    stored_path = row[0]
    base_folder = chemin_rep(mode)

    if os.path.isabs(stored_path):
        chemin_doc = stored_path
    else:
        chemin_doc = os.path.normpath(os.path.join(base_folder, stored_path))

    if not os.path.isfile(chemin_doc):
        print("Document introuvable:", chemin_doc)
        return redirect(url_for('bp_documentation.docs_table_proprios'))

    titre = os.path.basename(chemin_doc)
    send_file_params = inspect.signature(send_file).parameters

    if 'download_name' in send_file_params:
        return send_file(
            chemin_doc,
            mimetype='application/pdf',
            as_attachment=False,
            download_name=titre,
            max_age=0
        )

    return send_file(
        chemin_doc,
        mimetype='application/pdf',
        as_attachment=False,
        attachment_filename=titre,
        cache_timeout=0
    )

@bp_documentation.route('/chemin_doc_supprime/<id_doc>', methods=['POST','GET'])
def chemin_doc_supprime(id_doc):
    """Supprimer le chemin du document sélectionné par l'admin dans la table"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("UPDATE documentation SET CheminPath=%s"
                "WHERE IDDoc= %s AND IDClient=%s",('',id_doc,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_documentation.doc_enreg',parametre=id_doc))


@bp_documentation.route('/doc_delete/<id_doc>")', methods=['POST','GET'])
def doc_delete(id_doc):
    """Supprimer le document sélectionné par l'admin dans la table.
    * pour éviter de supprimer un rapport obligatoire déjà mis dans la table par le programmeur"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list = session.get('ProfilUsager')
    # vérifier type d'usager (Admin syst.-1, admin syndicat - 4 et gestionnaire - 2 seulement)
    # le membre du ca, l'employé et le coproprio ne peut supprimer
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident = profile_list[0]
    doc_type=int()
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("SELECT IDTypeDoc FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_doc,client_ident))
    for item in cur.fetchall():
        doc_type=item[0]
    if doc_type==1:
        return render_template('document_no_delete.html')
    else:
        ch_doc=str()
        cur.execute("SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_doc,client_ident))
        for item in cur.fetchall():
            ch_doc=item[0]
        cur.execute("DELETE FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_doc,client_ident))
        cnx.commit()
        cnx.close()
        #supprimer le document du répertoire
        ch_doc_delete=chemin_rep(mode)+ch_doc
        if os.path.exists(ch_doc_delete):
            os.remove(ch_doc_delete)
        else:
            print("The file does not exist")
        return redirect(url_for('bp_documentation.docs_table'))

# #affichage de la table de plans et schémas pour admin
# @bp_documentation.route('/plans_table', methods=['POST','GET'])
# def plans_table():
#     """afficher la page de la table des plans et schémas avec fonction ajout réservée aux admin
# """
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     # vérifier type d'usager (Admin syst.-1, admin syndicat - 4 et gestionnaire - 2 seulement)
#     if profile_list[2]==3:
#         #print('profil après if:',profile_list[2])
#         return redirect(url_for('bp_admin.permission'))
#     fill_plans=[]
#     client_ident=profile_list[0]
#     # obtenir taille du répertoire de documentation  pour ce client
#     # pour serveur PA:
#     # path_folder=str('/home/CondoFix/mysite/documentation/'+profile_list[4]+'_docs')
#     # pour localhost:
#
#     path_folder=str('../documentation/'+profile_list[7]+'_docs'+'/plans')
#
#     total_size = os.path.getsize(path_folder)
#     for item in os.listdir(path_folder):
#         itempath = os.path.join(path_folder, item)
#         if os.path.isfile(itempath):
#             total_size += os.path.getsize(itempath)
#     jauge_val=total_size/1000000000
#     cnx = connect_db()
#     cur = cnx.cursor()
#     # lecture de la table de bd
#     cur.execute("SELECT IDPlans, IDCategorie, Description FROM plans WHERE IDClient=%s",(client_ident,))
#     for row in cur.fetchall():
#         cur.execute("SELECT Description FROM categories WHERE IDCategories=%s AND IDClient=%s", (row[1],client_ident))
#         for item_1 in cur.fetchone():
#             desc_categ=item_1[0]
#             row+=(desc_categ,)
#         fill_plans.append(row)
#     cnx.close()
#     return render_template('plans_table.html',fill_plans=fill_plans,jauge_val=jauge_val,bd=profile_list[3])
#
#
# @bp_documentation.route('/plan_enreg")', methods=['POST','GET'])
# def plan_enreg():
#     """Afficher la page d'ajout dans la bd mysql"""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     # vérifier type d'usager si bp_admin ou non
#     if profile_list[2] > 2:
#         return redirect(url_for('bp_admin.permission'))
#     client_ident=profile_list[0]
#     cnx = connect_db()
#     cur = cnx.cursor()
#     liste_categories=[]
#     cur.execute("SELECT IDCategorie,Description FROM categories WHERE IDClient=%s",(client_ident,))
#     for row in cur.fetchall():
#         liste_categories.append(row)
#     #tri par ordre alpha
#     liste_categories.sort(key = lambda x: x[1], reverse=False)
#     cnx.close()
#     return render_template('plans_ajout.html', liste_categories=liste_categories,bd=profile_list[3])

# #fonctions pour ajouter ou modifier un équipement
# @bp_documentation.route("/plan_ajout", methods=['POST','GET'])
# def plan_ajout():
#     """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements
#
#     |* Vérifier format du doc (doit être .pdf)
#     * Vérifier si répertoire de plans du client dépasse 1GB
#     * Vérifier si champs obligatoires sont remplis et éviter de sauvegarder '' dans rubrique 'INT'
#            """
#
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     cnx = connect_db()
#     cur = cnx.cursor()
#     plan=request.files['fichier']
#     titre=plan.filename
#     # vérifier extension permise (.pdf seulement)
#     ext_permis=["pdf"]
#     if not "." in titre:
#         return "format incorrect: manque un point avant 'pdf'"
#     ext = titre.rsplit(".", 1)[1]
#     if ext in ext_permis:
#         # vérifier si répertoire des plans excède 1GB
#         #folder=str('/home/CondoFix/mysite/documentation/'+profile_list[4]+'_docs'+'/plans')
#         # pour local:
#         folder=str('C:/Users/Donal/Documents/Projets Programmation/mysite_PA_july11/documentation/'+profile_list[7]+'_docs'+'/plans')
#
#         total_size = os.path.getsize(folder)
#         for item in os.listdir(folder):
#             itempath = os.path.join(folder, item)
#             if os.path.isfile(itempath):
#                 total_size += os.path.getsize(itempath)
#         if total_size>1000000000:
#             flash('Vous avez excédé la capacité du répertoire (1Gb). Vous devrez supprimer des documents pour y accéder.')
#             return redirect(url_for('bp_documentation.plans_table'))
#         else:
#             # titrer le plan avec date et heure
#             #source_path = chemin_fichier
#             nom_fichier_brut = datetime.today().strftime(
#                 '%Y-%m-%d') + 'Plan' + datetime.today().strftime('%H:%M:%S') + '.pdf'
#             nom_fichier = nom_fichier_brut.replace(':', '')
#             dest_path = os.path.join(chemin_rep('facture'), nom_fichier)
#     #         shutil.move(source_path, dest_path)
#     #         chemin_db = 'documentation/' + profile_list[7] + '_docs/Factures/' + nom_fichier
#     #         chemin_fichier = os.path.join(chemin_ocr, 'temp_image_' + profile_list[7] + '.pdf')
#     #         file_stats = os.stat(chemin_fichier)
#     #         taille_pdf = file_stats.st_size
#     #         # print('taille pdf:',taille_pdf)
#     #         if taille_pdf > 400000:
#     #             flash('Fichier pdf trop grand pour être sauvegardé (maximum de 400K permis).', 'warning')
#     #         else:
#     #
#     #         nom_fichier = secure_filename(titre)
#     #         #trouver répertoire de base
#     #         base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#     #         #enlever le mot 'condofix' pour se retrouver au niveau de 'mysite'
#     #         modified_dir=base_dir.replace('condofix', '')
#     #         #ajout du chemin du fichier recherché
#     #         chemin_db='documentation'+'/'+profile_list[4]+'_docs'+'/'+nom_fichier
#     #         chemin_rep=modified_dir+chemin_db
#     #
#     #         #sauvegarder doc dans répertoire 'documentation'
#     #         doc.save(chemin_rep)
#     #         type_doc=int(request.form['type_doc'])
#     #
#     #         # vérifier si champs obligatoires sont remplis et éviter de sauvegarder '' dans rubrique 'INT'
#     #         if request.form['freq']=='':
#     #             if 0<type_doc<5:
#     #                 flash("Le champ 'fréquence' doit avoir une valeur",'warning')
#     #                 return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
#     #             freq=None
#     #         else: freq=request.form['freq']
#     #         if request.form['fournisseur']=='':
#     #             # pour rapports et contrats seulement
#     #             if 0<type_doc<5:
#     #                 flash("Le champ 'fournisseur' doit avoir une valeur",'warning')
#     #                 return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
#     #             fournisseur=None
#     #         else: fournisseur=request.form['fournisseur']
#     #         if request.form['montant_HT']=='':
#     #             # pour contrats seulement
#     #             if 2<type_doc<5:
#     #                 flash("Le champ 'montant $HT' doit avoir une valeur",'warning')
#     #                 return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
#     #             montant=None
#     #         else: montant=request.form['montant_HT']
#     #         if request.form['date_proch']=='':
#     #             # pour rapports obligatoires
#     #             if 0<type_doc<2:
#     #                 flash("Le champ 'date prochain' doit avoir une valeur",'warning')
#     #                 return redirect(url_for('bp_documentation.doc_enreg',parametre=0))
#     #             date=None
#     #         else: date=request.form['date_proch']
#     #         IDUsager=profile_list[1]
#     #         if int(request.form['type_doc'])<5: # pour rapports et contrats, on sauvegarde tous les champs
#     #             cur.execute('INSERT INTO documentation (IDClient,IDUsager,IDTypeDoc,Description,CheminPath,FrequenceAns,Fournisseur,Montant$HT,DateProchain) '
#     #                        'values (%s, %s, %s, %s, %s, %s, %s, %s, %s)',
#     #                        [client_ident, IDUsager, request.form['type_doc'], request.form['desc_doc'], chemin_db, freq, fournisseur,
#     #                         montant, date])
#     #         else:
#     #             cur.execute('INSERT INTO documentation (IDClient,IDUsager,IDTypeDoc,Description,CheminPath) '
#     #                         'values (%s, %s, %s, %s, %s)',
#     #                         [client_ident, IDUsager, request.form['type_doc'], request.form['desc_doc'], chemin_db])
#     #
#     #         cnx.commit()
#     #         cnx.close()
#     #         return redirect(url_for('bp_documentation.plans_table'))
#     #
#     # else:
#     #     flash("Format de fichier .pdf permis seulement.'",'warning')
#         return redirect(url_for('bp_documentation.plan_enreg'))
#
# @bp_documentation.route('/plan_affiche/<id_plan>")', methods=['POST','GET'])
# def plan_affiche(id_plan):
#     """Afficher le document pdf sélectionné dans la table des copropriétaires"""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list=session.get('ProfilUsager')
#     client_ident=profile_list[0]
#     cnx = connect_db()
#     cur = cnx.cursor()
#     chemin_doc=str()
#     titre=str()
#     cur.execute("SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_plan,client_ident))
#     for item in cur.fetchall():
#         #trouver répertoire de base
#         base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#         #enlever le mot 'condofix' pour se retrouver au niveau de 'mysite'
#         modified_dir=base_dir.replace('condofix', '')
#         #ajout du chemin du fichier recherché
#         if item[0]==None:
#             return redirect(url_for('bp_documentation.docs_table_proprios'))
#         chemin_doc=modified_dir+item[0]
#         #pour obtenir le titre du doc seulement
#         titre=item[0].split("docs/",1)[1]
#         cnx.close()
#     return send_file(chemin_doc,attachment_filename=titre)
#
# @bp_documentation.route('/plan_delete/<id_plan>")', methods=['POST','GET'])
# def plan_delete(id_plan):
#     """Supprimer le document sélectionné par l'admin dans la table.
#     * pour éviter de supprimer un rapport obligatoire déjà mis dans la table par le programmeur"""
#     if session.get('ProfilUsager') is None:
#         # probablement délai de session atteint
#         return render_template('session_ferme.html')
#     profile_list = session.get('ProfilUsager')
#     # vérifier type d'usager (Admin syst.-1, admin syndicat - 4 et gestionnaire - 2 seulement)
#     # le membre du ca, l'employé et le coproprio ne peut supprimer
#     if profile_list[2] > 2:
#         return redirect(url_for('bp_admin.permission'))
#     client_ident = profile_list[0]
#     doc_type=int()
#     cnx = connect_db()
#     cur = cnx.cursor()
#     cur.execute("SELECT IDTypeDoc FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_plan,client_ident))
#     for item in cur.fetchall():
#         doc_type=item[0]
#     if doc_type==1:
#         return render_template('document_no_delete.html')
#     else:
#         ch_doc=str()
#         cur.execute("SELECT CheminPath FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_plan,client_ident))
#         for item in cur.fetchall():
#             ch_doc=item[0]
#         cur.execute("DELETE FROM documentation WHERE IDDoc=%s AND IDClient=%s",(id_plan,client_ident))
#         cnx.commit()
#         cnx.close()
#         #supprimer le document du répertoire
#         #trouver répertoire de base
#         base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#         #enlever le mot 'condofix' pour se retrouver au niveau de 'mysite'
#         modified_dir=base_dir.replace('condofix', '')
#         ch_doc_delete=modified_dir+ch_doc
#         if os.path.exists(ch_doc_delete):
#             os.remove(ch_doc_delete)
#         else:
#             print("The file does not exist")
#         return redirect(url_for('bp_documentation.docs_table'))
