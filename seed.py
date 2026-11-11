"""
seed.py - The data BICTDA LMS needs before anyone signs up (no demo accounts).

    Programmes (SIWES, NYSC), the 6-month course track and the BICTDA-issued Facilitator IDs.
    app.py adds anything missing every time the app starts, so you rarely need to run this yourself:

    python seed.py           -> create the tables and the reference data
    python seed.py --reset   -> DELETE ALL local SQLite data and start empty (local only, never Neon)
"""
import sys

from extensions import db
from models import COURSE_DURATION_WEEKS, Course, IssuedFacilitatorID, Programme

# ---------------------------------------------------------------------------
# Programmes (both take the same 6-month course track)
# ---------------------------------------------------------------------------
PROGRAMMES = [
    {"code": "SIWES", "name": "Students Industrial Work Experience Scheme", "badge_color": "emerald",
     "description": "Industrial training for university and polytechnic students on attachment at BICTDA."},
    {"code": "NYSC", "name": "National Youth Service Corps", "badge_color": "blue",
     "description": "Digital skills training for corps members whose place of primary assignment (PPA) is BICTDA."},
]

# ---------------------------------------------------------------------------
# THE COURSE TRACK - edit the courses here (one place).
# Every SIWES and NYSC intern takes them in THIS order: 1 + 2 + 1 + 2 = 6 months.
#   (title, description, icon, expected duration in months)
# ---------------------------------------------------------------------------
COURSES = [
    ("Web Development",
     "Build modern websites with HTML, CSS and JavaScript basics: page structure, "
     "styling, responsive layouts and simple interactivity.",
     "fa-solid fa-code", 1),
    ("Data Science & Python",
     "Python programming for data: variables, functions, Pandas, data cleaning, "
     "exploratory analysis and charts.",
     "fa-solid fa-chart-line", 2),
    ("Machine Learning",
     "Supervised and unsupervised learning with scikit-learn: regression, "
     "classification, model evaluation and a mini project.",
     "fa-solid fa-brain", 1),
    ("Cybersecurity",
     "Security fundamentals: networks, threats, passwords and encryption, "
     "secure web practices and basic security auditing.",
     "fa-solid fa-shield-halved", 2),
]


def seed_courses():
    """Create the courses from COURSES. Order in the list = sequence_order. Returns {order: Course}."""
    courses = {}
    for order, (title, description, icon, months) in enumerate(COURSES, start=1):
        course = Course(sequence_order=order, code=f"C{order}", title=title, description=description,
                        icon=icon, duration_weeks=months * COURSE_DURATION_WEEKS)
        db.session.add(course)
        courses[order] = course
    db.session.flush()
    return courses

# ---------------------------------------------------------------------------
# FACILITATOR IDS ISSUED BY BICTDA - the admin adds new IDs here (one place).
# A facilitator can only sign up with an ID from this list, and each ID only once.
# New IDs are added to the database every time the app starts.
#   (Facilitator ID, full name shown on their account)
# You can also add an ID straight into the "issued_facilitator_ids" table in Neon.
# Example line:  ("BICTDA-FAC-001", "Engr. Full Name Here"),
# ---------------------------------------------------------------------------
ISSUED_FACILITATOR_IDS = [
]


def seed_issued_ids():
    """Add any ID from ISSUED_FACILITATOR_IDS that is not in the database yet. Returns how many were added."""
    existing = {row.facilitator_id for row in IssuedFacilitatorID.query.all()}
    new_ids = [(fid, name) for fid, name in ISSUED_FACILITATOR_IDS if fid not in existing]
    for fid, name in new_ids:
        db.session.add(IssuedFacilitatorID(facilitator_id=fid, full_name=name))
    if new_ids:
        db.session.commit()
    return len(new_ids)


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------
def seed_reference_data():
    """
    Programmes, the course track and the issued Facilitator IDs - sign-up needs them
    (it lists SIWES/NYSC and the courses). Only adds what is missing, so it is safe on every start.
    """
    if Programme.query.first() is None:
        for p in PROGRAMMES:
            db.session.add(Programme(code=p["code"], name=p["name"],
                                     description=p["description"], badge_color=p["badge_color"]))
    if Course.query.first() is None:
        seed_courses()
    db.session.commit()
    seed_issued_ids()


def _make_cli_app():
    """A minimal Flask app so this file can run on its own (before app.py exists)."""
    from flask import Flask

    from config import Config

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


if __name__ == "__main__":
    app = _make_cli_app()
    with app.app_context():
        if "--reset" in sys.argv:
            if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
                sys.exit("[seed] --reset is only allowed for the local SQLite database.")
            print("[seed] Resetting local database...")
            db.drop_all()
        db.create_all()
        seed_reference_data()
        print(f"[seed] Tables, programmes, courses and issued Facilitator IDs are ready in "
              f"{app.config['SQLALCHEMY_DATABASE_URI']}")
