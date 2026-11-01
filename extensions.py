"""
extensions.py - Flask extension objects.

They are created here (without an app) and connected to the app later in
app.py. Keeping them in their own file avoids circular imports between
app.py, models.py and services.py.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
