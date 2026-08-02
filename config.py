import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    ENV = os.environ.get("FLASK_ENV", "development")
    DEBUG = ENV == "development"
    PORT = int(os.environ.get("PORT", "5000"))
    SECRET_KEY = os.environ.get("SWP_SECRET_KEY") or os.urandom(32)
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "database.db"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_BYTES", 12 * 1024 * 1024))
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "txt", "md"}
    SESSION_COOKIE_NAME = "swp_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ENV == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = ENV == "production"
    REMEMBER_COOKIE_SAMESITE = "Lax"
    PASSWORD_RESET_TTL_MINUTES = int(os.environ.get("PASSWORD_RESET_TTL_MINUTES", "30"))
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_FROM = os.environ.get("SMTP_FROM")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    ADMIN_EMAILS = {value.strip().lower() for value in os.environ.get("ADMIN_EMAILS", "").split(",") if value.strip()}

    @classmethod
    def validate(cls):
        if cls.ENV == "production" and not os.environ.get("SWP_SECRET_KEY"):
            raise RuntimeError("SWP_SECRET_KEY is required in production.")
