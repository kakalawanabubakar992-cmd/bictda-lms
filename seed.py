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
    COURSE_DURATION_WEEKS,
    DEPT_CYBERSECURITY,
    DEPT_SOFTWARE_DATA,
    ROLE_INTERN,
    Assignment,
    Course,
    IssuedFacilitatorID,
    Programme,
    Submission,
    User,
)
from services import (
    calculate_attendance_rate,
    create_notification,
    enroll_intern,
    generate_intern_id,
    grade_submission,
    mark_attendance,
    record_final_result,
    register_facilitator,
)
from utils import normalize_phone, today_wat

# Demo passwords (shown on screen after seeding - change them for real use)
INTERN_PASSWORD = "Intern@123"
FACILITATOR_PASSWORD = "Facilitator@123"

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
# ---------------------------------------------------------------------------
ISSUED_FACILITATOR_IDS = [
    ("BICTDA-FAC-001", "Engr. Babagana Modu"),
    ("BICTDA-FAC-002", "Mrs. Fatima Bukar Kyari"),
    ("BICTDA-FAC-003", "Dr. Musa Ibrahim Kolo"),
    ("BICTDA-FAC-004", "Mal. Yakubu Ali Gana"),
    ("BICTDA-FAC-005", "Hajiya Aisha Umar Bulama"),
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


# Demo facilitator accounts (already signed up). BICTDA-FAC-003 to 005 are left free to test sign-up.
#   teaches: course numbers (sequence_order) this facilitator offers
FACILITATORS = [
    {"facilitator_id": "BICTDA-FAC-001", "phone": "08031110001",
     "specialization": "Data Science & Machine Learning", "teaches": [2, 3]},
    {"facilitator_id": "BICTDA-FAC-002", "phone": "08031110002",
     "specialization": "Web Development & Cybersecurity", "teaches": [1, 4]},
]

# scenario: what has happened to this intern so far
#   "passed_c1" -> passed Course 1, now on Course 2
#   "failed_c1" -> scored 45% in Course 1 (below the 50% pass mark), retake required
#   "on_c1"     -> currently on Course 1
INTERNS = [
    {"programme": "SIWES", "full_name": "Aisha Mohammed Goni", "email": "aisha.goni@student.test",
     "phone": "08031234501", "institution": "University of Maiduguri", "department": DEPT_SOFTWARE_DATA,
     "days_ago": 42, "scenario": "passed_c1", "attendance": "perfect"},
    {"programme": "SIWES", "full_name": "Umar Ali Bukar", "email": "umar.bukar@student.test",
     "phone": "08031234502", "institution": "Ramat Polytechnic, Maiduguri", "department": DEPT_CYBERSECURITY,
     "days_ago": 35, "scenario": "failed_c1", "attendance": "weak"},
    {"programme": "SIWES", "full_name": "Hauwa Ibrahim Shettima", "email": "hauwa.shettima@student.test",
     "phone": "08031234503", "institution": "Borno State University", "department": DEPT_CYBERSECURITY,
     "days_ago": 14, "scenario": "on_c1", "attendance": "good"},
    {"programme": "NYSC", "full_name": "Chinedu Emmanuel Okafor", "email": "chinedu.okafor@corps.test",
     "phone": "08031234504", "institution": "PPA: BICTDA Headquarters, Maiduguri", "department": DEPT_SOFTWARE_DATA,
     "days_ago": 21, "scenario": "on_c1", "attendance": "good"},
    {"programme": "NYSC", "full_name": "Zainab Musa Lawan", "email": "zainab.lawan@corps.test",
     "phone": "08031234505", "institution": "PPA: BICTDA Headquarters, Maiduguri", "department": DEPT_CYBERSECURITY,
     "days_ago": 14, "scenario": "on_c1", "attendance": "excellent"},
]

# Probability of (Punctual, Late, Absent) for each attendance profile
ATTENDANCE_PROFILES = {
    "perfect": (1.00, 0.00, 0.00),
    "excellent": (0.90, 0.10, 0.00),
    "good": (0.75, 0.15, 0.10),
    "weak": (0.50, 0.25, 0.25),
}

# Assignments: course number -> [(title, instructions, due in N days, max score)]
# Negative days = due date already passed.
ASSIGNMENTS = {
    1: [
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
    2: [
        ("Python Basics: Cleaning Rainfall Data",
         "Using Python lists and dictionaries, clean the sample Borno monthly rainfall data "
         "(remove blanks, fix units) and print the average for each year.", -4, 25),
        ("Exploratory Data Analysis with Pandas",
         "Load the provided CSV into Pandas, describe the data, find missing values and "
         "create two charts with Matplotlib. Submit a Google Colab or GitHub link.", 6, 25),
    ],
    3: [
        ("Linear Regression: Predicting Crop Yield",
         "Train a linear regression model with scikit-learn on the crop yield dataset, "
         "report the R-squared score and explain your results in 200 words.", 60, 50),
    ],
    4: [
        ("Network Security Audit Report",
         "Perform a basic security audit of a home or office network (password policy, "
         "router settings, open ports) and write a 2-page report with recommendations.", 100, 50),
    ],
}

# Demo submissions: (intern email, course number, assignment index,
#                    submitted N days ago, score or None, feedback)
SUBMISSIONS = [
    ("aisha.goni@student.test", 1, 0, 20, 18, "Excellent use of semantic tags."),
    ("aisha.goni@student.test", 1, 1, 17, 17, "Clean, responsive layout."),
    ("aisha.goni@student.test", 1, 2, 16, 26, "Great validation messages."),
    ("aisha.goni@student.test", 2, 0, 5, 22, "Good data cleaning steps."),
    ("aisha.goni@student.test", 2, 1, 1, None, None),
    ("umar.bukar@student.test", 1, 0, 16, 9, "Incomplete - footer and contact section missing."),
    ("umar.bukar@student.test", 1, 1, 9, None, None),
    ("hauwa.shettima@student.test", 1, 0, 10, 15, "Good work, submitted late."),
    ("hauwa.shettima@student.test", 1, 1, 9, None, None),
    ("chinedu.okafor@corps.test", 1, 0, 19, 17, "Well structured page."),
    ("chinedu.okafor@corps.test", 1, 1, 1, None, None),
    ("zainab.lawan@corps.test", 1, 0, 11, None, None),
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


def _seed_attendance(intern, progress, profile, rng):
    """Mark weekday attendance from the course start until yesterday (or the course end)."""
    yesterday = today_wat() - timedelta(days=1)
    last_class_day = min(progress.end_date - timedelta(days=1), yesterday)
    weights = ATTENDANCE_PROFILES[profile]
    for day in _weekdays(progress.start_date, last_class_day):
        status = rng.choices([ATT_PUNCTUAL, ATT_LATE, ATT_ABSENT], weights=weights)[0]
        mark_attendance(intern, progress.course, day, status,
                        marked_by=progress.course.facilitator, commit=False)


def _at(day, hour=10, minute=0):
    return datetime.combine(day, time(hour, minute))


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------
def seed_reference_data():
    """
    Programmes, the course track and the issued Facilitator IDs. The LMS needs these even
    without demo data (e.g. sign-up must list SIWES/NYSC and the courses). Safe to run on every start.
    """
    if Programme.query.first() is None:
        for p in PROGRAMMES:
            db.session.add(Programme(code=p["code"], name=p["name"],
                                     description=p["description"], badge_color=p["badge_color"]))
    if Course.query.first() is None:
        seed_courses()
    db.session.commit()
    seed_issued_ids()


def seed_database(verbose=True):
    """Seed demo users ONLY if the database has no users. Returns True if it seeded."""
    seed_reference_data()
    if User.query.first() is not None:
        if verbose:
            print("[seed] Database already has data - seeding skipped.")
        return False

    today = today_wat()

    # 1. Programmes and the shared course track (created by seed_reference_data)
    programmes = {p.code: p for p in Programme.query.all()}
    courses = {c.sequence_order: c for c in Course.query.all()}

    # 2. Facilitators - signed up through the same function as the Sign Up page
    for f in FACILITATORS:
        facilitator = register_facilitator(f["facilitator_id"], FACILITATOR_PASSWORD, FACILITATOR_PASSWORD,
                                           [courses[order].id for order in f["teaches"]], commit=False)
        facilitator.phone = normalize_phone(f["phone"])
        facilitator.specialization = f["specialization"]
    db.session.flush()

    # 3. Assignments (posted by each course's facilitator)
    assignments = {}
    for order, items in ASSIGNMENTS.items():
        course = courses[order]
        for index, (title, instructions, due_in_days, max_score) in enumerate(items):
            assignment = Assignment(course=course, title=title, instructions=instructions,
                                    due_date=_at(today + timedelta(days=due_in_days), 23, 59),
                                    max_score=max_score, created_by=course.facilitator,
                                    created_at=_at(today + timedelta(days=due_in_days - 10)))
            db.session.add(assignment)
            assignments[(order, index)] = assignment
    db.session.flush()

    # 4. Interns, enrollment, attendance and course results
    interns = {}
    for i in INTERNS:
        programme = programmes[i["programme"]]
        start = today - timedelta(days=i["days_ago"])

        intern = User(role=ROLE_INTERN, full_name=i["full_name"], email=i["email"].lower(),
                      phone=normalize_phone(i["phone"]), intern_id=generate_intern_id(programme.code),
                      programme=programme, institution=i["institution"], department=i["department"],
                      enrollment_date=start)
        intern.set_password(INTERN_PASSWORD)
        db.session.add(intern)
        db.session.flush()

        progress = enroll_intern(intern, start_date=start, commit=False)
        rng = random.Random(2026 + intern.id)   # fixed seed -> same demo data every time
        course1 = progress[0]
        _seed_attendance(intern, course1, i["attendance"], rng)

        if i["scenario"] == "passed_c1":
            # Passed Course 1 with 78% at the end of the month -> Course 2 unlocks automatically
            record_final_result(course1, 78, graded_by=course1.course.facilitator,
                                effective_date=course1.end_date, commit=False)
            _seed_attendance(intern, progress[1], "excellent", rng)
        elif i["scenario"] == "failed_c1":
            # 45% is below the pass mark -> FAIL, Course 2 stays locked
            record_final_result(course1, 45, graded_by=course1.course.facilitator,
                                effective_date=course1.end_date, commit=False)

        create_notification(intern, f"Welcome to the BICTDA {programme.code} Internship Portal, "
                                    f"{intern.full_name.split()[0]}!",
                            icon="fa-solid fa-hand-sparkles", commit=False)
        interns[intern.email] = intern

    # 5. Submissions and grades
    for email, order, index, days_ago, score, feedback in SUBMISSIONS:
        intern = interns[email]
        assignment = assignments[(order, index)]
        submitted_at = _at(today - timedelta(days=days_ago), 14, 30)
        submission = Submission(assignment=assignment, intern=intern,
                                response_text=f"My submission for '{assignment.title}'. "
                                              f"Please see the link for the full work.",
                                link_url=f"https://github.com/example/{intern.intern_id.lower()}-task{index + 1}",
                                submitted_at=submitted_at, updated_at=submitted_at,
                                is_late=submitted_at > assignment.due_date)
        db.session.add(submission)
        if score is not None:
            grade_submission(submission, score, feedback, graded_by=assignment.course.facilitator, commit=False)

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
    used = {u.facilitator_id for u in User.query.filter(User.facilitator_id.isnot(None))}
    free = [fid for fid, _ in ISSUED_FACILITATOR_IDS if fid not in used]
    print(f" Free Facilitator IDs for testing Sign Up: {', '.join(free) or 'none'}")
    print(line)
    print(" BUSINESS RULE CHECK")
    for user in User.query.filter_by(role=ROLE_INTERN).order_by(User.id).all():
        parts = []
        for p in user.ordered_progress:
            label = f"C{p.course.sequence_order}:{p.status_label}"
            if p.final_score is not None:
                label += f"({p.final_score:g}%)"
            parts.append(label)
        lengths = " + ".join(str(p.duration_weeks // COURSE_DURATION_WEEKS) for p in user.ordered_progress)
        total = sum(p.duration_weeks for p in user.ordered_progress) // COURSE_DURATION_WEEKS
        current = user.current_progress
        rate = calculate_attendance_rate(user.id, current.course_id) if current else 0
        print(f"  {user.intern_id:<18} {' | '.join(parts)}")
        print(f"  {'':<18} Track: {lengths} = {total} months")
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
