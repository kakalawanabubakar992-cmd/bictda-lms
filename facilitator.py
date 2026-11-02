"""
facilitator.py - Facilitator portal.

    /facilitator/dashboard     metrics + course progress chart
    /facilitator/attendance    mark Punctual (100%) / Late (50%) / Absent (0%) for a course and date
    /facilitator/assignments   post assignments and see submission counts
    /facilitator/grading       grade intern submissions
    /facilitator/interns       intern list + final course results (a pass unlocks the next course)

Every facilitator can manage every course; their own courses are pre-selected.
All business rules live in services.py - these routes only collect input and show results.
"""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from auth import safe_next_url
from decorators import facilitator_required
from extensions import db
from models import (
    ATT_ABSENT,
    ATT_LATE,
    ATT_PUNCTUAL,
    ATTENDANCE_CREDITS,
    ROLE_INTERN,
    STATUS_ACTIVE,
    STATUS_FAILED,
    STATUS_LOCKED,
    STATUS_PASSED,
    Assignment,
    Attendance,
    Course,
    CourseProgress,
    Programme,
    Submission,
    User,
)
from services import (
    can_mark_attendance,
    current_progress_for,
    get_next_progress,
    grade_submission,
    mark_attendance,
    post_assignment,
    record_final_result,
)
from utils import today_wat

facilitator_bp = Blueprint("facilitator", __name__, url_prefix="/facilitator")

