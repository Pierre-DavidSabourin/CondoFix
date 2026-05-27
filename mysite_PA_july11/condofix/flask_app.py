import sys
import os
import traceback
from datetime import timedelta
from html import escape
from pathlib import Path

import matplotlib
from flask import Flask, Response, render_template, request
from flask_dropzone import Dropzone
from werkzeug.exceptions import HTTPException

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for path in (BASE_DIR, PROJECT_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

def bool_env(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")
#-*-coding: Utf-8-*-

__author__ = 'donald'

matplotlib.use('Agg')#pour éviter que le retour au tableau de bord cause une erreur

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
#from bp_sinistres.routes import bp_sinistres

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
#app.register_blueprint(bp_sinistres) # feature will not be implemented

app.config["CONDOFIX_ENV"] = os.getenv("CONDOFIX_ENV", "DEV").upper()
app.config["ERROR_EMAIL_ENABLED"] = bool_env("CONDOFIX_ERROR_EMAIL_ENABLED", "false")
app.config["ERROR_EMAIL_RECIPIENTS"] = os.getenv(
    "CONDOFIX_ERROR_EMAIL_RECIPIENTS",
    "sabourinpd@outlook.com"
)

# =========================
# SEO infrastructure routes
# =========================

@app.route("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /login",
        "Sitemap: https://www.condofix.ca/sitemap.xml",
    ]
    resp = Response("\n".join(lines) + "\n", mimetype="text/plain; charset=utf-8")
    resp.headers["Cache-Control"] = "public, max-age=86400"  # 24h
    return resp

@app.route("/sitemap.xml")
def sitemap_xml():
    base = "https://www.condofix.ca"

    # Per-URL lastmod (update only when the page meaningfully changes)
    URL_LASTMOD = {
        "/": "2026-01-03",
        "/produits": "2026-01-03",
        "/services": "2026-01-03",
        "/carnet_entretien": "2025-12-30",
        "/module_fdp": "2025-12-30",
        "/demande_info": "2025-12-10",
        "/tarifs/1": "2026-01-03",
    }

    # (path, changefreq, priority)
    url_config = [
        ("/",                 "weekly",  "1.0"),
        ("/produits",         "monthly", "0.9"),
        ("/services",         "monthly", "0.9"),
        ("/carnet_entretien", "yearly",  "0.8"),
        ("/module_fdp",       "yearly",  "0.8"),
        ("/demande_info",     "monthly", "0.7"),
        ("/tarifs/1",         "monthly", "0.8"),
    ]

    urls_xml = []
    for path, changefreq, priority in url_config:
        loc = f"{base}{path}"

        lastmod = URL_LASTMOD.get(path)
        lastmod_xml = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""

        urls_xml.append(
f"""  <url>
    <loc>{loc}</loc>{lastmod_xml}
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>"""
        )

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls_xml)}
</urlset>
"""

    resp = Response(xml, mimetype="application/xml; charset=utf-8")
    resp.headers["Cache-Control"] = "public, max-age=86400"  # 24h
    return resp


# app.config['SECRET_KEY'] = 'OHOSZO5D382UAL9J'
app.config['SECRET_KEY'] = required_env('CONDOFIX_SECRET_KEY')
# délai pour fermeture de session
app.config['PERMANENT_SESSION_LIFETIME'] =  timedelta(minutes=30)
app.config.update(
       DROPZONE_MAX_FILE_SIZE = 5,
       DROPZONE_TIMEOUT = 5*60*1000,
       DROPZONE_ACCEPTED_FILES = 'image/*,application/pdf',
       DROPZONE_DEFAULT_MESSAGE = 'Glisser le fichier ici ou cliquer pour télécharger')

dropzone = Dropzone(app)

@app.errorhandler(500)
def handle_exception(e):
    """
    QA/TEST server error handler.

    Sends an error email only when CONDOFIX_ERROR_EMAIL_ENABLED=true.
    SMTP credentials are handled by services.email_service and .env.
    """
    if isinstance(e, HTTPException):
        app.logger.exception("Internal server error")

    if app.config.get("ERROR_EMAIL_ENABLED", False):
        try:
            from services.email_service import send_html_email

            body = escape(traceback.format_exc())

            html = f"""
            <html>
              <body>
                <p><b>Environnement:</b> {escape(app.config.get("CONDOFIX_ENV", "UNKNOWN"))}</p>
                <p><b>Erreur serveur CondoFix</b></p>
                <pre>{body}</pre>
              </body>
            </html>
            """

            send_html_email(
                subject=f"Erreur CondoFix SERVEUR - {app.config.get('CONDOFIX_ENV', 'UNKNOWN')}",
                recipients=app.config.get("ERROR_EMAIL_RECIPIENTS"),
                html_body=html
            )
        except Exception:
            app.logger.exception("Erreur lors de l'envoi du courriel d'erreur serveur.")

    return render_template('-erreur.html'), 500

@app.context_processor
def inject_theme_ui() -> object:
    return {
        "theme_ui": request.cookies.get("condofix_theme_ui", "normal-condofix-classic")
    }


# #ajout de 'host' et port pour s'assurer de la vitesse du site en test
if __name__ == '__main__':
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(host="127.0.0.1", port=8080, threaded=True, debug=True)

