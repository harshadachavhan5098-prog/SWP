import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)


def send_password_reset(email, reset_url):
    config = current_app.config
    if not config["SMTP_HOST"]:
        if config["ENV"] == "production":
            raise RuntimeError("SMTP is not configured.")
        logger.warning("Development password reset URL for %s: %s", email, reset_url)
        return
    message = EmailMessage()
    message["Subject"] = "Reset your SWP password"
    message["From"] = config["SMTP_FROM"]
    message["To"] = email
    message.set_content(f"Use this secure one-time link within {config['PASSWORD_RESET_TTL_MINUTES']} minutes: {reset_url}")
    with smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=15) as server:
        if config["SMTP_USE_TLS"]:
            server.starttls()
        if config["SMTP_USERNAME"]:
            server.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
        server.send_message(message)
