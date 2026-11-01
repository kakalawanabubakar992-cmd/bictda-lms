"""
seed.py - Fill an EMPTY database with realistic demo data.

Run it yourself:
    python seed.py           -> create tables and seed (only if the database is empty)
    python seed.py --reset   -> DELETE the local SQLite data and seed again (local only)

From Phase 2, app.py also calls seed_database() automatically on start-up.
Seeding is idempotent: if any user already exists, nothing is changed.
"""
import random
import sys
from datetime import datetime, time, timedelta

from extensions import db
from models import (
    ATT_ABSENT,
    ATT_LATE,
    ATT_PUNCTUAL,
    ROLE_FACILITATOR,
    ROLE_INTERN,
    Assignment,
    Course,
    Programme,
    Submission,
    User,
)
from services import (
    calculate_attendance_rate,
    create_notification,
    enroll_intern,
    generate_facilitator_id,
    generate_intern_id,
    grade_submission,
    mark_attendance,
    record_final_result,
)
from utils import normalize_phone, today_wat

# Demo passwords (shown on screen after seeding - change them for real use)
INTERN_PASSWORD = "Intern@123"
FACILITATOR_PASSWORD = "Facilitator@123"

# ---------------------------------------------------------------------------
# Programmes & course tracks
# ---------------------------------------------------------------------------
PROGRAMMES = [
    {
        "code": "SIWES",
        "name": "Students Industrial Work Experience Scheme",
        "badge_color": "emerald",
        "description": "Industrial training for university and polytechnic students "
                       "on attachment at BICTDA.",
        "courses": [
            ("Web Development",
             "Build modern websites with HTML, CSS and JavaScript basics: page structure, "
             "styling, responsive layouts and simple interactivity.", "fa-solid fa-code"),
            ("Data Science & Python",
             "Python programming for data: variables, functions, Pandas, data cleaning, "
             "exploratory analysis and charts.", "fa-solid fa-chart-line"),
            ("Machine Learning",
             "Supervised and unsupervised learning with scikit-learn: regression, "
             "classification, model evaluation and a mini project.", "fa-solid fa-brain"),
            ("Cybersecurity",
             "Security fundamentals: networks, threats, passwords and encryption, "
             "secure web practices and basic security auditing.", "fa-solid fa-shield-halved"),
        ],
    },
    {
        "code": "NYSC",
        "name": "National Youth Service Corps",
        "badge_color": "blue",
        "description": "Digital skills training for corps members whose place of "
                       "primary assignment (PPA) is BICTDA.",
        "courses": [
            ("HTML5 & Web Structure Fundamentals",
             "Semantic HTML5, page structure, forms, tables, media and accessibility basics.",
             "fa-brands fa-html5"),
            ("CSS3 & Responsive UI Design",
             "CSS3 styling, Flexbox, Grid, responsive design and modern UI principles.",
             "fa-solid fa-palette"),
            ("Python Programming (Beginners)",
             "Python syntax, data types, control flow, functions, lists and dictionaries.",
             "fa-brands fa-python"),
            ("Python Advanced & Web Backend Development",
             "OOP, modules, working with databases and building web backends with Flask.",
             "fa-solid fa-server"),
        ],
    },
]

FACILITATORS = [
    {"full_name": "Engr. Babagana Modu", "email": "babagana.modu@bictda.test",
     "phone": "08031110001", "specialization": "Software Engineering & Data Science",
     "teaches": "SIWES"},
    {"full_name": "Mrs. Fatima Bukar Kyari", "email": "fatima.kyari@bictda.test",
     "phone": "08031110002", "specialization": "Web Development & Python Programming",
     "teaches": "NYSC"},
]

