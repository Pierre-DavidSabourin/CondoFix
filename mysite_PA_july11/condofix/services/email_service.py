import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app


def _bool_env(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def send_html_email(subject, recipients, html_body, reply_to=None):
    if isinstance(recipients, str):
        recipients = [email.strip() for email in recipients.split(",") if email.strip()]

    if not recipients:
        raise ValueError("No email recipients provided.")

    if not _bool_env("CONDOFIX_EMAIL_ENABLED", "true"):
        current_app.logger.warning("Email sending disabled: CONDOFIX_EMAIL_ENABLED=false")
        return False

    smtp_host = _required_env("CONDOFIX_SMTP_HOST")
    smtp_port = int(os.getenv("CONDOFIX_SMTP_PORT", "465"))
    smtp_user = _required_env("CONDOFIX_SMTP_USER")
    smtp_password = _required_env("CONDOFIX_SMTP_PASSWORD")
    smtp_from = os.getenv("CONDOFIX_SMTP_FROM", smtp_user)
    use_ssl = _bool_env("CONDOFIX_SMTP_USE_SSL", "true")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = ", ".join(recipients)

    if reply_to:
        msg["Reply-To"] = reply_to

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())

    return True