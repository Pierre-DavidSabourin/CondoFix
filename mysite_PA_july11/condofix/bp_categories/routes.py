from flask import Blueprint, render_template,g,session,url_for,redirect,request
import mysql.connector
from utils import connect_db

bp_categories = Blueprint('bp_categories', __name__)


#***************Gestion des catégories (paramétrables) ******************************
@bp_categories.route("/categories")
def categories():
    """Afficher la page de la table d'enregistrements avec fonction ajout et modif."""

    if session.get('ProfilUsager') is None:
        return render_template('session_ferme.html')

    profile_list = session.get('ProfilUsager')

    # Pas accessible par l'employé ou le proprio
    if profile_list[2] == 3 or profile_list[2] == 5:
        return redirect(url_for('bp_admin.permission'))

    from decimal import Decimal, InvalidOperation

    client_ident = profile_list[0]
    version_client = profile_list[6]
    mode = profile_list[8]

    cnx = connect_db(mode)
    cur = cnx.cursor()

    fill_categories = []
    cum_budget = Decimal('0')
    nb_categories = 0
    nb_actives = 0
    nb_inactives = 0

    cur.execute(
        "SELECT IDCategorie, IDGroupe, Description, BudgetAnnuel, CodeGL, Actif "
        "FROM categories "
        "WHERE IDClient=%s",
        (client_ident,)
    )

    for row in cur.fetchall():
        nb_categories += 1

        # Groupe Uniformat
        groupe_desc = 'Non défini'

        if row[1] is not None:
            cur.execute(
                "SELECT Descriptif "
                "FROM groupesuniformat "
                "WHERE IDGroupe=%s",
                (row[1],)
            )
            groupe = cur.fetchone()

            if groupe is not None:
                groupe_desc = groupe[0]

        # Budget annuel
        budget_value = row[3]

        if budget_value not in (None, '', 'None'):
            try:
                cum_budget += Decimal(str(budget_value))
            except (InvalidOperation, ValueError, TypeError):
                pass

        # Actif
        if row[5] == 1:
            actif = 'oui'
            nb_actives += 1
        else:
            actif = 'non'
            nb_inactives += 1

        row += (groupe_desc, actif)
        fill_categories.append(row)

    date_budget = ''
    cur.execute(
        "SELECT DateDebutBudget "
        "FROM parametres "
        "WHERE IDClient=%s",
        (client_ident,)
    )
    row_date_budget = cur.fetchone()

    if row_date_budget is not None:
        date_budget = row_date_budget[0]

    cnx.close()

    return render_template(
        'categories_table.html',
        version=version_client,
        fill_categories=fill_categories,
        date_budget=date_budget,
        cum_budget=float(cum_budget),
        nb_categories=nb_categories,
        nb_actives=nb_actives,
        nb_inactives=nb_inactives,
        bd=profile_list[3]
    )

@bp_categories.route('/categorie_enreg/<parametre>')
def categorie_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2]>2:
        return redirect(url_for('bp_admin.permission'))
    # si nouveau parametre =0, si modif parametre=liste de valeurs de l'enregistrement (item de fill_intervenants)
    client_ident=profile_list[0]
    version_client = profile_list[6]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    liste_groupes=[]
    cur.execute("SELECT IDGroupe,Descriptif FROM groupesuniformat")
    for item in cur.fetchall():
        liste_groupes.append(item)

    if parametre=='0':
        cnx.close()
        return render_template('categorie_ajout.html', version=version_client, liste_groupes=liste_groupes,bd=profile_list[3])
    else:
        liste_categorie=[]
        cur.execute("SELECT IDCategorie, IDGroupe, Description, BudgetAnnuel, CodeGL, Actif FROM categories WHERE IDCategorie=%s AND IDClient=%s",(parametre,client_ident,))
        for row in cur.fetchall():
            liste_categorie.append(row)
            cnx.close()
        return render_template('categorie_modif.html', version=version_client, liste_categorie=liste_categorie, liste_groupes=liste_groupes, bd=profile_list[3])

#fonctions pour ajouter ou modifier une catégorie
@bp_categories.route("/categorie_ajout", methods=['POST'])
def categorie_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] >2:
        return redirect(url_for('permission'))
    client_ident=profile_list[0]
    version_client=profile_list[6]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    if version_client==1:
        budget=request.form['budget']
    else:
        budget=None
    cur.execute('INSERT INTO categories (IDClient, Description, BudgetAnnuel, IDGroupe, CodeGl, Actif) VALUES (%s, %s, %s, %s, %s, %s)',
                 [client_ident, request.form['categorie_desc'], budget , request.form['groupe'], request.form['codeGL'],1])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_categories.categories'))

@bp_categories.route('/categorie_modif/<ident_categorie>', methods=['POST'])
def categorie_modif(ident_categorie):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin ou non (Admin syst.-1 et gestionnaire - 2 seulement)
    if profile_list[2] > 2:
        return redirect(url_for('permission'))
    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1
    client_ident=profile_list[0]
    version_client = profile_list[6]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    if version_client==1:
        budget=request.form['budget']
    else:
        budget=None
    cur.execute("UPDATE categories SET BudgetAnnuel= %s, IDGroupe= %s, CodeGL= %s, Actif= %s WHERE IDCategorie = %s AND IDClient=%s",
                 ([budget, request.form['groupe'], request.form['codeGL'], val_actif, ident_categorie, client_ident]))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_categories.categories'))