# scenario: what has happened to this intern so far
#   "passed_c1" -> passed Course 1, now on Course 2
#   "failed_c1" -> scored exactly 50% in Course 1 (FAIL), retake required
#   "on_c1"     -> currently on Course 1
INTERNS = [
    {"programme": "SIWES", "full_name": "Aisha Mohammed Goni", "email": "aisha.goni@student.test",
     "phone": "08031234501", "institution": "University of Maiduguri",
     "days_ago": 42, "scenario": "passed_c1", "attendance": "perfect"},
    {"programme": "SIWES", "full_name": "Umar Ali Bukar", "email": "umar.bukar@student.test",
     "phone": "08031234502", "institution": "Ramat Polytechnic, Maiduguri",
     "days_ago": 35, "scenario": "failed_c1", "attendance": "weak"},
    {"programme": "SIWES", "full_name": "Hauwa Ibrahim Shettima", "email": "hauwa.shettima@student.test",
     "phone": "08031234503", "institution": "Borno State University",
     "days_ago": 14, "scenario": "on_c1", "attendance": "good"},
    {"programme": "NYSC", "full_name": "Chinedu Emmanuel Okafor", "email": "chinedu.okafor@corps.test",
     "phone": "08031234504", "institution": "PPA: BICTDA Headquarters, Maiduguri",
     "days_ago": 21, "scenario": "on_c1", "attendance": "good"},
    {"programme": "NYSC", "full_name": "Zainab Musa Lawan", "email": "zainab.lawan@corps.test",
     "phone": "08031234505", "institution": "PPA: BICTDA Headquarters, Maiduguri",
     "days_ago": 14, "scenario": "on_c1", "attendance": "excellent"},
]

# Probability of (Punctual, Late, Absent) for each attendance profile
ATTENDANCE_PROFILES = {
    "perfect": (1.00, 0.00, 0.00),
    "excellent": (0.90, 0.10, 0.00),
    "good": (0.75, 0.15, 0.10),
    "weak": (0.50, 0.25, 0.25),
}

# Assignments: (programme, course sequence) -> [(title, instructions, due in N days, max score)]
# Negative days = due date already passed.
ASSIGNMENTS = {
    ("SIWES", 1): [
        ("Personal Portfolio Page (HTML Structure)",
         "Build a one-page personal portfolio using semantic HTML (header, nav, main, section, "
         "footer). Include an About section, a Skills list and a Contact section. "
         "Push it to GitHub and submit the repository link.", -18, 20),
        ("Responsive Landing Page with CSS Flexbox",
         "Style your portfolio with an external CSS file. Use Flexbox for the navigation and "
         "skills cards, and add a media query so it looks good on phones.", -8, 20),
        ("JavaScript Form Validation",
         "Add a contact form and write JavaScript that checks the name, email and message "
         "fields before submission. Show friendly error messages.", 5, 30),
    ],
    ("SIWES", 2): [
        ("Python Basics: Cleaning Rainfall Data",
         "Using Python lists and dictionaries, clean the sample Borno monthly rainfall data "
         "(remove blanks, fix units) and print the average for each year.", -4, 25),
        ("Exploratory Data Analysis with Pandas",
         "Load the provided CSV into Pandas, describe the data, find missing values and "
         "create two charts with Matplotlib. Submit a Google Colab or GitHub link.", 6, 25),
    ],
    ("SIWES", 3): [
        ("Linear Regression: Predicting Crop Yield",
         "Train a linear regression model with scikit-learn on the crop yield dataset, "
         "report the R-squared score and explain your results in 200 words.", 35, 50),
    ],
    ("SIWES", 4): [
        ("Network Security Audit Report",
         "Perform a basic security audit of a home or office network (password policy, "
         "router settings, open ports) and write a 2-page report with recommendations.", 63, 50),
    ],
    ("NYSC", 1): [
        ("Semantic HTML5 Page for a Local Business",
         "Create a web page for a local business in Maiduguri using semantic HTML5 elements. "
         "Include a header, services list, opening hours table and footer.", -12, 20),
        ("Corps Member Registration Form",
         "Build an HTML form that collects a corps member's name, state code, PPA, phone "
         "and email. Use the correct input types and labels.", -2, 20),
        ("Accessible Multimedia Page",
         "Add images, an audio clip and a video to a page with proper alt text, captions "
         "and keyboard-friendly controls.", 6, 20),
    ],
    ("NYSC", 2): [
        ("Responsive CSS Grid Layout",
         "Recreate a news homepage layout using CSS Grid that changes from 3 columns on "
         "desktop to 1 column on phones.", 25, 30),
    ],
    ("NYSC", 3): [
        ("Python Mini Project: Student Grade Calculator",
         "Write a Python program that reads student scores, calculates averages and grades, "
         "and prints a neat report.", 50, 40),
    ],
    ("NYSC", 4): [
        ("Flask REST API for a To-Do App",
         "Build a small Flask API with routes to create, list, update and delete tasks "
         "stored in SQLite.", 80, 50),
    ],
}

