"""
config.py - Central configuration for BICTDA LMS.

All settings come from environment variables (or a local .env file), so the
same code runs on your laptop (SQLite) and on Render (Neon PostgreSQL)
without any changes.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Folder that contains this file (the project root)
BASE_DIR = Path(__file__).resolve().parent

# Load variables from .env when running locally (Render sets them directly)
load_dotenv(BASE_DIR / ".env")


def get_database_url():
    """
    Decide which database to use:
      - No DATABASE_URL set  -> local SQLite file  bictda_lms.db  in the project root
      - DATABASE_URL set     -> PostgreSQL (Neon), using the psycopg 3 driver
    """
    url = os.environ.get("DATABASE_URL", "").strip()

    if not url:
        sqlite_path = (BASE_DIR / "bictda_lms.db").as_posix()
        return f"sqlite:///{sqlite_path}"

    # Neon/Render give URLs like postgres://... or postgresql://...
    # SQLAlchemy needs postgresql+psycopg://... to use the psycopg 3 driver.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Config:
    FLASK_ENV = os.environ.get("FLASK_ENV", "development").lower()
    IS_PRODUCTION = FLASK_ENV == "production"

    # Secret key signs session cookies. In production it MUST come from the environment.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-insecure-key-change-me"
    if IS_PRODUCTION and not os.environ.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY environment variable must be set in production.")

    # Database
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,   # test connections first (Neon suspends idle databases)
        "pool_recycle": 280,     # refresh connections every ~5 minutes
    }
    if SQLALCHEMY_DATABASE_URI.startswith("postgresql"):
        # Neon's pooled connection (PgBouncer) - turn off psycopg's automatic prepared statements
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"prepare_threshold": None}

    # Password-reset emails. Render's free plan blocks normal email (SMTP), so emails go
    # through Brevo's web API (free: 300 emails a day). Without a key, on your laptop the
    # reset link is printed in the terminal instead.
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
    MAIL_SENDER_EMAIL = os.environ.get("MAIL_SENDER_EMAIL", "")   # the sender address you verified in Brevo
    MAIL_SENDER_NAME = "BICTDA LMS"
    RESET_LINK_MINUTES = 60                                         # a reset link works for 1 hour, once

    # Security (CSRF + cookies)
    WTF_CSRF_TIME_LIMIT = None             # CSRF token valid for the whole session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION  # cookies only over HTTPS on Render
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = IS_PRODUCTION

    # App version - changes on every deploy so installed phone apps update themselves.
    # Render sets RENDER_GIT_COMMIT; on your laptop the start-up time is used instead.
    APP_VERSION = os.environ.get("RENDER_GIT_COMMIT", "")[:12] or datetime.now().strftime("%Y%m%d%H%M%S")

    # Assignment uploads - files are saved in the database (Render's free disk is wiped on every deploy)
    MAX_UPLOAD_MB = 5
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024   # Flask rejects bigger requests (error 413)
    ALLOWED_UPLOAD_EXTENSIONS = {
        "pdf", "doc", "docx", "txt",             # documents (every course)
        "html", "htm", "css", "js",              # Web Development
        "py", "ipynb",                           # Data Science & Python / Machine Learning
    }

    # Result slip signatory
    RESULT_SIGNATORY_NAME = "Engr. Mohammed Kabir Wanori FNSE FNIEEE"
    RESULT_SIGNATORY_TITLE = "Executive Secretary, BICTDA"

    # Branding
    APP_NAME = "BICTDA LMS"
    APP_FULL_NAME = "BICTDA Internship & Digital Skills Portal"
    AGENCY_NAME = "Borno State Information and Communication Technology Development Agency"