# (status, label, credit, colour) for the attendance radio buttons
ATTENDANCE_OPTIONS = [
    (ATT_PUNCTUAL, "Punctual", ATTENDANCE_CREDITS[ATT_PUNCTUAL], "emerald"),
    (ATT_LATE, "Late", ATTENDANCE_CREDITS[ATT_LATE], "amber"),
    (ATT_ABSENT, "Absent", ATTENDANCE_CREDITS[ATT_ABSENT], "rose"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _all_courses():
    return Course.query.order_by(Course.sequence_order).all()


def _selected_course(courses):
    """Course from ?course=<id>, otherwise the facilitator's own first course, otherwise Course 1."""
    requested = request.values.get("course", type=int)
    mine = [c for c in courses if c.facilitator_id == current_user.id]
    return next((c for c in courses if c.id == requested), None) or (mine or courses or [None])[0]


def _average_score(intern, course):
    """Average % of an intern's graded assignments in one course (None if nothing graded)."""
    graded = [s.percent for s in intern.submissions if s.is_graded and s.assignment.course_id == course.id]
    return round(sum(graded) / len(graded), 1) if graded else None


def _back(default_endpoint, **values):
    """Return to the page (with its filters) that submitted the form."""
    return redirect(safe_next_url(request.form.get("next")) or url_for(default_endpoint, **values))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@facilitator_bp.route("/dashboard")
@facilitator_required
def dashboard():
    courses = _all_courses()
    rows = CourseProgress.query.all()

    def count(course, statuses):
        return sum(1 for p in rows if p.course_id == course.id and p.status in statuses)

    current = [count(c, (STATUS_ACTIVE, STATUS_FAILED)) for c in courses]
    chart = {
        "labels": [c.title for c in courses],
        "series": [
            {"label": "Passed", "values": [count(c, (STATUS_PASSED,)) for c in courses]},
            {"label": "Current", "values": current},
            {"label": "Locked", "values": [count(c, (STATUS_LOCKED,)) for c in courses]},
        ],
    }
    today_avg, today_count = (db.session.query(func.avg(Attendance.credit), func.count(Attendance.id))
                              .filter(Attendance.date == today_wat()).one())
    pending = Submission.query.filter(Submission.score.is_(None)).order_by(Submission.submitted_at).all()

    return render_template(
        "facilitator/dashboard.html",
        title="Facilitator Dashboard",
        total_interns=User.query.filter_by(role=ROLE_INTERN).count(),
        course_counts=list(zip(courses, current)),
        today_rate=round(float(today_avg), 1) if today_count else None,
        today_count=today_count,
        pending=pending,
        chart=chart,
    )


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
@facilitator_bp.route("/attendance", methods=["GET", "POST"])
@facilitator_required
def attendance():
    courses = _all_courses()
    course = _selected_course(courses)
    try:
        on_date = datetime.strptime(request.values.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        on_date = today_wat()
    rows = current_progress_for(course) if course else []

    if request.method == "POST":
        saved, errors = 0, []
        for progress in rows:
            status = request.form.get(f"status_{progress.intern_id}")
            if status not in ATTENDANCE_CREDITS:
                continue                                   # not marked - skip
            allowed, reason = can_mark_attendance(progress, on_date)
            if not allowed:
                errors.append(f"{progress.intern.full_name}: {reason}")
                continue
            mark_attendance(progress.intern, course, on_date, status, marked_by=current_user, commit=False)
            saved += 1
        db.session.commit()
        if saved:
            flash(f"Attendance saved for {saved} intern{'s' if saved != 1 else ''} on {on_date:%d %b %Y}.", "success")
        for error in errors:
            flash(error, "error")
        if not saved and not errors:
            flash("Choose Punctual, Late or Absent for at least one intern.", "warning")
        return redirect(url_for("facilitator.attendance", course=course.id, date=on_date.isoformat()))

    marked = {}
    if course:
        marked = {a.intern_id: a.status for a in Attendance.query.filter_by(course_id=course.id, date=on_date)}
    return render_template("facilitator/attendance.html", title="Mark Attendance", courses=courses,
                           course=course, on_date=on_date, rows=rows, marked=marked, options=ATTENDANCE_OPTIONS)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------
@facilitator_bp.route("/assignments", methods=["GET", "POST"])
@facilitator_required
def assignments():
    courses = _all_courses()
    if request.method == "POST":
        course = db.session.get(Course, request.form.get("course", type=int) or 0)
        try:
            post_assignment(course, request.form.get("title"), request.form.get("instructions"),
                            request.form.get("due_date"), request.form.get("max_score"), created_by=current_user)
            flash("Assignment posted. Interns in this course have been notified.", "success")
            return redirect(url_for("facilitator.assignments", course=course.id))
        except ValueError as error:
            flash(str(error), "error")      # show the form again with what was typed
    course = _selected_course(courses)
    return render_template("facilitator/assignments.html", title="Assignments", courses=courses,
                           course=course, form=request.form)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
@facilitator_bp.route("/grading")
@facilitator_required
def grading():
    course_id = request.args.get("course", type=int)
    assignment_id = request.args.get("assignment", type=int)
    status = request.args.get("status", "pending")

    query = Submission.query.join(Submission.assignment)
    if assignment_id:
        query = query.filter(Submission.assignment_id == assignment_id)
    elif course_id:
        query = query.filter(Assignment.course_id == course_id)
    if status == "pending":
        query = query.filter(Submission.score.is_(None))
    elif status == "graded":
        query = query.filter(Submission.score.isnot(None))

    return render_template("facilitator/grading.html", title="Grade Submissions", courses=_all_courses(),
                           submissions=query.order_by(Submission.submitted_at).all(),
                           course_id=course_id, assignment_id=assignment_id, status=status)


@facilitator_bp.route("/grading/<int:submission_id>", methods=["POST"])
@facilitator_required
def grade(submission_id):
    submission = db.session.get(Submission, submission_id) or abort(404)
    try:
        grade_submission(submission, request.form.get("score"), request.form.get("feedback"), graded_by=current_user)
        flash(f"Grade saved for {submission.intern.full_name}.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return _back("facilitator.grading")


# ---------------------------------------------------------------------------
# Interns & final results
# ---------------------------------------------------------------------------
@facilitator_bp.route("/interns")
@facilitator_required
def interns():
    programme = request.args.get("programme", "")
    course_id = request.args.get("course", type=int)
    status = request.args.get("status", "")          # active / retake / completed
    search = request.args.get("q", "").strip()

    query = User.query.filter_by(role=ROLE_INTERN)
    if programme:
        query = query.join(Programme).filter(Programme.code == programme)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(like), User.intern_id.ilike(like), User.email.ilike(like)))

    rows = []
    for intern in query.order_by(User.intern_id).all():
        progress = intern.current_progress
        if course_id and (progress is None or progress.course_id != course_id):
            continue
        if (status == "active" and not (progress and progress.is_active)) or \
           (status == "retake" and not (progress and progress.is_failed)) or \
           (status == "completed" and progress is not None):
            continue
        next_progress = get_next_progress(progress) if progress else None
        rows.append({
            "intern": intern,
            "progress": progress,
            "average": _average_score(intern, progress.course) if progress else None,
            "next_course": next_progress.course if next_progress else None,
        })

    return render_template("facilitator/interns.html", title="Interns & Results", rows=rows,
                           programmes=Programme.query.order_by(Programme.id).all(), courses=_all_courses(),
                           filters={"programme": programme, "course": course_id, "status": status, "q": search})


@facilitator_bp.route("/results/<int:progress_id>", methods=["POST"])
@facilitator_required
def save_result(progress_id):
    """Save a final course result. services.record_final_result applies the pass mark and unlocks the next course."""
    progress = db.session.get(CourseProgress, progress_id) or abort(404)
    try:
        outcome = record_final_result(progress, request.form.get("score"), graded_by=current_user)
        name, course = progress.intern.full_name, progress.course.title
        if not outcome["passed"]:
            flash(f"{name} scored {progress.final_score:g}% in {course} - below the pass mark, retake required.", "warning")
        elif outcome["unlocked_course"]:
            flash(f"{name} passed {course} ({progress.final_score:g}%). "
                  f"{outcome['unlocked_course'].title} is now unlocked.", "success")
        else:
            done = " All courses completed!" if progress.intern.current_progress is None else ""
            flash(f"{name} passed {course} ({progress.final_score:g}%).{done}", "success")
    except ValueError as error:
        flash(str(error), "error")
    return _back("facilitator.interns")
