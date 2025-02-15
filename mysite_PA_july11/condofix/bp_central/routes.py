from flask import Blueprint, render_template,g,session,url_for,redirect,request
import sqlite3
from pathlib import Path


bp_central= Blueprint('bp_central', __name__)

#ouverture de la base de données principale
@bp_central.route('/connect_sqlite')
def connect_sqlite():
    """Fonction de connexion à la base de données sqlite 'Central'."""
    # vérifier si l'app est utilisé en dev (pycharm) ou en prod (QA,demo ou app chez PythonAnywhere (PA))
    environnement = Path.cwd()
    cible_db=str()
    env=str()
    if 'home/CondoFix/QA' in str(environnement):
        env = 'QA'
    if 'home/CondoFix/mysite' in str(environnement):
        env = 'APP'
    if 'mysite_PA_july11' in str(environnement):
        env = 'DEV'
    print('env:', env)
    if env == 'DEV':
        cible_db = sqlite3.connect(str('Central.db'))
    if env == 'QA' or env == 'APP':
        cible_db = sqlite3.connect(str('/home/CondoFix/mysite/condofix/Central.db'))
    return cible_db

#********************CENTRAL****************************************
#page de la liste de clients et d'usagers

# pour accéder à la base de données 'Central' (contrôle des clients et usagers)
# afficher page avec mot de passe
@bp_central.route('/central_acces', methods=['POST', 'GET'])
def central_acces():
    """accéder à la base de données 'Central' (contrôle des clients et usagers)

 | afficher page avec mot de passe"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2]!= 1 :  #administrateur de CondoFix seulement
        return redirect(url_for('bp_admin.permission'))
    return render_template('acces_central.html')

# afficher page avec tables
@bp_central.route('/central_table/<via_page_acces>', methods=['POST', 'GET'])
def central_table(via_page_acces):
    """afficher page comprennant tables pour clients et usagers"""
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    if via_page_acces=='oui':
        if request.form['mot_passe']=='LouDoDepuis1999':#ou '1'
            pass
        else:
            return redirect(url_for('bp_admin.permission'))
    g.db= connect_sqlite()
    client_list=[]
    cur= g.db.execute("SELECT IDClient,Nom,Actif,ModuleRez,CarnetPlus,Database FROM Clients")
    for row in cur.fetchall():
        # client actif
        if row[2]==1:
            row+=('Oui',)
        else:
            row+=('Non',)
        # module de réservations
        if row[3]==1:
            row+=('Oui',)
        else:
            row+=('Non',)
        # produit CarnetPlus
        if row[4] == 1:
            row += ('Oui',)
        else:
            row += ('Non',)
        client_list.append(row)
    usagers_list=[]
    cur= g.db.execute("SELECT IDUsager,IDClient,NomUsager,IDTypeUsager,Email,MotPasse,Actif FROM Usagers")
    for row in cur.fetchall():
        if row[6]==1:
            row+=('Oui',)
        else:
            row+=('Non',)
        usagers_list.append(row)
    g.db.close()
    return render_template('central_tables.html',fill_clients=client_list,fill_usagers=usagers_list)


@bp_central.route('/clients_enreg/<parametre>')
def clients_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd sqlite"""

    # si nouveau parametre =0, si modif parametre=liste de valeurs de l'enregistrement
    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    if parametre=='0':
        return render_template('client_ajout.html')
    else:#modification
        g.db= connect_sqlite()
        liste_client=[]

        cur= g.db.execute("SELECT IDClient,Nom,CarnetPlus,Actif,ModuleRez,Database FROM Clients WHERE IDClient=?",(parametre,))
        for row in cur.fetchall():
            liste_client.append(row)
        g.db.close()
        return render_template('client_modif.html', liste_client= liste_client)

