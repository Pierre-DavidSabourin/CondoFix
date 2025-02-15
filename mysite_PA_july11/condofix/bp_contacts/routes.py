from flask import Blueprint, render_template,g,session,url_for,redirect,request
import mysql.connector
from utils import connect_db

bp_contacts = Blueprint('bp_contacts', __name__)


#********************CONTACTS****************************************

#page de la liste de contacts pour les proprios
@bp_contacts.route("/contacts_table_proprios")
def contacts_table_proprios():
    """afficher la page de la table d'enregistrements

    |Page dédiée aux copropriétaires car pas de fonctionnalités d'ajout ou de modif
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    fill_contacts=[]
    client_ident=profile_list[0]
    mode=profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("SELECT IDContact,NomPrenom,Titre,Description,Email,Telephone from contacts WHERE IDClient=%s",(client_ident,))
    for row in cur.fetchall():
        fill_contacts.append(row)
    return render_template('contacts_table_proprios.html', fill_contacts=fill_contacts,bd=profile_list[3])



#page de la liste de contacts avec fonction ajout
@bp_contacts.route("/contacts_table_admin")
def contacts_table_admin():
    """afficher la page de la table d'enregistrements avec fonction ajout et modif réservée aux admin
"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    fill_contacts=[]
    client_ident=profile_list[0]

    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("SELECT IDContact,NomPrenom,Titre,Description,Email,Telephone from contacts WHERE IDClient=%s",
                (client_ident,))
    for row in cur.fetchall():
        fill_contacts.append(row)
    return render_template('contacts_table_admin.html', fill_contacts=fill_contacts,bd=profile_list[3])

#page enregistrement contact (nouveau ou modifier)
@bp_contacts.route('/contact_enreg/<parametre>')
def contact_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd mysql"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    # si nouveau parametre =0, si modif parametre=liste de valeurs de l'enregistrement
    if parametre=='0':
        return render_template('contact_ajout.html',bd=profile_list[3])
    else:
        print('parametre:', parametre)
        liste_contact=[]
        client_ident=profile_list[0]
        mode = profile_list[8]
        cnx = connect_db(mode)
        cur = cnx.cursor()
        cur.execute("SELECT IDContact,NomPrenom,Titre,Description,Email,Telephone from contacts WHERE IDContact=%s AND IDClient=%s",(parametre,client_ident))
        for row in cur.fetchall():
            liste_contact.append(row)
        cnx.close()
        return render_template('contact_modif.html', liste_contact= liste_contact,bd=profile_list[3])

#fonctions pour ajouter ou modifier un contact
@bp_contacts.route("/contact_ajout", methods=['POST'])
def contact_ajout():
    """Ajouter un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute('INSERT INTO contacts (IDClient, NomPrenom,Titre,Description,Email,Telephone) '
                 'VALUES (%s, %s, %s, %s, %s, %s)',
                 [client_ident, request.form['contact_nom'], request.form['contact_titre'], request.form['contact_desc'],
                  request.form['contact_email'],request.form['contact_tel']])
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_contacts.contacts_table_admin'))

@bp_contacts.route('/contact_modif/<ident_contact>', methods=['POST'])
def contact_modif(ident_contact):
    """Modifier un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("UPDATE contacts SET NomPrenom= %s,Titre= %s, Description= %s, Email=%s, Telephone= %s WHERE IDContact = %s AND IDClient=%s",
                 ([request.form['contact_nom'], request.form['contact_titre'], request.form['contact_desc'], request.form['contact_email'],
                   request.form['contact_tel'], ident_contact, client_ident]))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_contacts.contacts_table_admin'))

@bp_contacts.route('/contact_supprime/<ident_contact>', methods=['POST','GET'])
def contact_supprime(ident_contact):
    """Supprimer un enregistrement dans la table mysql suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager (admin seulement)
    if profile_list[2] > 2:
        return redirect(url_for('bp_admin.permission'))
    client_ident=profile_list[0]
    mode = profile_list[8]
    cnx = connect_db(mode)
    cur = cnx.cursor()
    cur.execute("DELETE FROM contacts WHERE IDContact=%s AND IDClient=%s",(ident_contact,client_ident))
    cnx.commit()
    cnx.close()
    return redirect(url_for('bp_contacts.contacts_table_admin'))