# Demo submissions: (intern email, programme, course seq, assignment index,
#                    submitted N days ago, score or None, feedback)
SUBMISSIONS = [
    ("aisha.goni@student.test", "SIWES", 1, 0, 20, 18, "Excellent use of semantic tags."),
    ("aisha.goni@student.test", "SIWES", 1, 1, 17, 17, "Clean, responsive layout."),
    ("aisha.goni@student.test", "SIWES", 1, 2, 16, 26, "Great validation messages."),
    ("aisha.goni@student.test", "SIWES", 2, 0, 5, 22, "Good data cleaning steps."),
    ("aisha.goni@student.test", "SIWES", 2, 1, 1, None, None),
    ("umar.bukar@student.test", "SIWES", 1, 0, 16, 9, "Incomplete - footer and contact section missing."),
    ("umar.bukar@student.test", "SIWES", 1, 1, 9, None, None),
    ("hauwa.shettima@student.test", "SIWES", 1, 0, 10, 15, "Good work, submitted late."),
    ("hauwa.shettima@student.test", "SIWES", 1, 1, 9, None, None),
    ("chinedu.okafor@corps.test", "NYSC", 1, 0, 13, 17, "Well structured page."),
    ("chinedu.okafor@corps.test", "NYSC", 1, 1, 1, None, None),
    ("zainab.lawan@corps.test", "NYSC", 1, 0, 11, None, None),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _weekdays(start, end):
    """All Monday-Friday dates from start to end (inclusive)."""
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def _seed_attendance(intern, progress, profile, rng, marked_by):
    """Mark weekday attendance from the course start until yesterday (or the course end)."""
    yesterday = today_wat() - timedelta(days=1)
    last_class_day = min(progress.end_date - timedelta(days=1), yesterday)
    weights = ATTENDANCE_PROFILES[profile]
    for day in _weekdays(progress.start_date, last_class_day):
        status = rng.choices([ATT_PUNCTUAL, ATT_LATE, ATT_ABSENT], weights=weights)[0]
        mark_attendance(intern, progress.course, day, status, marked_by=marked_by, commit=False)


def _at(day, hour=10, minute=0):
    return datetime.combine(day, time(hour, minute))


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------
def seed_database(verbose=True):
    """Seed demo data ONLY if the database has no users. Returns True if it seeded."""
    if User.query.first() is not None:
        if verbose:
            print("[seed] Database already has data - seeding skipped.")
        return False

    today = today_wat()

    # 1. Programmes and courses
    programmes = {}
    for p in PROGRAMMES:
        programme = Programme(code=p["code"], name=p["name"],
                              description=p["description"], badge_color=p["badge_color"])
        db.session.add(programme)
        for order, (title, description, icon) in enumerate(p["courses"], start=1):
            db.session.add(Course(programme=programme, sequence_order=order,
                                  code=f"{p['code']}-C{order}", title=title,
                                  description=description, icon=icon, duration_weeks=4))
        programmes[p["code"]] = programme
    db.session.flush()

    # 2. Facilitators (each teaches one programme's track)
    facilitators = {}
    for f in FACILITATORS:
        facilitator = User(role=ROLE_FACILITATOR, full_name=f["full_name"], email=f["email"].lower(),
                           phone=normalize_phone(f["phone"]), facilitator_id=generate_facilitator_id(),
                           specialization=f["specialization"])
        facilitator.set_password(FACILITATOR_PASSWORD)
        db.session.add(facilitator)
        db.session.flush()
        for course in programmes[f["teaches"]].courses:
            course.facilitator = facilitator
        facilitators[f["teaches"]] = facilitator

    # 3. Assignments
    assignments = {}
    for (prog_code, seq), items in ASSIGNMENTS.items():
        course = programmes[prog_code].courses[seq - 1]
        for index, (title, instructions, due_in_days, max_score) in enumerate(items):
            assignment = Assignment(course=course, title=title, instructions=instructions,
                                    due_date=_at(today + timedelta(days=due_in_days), 23, 59),
                                    max_score=max_score,
                                    created_by=facilitators[prog_code],
                                    created_at=_at(today + timedelta(days=due_in_days - 10)))
            db.session.add(assignment)
            assignments[(prog_code, seq, index)] = assignment
    db.session.flush()

    # 4. Interns, enrollment, attendance and course results
    interns = {}
    for i in INTERNS:
        programme = programmes[i["programme"]]
        facilitator = facilitators[i["programme"]]
        start = today - timedelta(days=i["days_ago"])

        intern = User(role=ROLE_INTERN, full_name=i["full_name"], email=i["email"].lower(),
                      phone=normalize_phone(i["phone"]), intern_id=generate_intern_id(programme.code),
                      programme=programme, institution=i["institution"], enrollment_date=start)
        intern.set_password(INTERN_PASSWORD)
        db.session.add(intern)
        db.session.flush()

        progress = enroll_intern(intern, start_date=start, commit=False)
        rng = random.Random(2026 + intern.id)   # fixed seed -> same demo data every time
        course1 = progress[0]
        _seed_attendance(intern, course1, i["attendance"], rng, facilitator)

        if i["scenario"] == "passed_c1":
            # Passed Course 1 with 78% at the end of the month -> Course 2 unlocks automatically
            record_final_result(course1, 78, graded_by=facilitator,
                                effective_date=course1.end_date, commit=False)
            _seed_attendance(intern, progress[1], "excellent", rng, facilitator)
        elif i["scenario"] == "failed_c1":
            # Exactly 50% is NOT above 50% -> FAIL, Course 2 stays locked
            record_final_result(course1, 50, graded_by=facilitator,
                                effective_date=course1.end_date, commit=False)

        create_notification(intern, f"Welcome to the BICTDA {programme.code} Internship Portal, "
                                    f"{intern.full_name.split()[0]}!",
                            icon="fa-solid fa-hand-sparkles", commit=False)
        interns[intern.email] = intern

    # 5. Submissions and grades
    for email, prog_code, seq, index, days_ago, score, feedback in SUBMISSIONS:
        intern = interns[email]
        assignment = assignments[(prog_code, seq, index)]
        submitted_at = _at(today - timedelta(days=days_ago), 14, 30)
        submission = Submission(assignment=assignment, intern=intern,
                                response_text=f"My submission for '{assignment.title}'. "
                                              f"Please see the link for the full work.",
                                link_url=f"https://github.com/example/{intern.intern_id.lower()}-task{index + 1}",
                                submitted_at=submitted_at, updated_at=submitted_at,
                                is_late=submitted_at > assignment.due_date)
        db.session.add(submission)
        if score is not None:
            grade_submission(submission, score, feedback, graded_by=facilitators[prog_code], commit=False)

    db.session.commit()

    if verbose:
        _print_summary()
    return True


def _print_summary():
    line = "=" * 78
    print(line)
    print(" BICTDA LMS - DEMO DATA CREATED")
    print(line)
    print(f" {'ROLE':<13}{'LOGIN ID':<20}{'NAME':<27}PASSWORD")
    print("-" * 78)
    for user in User.query.order_by(User.role, User.id).all():
        role = "Facilitator" if user.is_facilitator else f"{user.programme.code} Intern"
        password = FACILITATOR_PASSWORD if user.is_facilitator else INTERN_PASSWORD
        print(f" {role:<13}{user.login_id:<20}{user.full_name[:25]:<27}{password}")
    print("-" * 78)
    print(" Interns can also sign in with their email or phone, e.g. 08031234501")
    print(line)
    print(" BUSINESS RULE CHECK")
    for user in User.query.filter_by(role=ROLE_INTERN).order_by(User.id).all():
        parts = []
        for p in user.ordered_progress:
            label = f"C{p.course.sequence_order}:{p.status_label}"
            if p.final_score is not None:
                label += f"({p.final_score:g}%)"
            parts.append(label)
        current = user.current_progress
        rate = calculate_attendance_rate(user.id, current.course_id) if current else 0
        print(f"  {user.intern_id:<18} {' | '.join(parts)}")
        if current:
            print(f"  {'':<18} current: {current.course.title} - attendance {rate}%")
    print(line)


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
        print(f"[seed] Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
        seed_database()