#fonctions pour ajouter ou modifier un client
@bp_central.route("/client_ajout", methods=['POST'])
def client_ajout():
    """Ajouter un enregistrement dans la table des clients suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin système
    if profile_list[2] != 1:
        return redirect(url_for('bp_admin.permission'))
    carnetplus=int()
    if request.form['carnet_plus']==1:
        carnetplus=1
    else:
        carnetplus=0
    modulerez=int()
    if request.form['module_rez']==1:
        modulerez=1
    else:
        modulerez=0
    g.db= connect_sqlite()
    g.db.execute('INSERT INTO Clients (Nom,CarnetPlus,Actif,ModuleRez,Database) VALUES (?, ?, ?, ?, ?)',
                 [request.form['client_nom'],carnetplus,1,modulerez,request.form['database']])
    g.db.commit()
    g.db.close()
    return redirect(url_for('bp_central.central_table',via_page_acces='non'))

@bp_central.route('/client_modif/<ident_client>', methods=['POST'])
def client_modif(ident_client):
    """Modifier un enregistrement dans la table des clients suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] != 1:
        return redirect(url_for('bp_admin.permission'))
    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1
    if request.form.get('module_rez') == None:
            val_rez = 0
    else:
            val_rez = 1
    if request.form.get('carnet_plus') == None:
            val_carnet_plus = 0
    else:
            val_carnet_plus = 1
    g.db= connect_sqlite()
    g.db.execute("UPDATE Clients SET Nom= ?,CarnetPlus= ?, Actif= ? , ModuleRez= ?, Database= ? WHERE IDClient = ?",
                 ([request.form['client_nom'], val_carnet_plus, val_actif,
                   val_rez, request.form['database'], ident_client]))
    g.db.commit()
    g.db.close()
    return redirect(url_for('bp_central.central_table',via_page_acces='non'))

@bp_central.route('/usagers_enreg/<parametre>')
def usagers_enreg(parametre):
    """Afficher la page d'ajout ou de modification (selon parametre: 0 ou autres) dans la bd sqlite"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    if parametre=='0':
        return render_template('usager_ajout.html')
    else:#modification
        g.db= connect_sqlite()
        liste_usager=[]
        cur= g.db.execute("SELECT IDUsager,IDClient,NomUsager,IDTypeUsager,Email,MotPasse,Actif FROM Usagers WHERE IDUsager=?",(parametre,))
        for row in cur.fetchall():
            print(parametre)
            print(row)
            liste_usager.append(row)
        g.db.close()
        return render_template('usager_modif.html', liste_usager= liste_usager)


#fonctions pour ajouter ou modifier un usager
@bp_central.route("/usager_ajout", methods=['POST'])
def usager_ajout():
    """Ajouter un enregistrement dans la table des usagers suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si admin système
    if profile_list[2] != 1:
        return redirect(url_for('bp_admin.permission'))
    g.db= connect_sqlite()
    g.db.execute('INSERT INTO Usagers (IDClient,NomUsager,IDTypeUsager,Email,MotPasse,Actif) VALUES (?, ?, ?, ?, ?, ?)',[request.form['usager_idclient'],
        request.form['usager_nom'], request.form['usager_type'],request.form['usager_email'],request.form['usager_motpasse'],request.form['actif']])
    g.db.commit()
    g.db.close()
    return redirect(url_for('bp_central.central_table',via_page_acces='non'))


@bp_central.route('/usager_modif/<ident_usager>', methods=['POST'])
def usager_modif(ident_usager):
    """Modifier un enregistrement dans la table des usagers suivi par retour à la page affichant les enregistrements"""

    if session.get('ProfilUsager') is None:
        # probablement délai de session atteint
        return render_template('session_ferme.html')
    profile_list=session.get('ProfilUsager')
    # vérifier type d'usager si bp_admin ou non
    if profile_list[2] != 1:
        return redirect(url_for('bp_admin.permission'))
    if request.form.get('actif')==None:
        val_actif=0
    else:
        val_actif=1
    g.db= connect_sqlite()
    g.db.execute("UPDATE Usagers SET IDClient=?,NomUsager=?,IDTypeUsager=?,Email=?,MotPasse=?, Actif=? WHERE IDUsager = ?",
                 ([request.form['usager_idclient'], request.form['usager_nom'], request.form['usager_type'],request.form['usager_email']
                     ,request.form['usager_motpasse'], val_actif,ident_usager]))
    g.db.commit()
    g.db.close()
    return redirect(url_for('bp_central.central_table',via_page_acces='non'))