import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
#-*-coding: Utf-8-*-

__author__ = 'donald'

from flask import Flask, request
import matplotlib
from datetime import timedelta
from flask_dropzone import Dropzone


import smtplib
from werkzeug.exceptions import HTTPException
matplotlib.use('Agg')#pour éviter que le retour au tableau de bord cause une erreur
import traceback
app = Flask(__name__)

# #pour éviter que l'engin de template jinja ajoute des espaces entre les lignes
app.jinja_env.trim_blocks = False
app.jinja_env.lstrip_blocks = False

from bp_public.routes import bp_public
from bp_admin.routes import bp_admin
from bp_categories.routes import bp_categories
from bp_documentation.routes import bp_documentation
from bp_equipements.routes import bp_equipements
from bp_factures.routes import bp_factures
from bp_fonds_prevoyance.routes import bp_fonds_prevoyance
from bp_intervenants.routes import bp_intervenants
from bp_preventif.routes import bp_preventif
from bp_tableaux_bord.routes import bp_tableaux_bord
from bp_tickets.routes import bp_tickets
from bp_central.routes import bp_central
from bp_reservations.routes import bp_reservations
from bp_ressources.routes import bp_ressources
from bp_contacts.routes import bp_contacts
from bp_rapports.routes import bp_rapports
from bp_signalements.routes import bp_signalements
from bp_parametres.routes import bp_parametres
from bp_ocr.routes import bp_ocr
from bp_sinistres.routes import bp_sinistres

app.register_blueprint(bp_public)
app.register_blueprint(bp_admin)
app.register_blueprint(bp_categories)
app.register_blueprint(bp_documentation)
app.register_blueprint(bp_equipements)
app.register_blueprint(bp_factures)
app.register_blueprint(bp_fonds_prevoyance)
app.register_blueprint(bp_intervenants)
app.register_blueprint(bp_preventif)
app.register_blueprint(bp_tableaux_bord)
app.register_blueprint(bp_tickets)
app.register_blueprint(bp_central)
app.register_blueprint(bp_reservations)
app.register_blueprint(bp_ressources)
app.register_blueprint(bp_contacts)
app.register_blueprint(bp_rapports)
app.register_blueprint(bp_signalements)
app.register_blueprint(bp_parametres)
app.register_blueprint(bp_ocr)
app.register_blueprint(bp_sinistres)


app.config['SECRET_KEY'] = 'OHOSZO5D382UAL9J'
# délai pour fermeture de session
app.config['PERMANENT_SESSION_LIFETIME'] =  timedelta(minutes=30)
app.config.update(
       DROPZONE_MAX_FILE_SIZE = 5,
       DROPZONE_TIMEOUT = 5*60*1000,
       DROPZONE_ACCEPTED_FILES = 'image/*,application/pdf',
       DROPZONE_DEFAULT_MESSAGE = 'Glisser le fichier ici ou cliquer pour télécharger')

dropzone = Dropzone(app)

# @app.errorhandler(500)
# def handle_exception(e):
#     #pass through HTTP errors
#     if isinstance(e, HTTPException):
#         # envoi d'email dans le cas d'une erreur ('internal server error' par exemple)
#         sujet='Erreur pour CondoFix SERVEUR'
#         body=traceback.format_exc()
#         yahoo_mail_user = 'condofix.ca@yahoo.com'
#         yahoo_mail_password = 'spyvlumgfwscqfkc'
#         sent_from = yahoo_mail_user
#         sent_to = ['donald.boileau@gmail.com']
#         subject = sujet
#         email_text = """From: %s\nTo: %s\nSubject: %s\n\n%s""" % (sent_from, ", ".join(sent_to), subject, body)
#         server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
#         server.ehlo()
#         server.login(yahoo_mail_user, yahoo_mail_password)
#         server.sendmail(sent_from, sent_to, email_text)
#         server.close()
#         return render_template('-erreur.html')


# #ajout de 'host' et port pour s'assurer de la vitesse du site en test
if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(host="127.0.0.1", port=8080, threaded=True, debug=True)

