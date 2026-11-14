"""
facilitator.py - Facilitator portal.

    /facilitator/dashboard     metrics + course progress chart
    /facilitator/attendance    mark Punctual (100%) / Late (50%) / Absent (0%) for a course and date
    /facilitator/assignments   post assignments and see submission counts
    /facilitator/grading       grade intern submissions
    /facilitator/interns       intern list + final course results (a pass unlocks the next course)
    /facilitator/courses       change the courses this facilitator offers

A facilitator only sees and manages the courses they chose (current_user.taught_courses).
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
    ATT_NO_CLASS,
    ATT_PUNCTUAL,
    ATTENDANCE_CREDITS,
    ENROLL_PENDING,
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
    approve_intern,
    can_mark_attendance,
    current_progress_for,
    get_next_progress,
    grade_submission,
    mark_attendance,
    pending_attendance_days,
    post_assignment,
    record_final_result,
    set_facilitator_courses,
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
def _my_courses():
    """The courses this facilitator offers, Course 1 -> 4."""
    return current_user.taught_courses


def _my_course_ids():
    return [c.id for c in _my_courses()]


def _teaches_first_course():
    """New interns always start in the first course, so its facilitators approve new accounts."""
    first = Course.query.order_by(Course.sequence_order).first()
    return first is not None and first.id in _my_course_ids()


def _selected_course(courses):
    """Course from ?course=<id> if it is one of the facilitator's courses, otherwise their first course."""
    requested = request.values.get("course", type=int)
    return next((c for c in courses if c.id == requested), None) or (courses[0] if courses else None)


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
    courses = _my_courses()
    ids = _my_course_ids()
    rows = CourseProgress.query.filter(CourseProgress.course_id.in_(ids)).all()

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
                              .filter(Attendance.date == today_wat(), Attendance.course_id.in_(ids)).one())
    pending = (Submission.query.join(Submission.assignment).filter(Submission.score.is_(None), Assignment.course_id.in_(ids))
               .order_by(Submission.submitted_at).all())

    return render_template(
        "facilitator/dashboard.html",
        title="Facilitator Dashboard",
        all_courses=Course.query.order_by(Course.sequence_order).all(),
        course_counts=list(zip(courses, current)),
        today_rate=round(float(today_avg), 1) if today_count else None,
        today_count=today_count,
        pending=pending,
        chart=chart,
    )


@facilitator_bp.route("/courses", methods=["POST"])
@facilitator_required
def update_courses():
    """Change the courses this facilitator offers (at least one)."""
    try:
        set_facilitator_courses(current_user, request.form.getlist("courses"))
        flash("Your courses have been updated.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("facilitator.dashboard"))


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------
@facilitator_bp.route("/attendance", methods=["GET", "POST"])
@facilitator_required
def attendance():
    courses = _my_courses()
    course = _selected_course(courses)
    try:
        on_date = datetime.strptime(request.values.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        on_date = today_wat()
    rows = current_progress_for(course) if course else []

    if request.method == "POST":
        no_training = bool(request.form.get("no_training"))      # the "No training this day" button
        saved, errors = 0, []
        for progress in rows:
            status = ATT_NO_CLASS if no_training else request.form.get(f"status_{progress.intern_id}")
            if status not in ATTENDANCE_CREDITS and status != ATT_NO_CLASS:
                continue                                   # not marked - skip
            allowed, reason = can_mark_attendance(progress, on_date)
            if not allowed:
                errors.append(f"{progress.intern.full_name}: {reason}")
                continue
            mark_attendance(progress.intern, course, on_date, status, marked_by=current_user, commit=False)
            saved += 1
        db.session.commit()
        if saved:
            what = "'No training' recorded" if no_training else "Attendance saved"
            flash(f"{what} for {saved} intern{'s' if saved != 1 else ''} on {on_date:%d %b %Y}.", "success")
        for error in errors:
            flash(error, "error")
        if not saved and not errors:
            flash("Choose Punctual, Late or Absent for at least one intern.", "warning")
        return redirect(url_for("facilitator.attendance", course=course.id, date=on_date.isoformat()))

    marked = {}
    if course:
        marked = {a.intern_id: a.status for a in Attendance.query.filter_by(course_id=course.id, date=on_date)}
    pending = sorted({day for progress in rows for day in pending_attendance_days(progress)})
    return render_template("facilitator/attendance.html", title="Mark Attendance", courses=courses,
                           course=course, on_date=on_date, rows=rows, marked=marked, options=ATTENDANCE_OPTIONS,
                           pending=pending, no_class=ATT_NO_CLASS)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------
@facilitator_bp.route("/assignments", methods=["GET", "POST"])
@facilitator_required
def assignments():
    courses = _my_courses()
    if request.method == "POST":
        course = _selected_course(courses) if request.form.get("course", type=int) in _my_course_ids() else None
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

    query = Submission.query.join(Submission.assignment).filter(Assignment.course_id.in_(_my_course_ids()))
    if assignment_id:
        query = query.filter(Submission.assignment_id == assignment_id)
    elif course_id:
        query = query.filter(Assignment.course_id == course_id)
    if status == "pending":
        query = query.filter(Submission.score.is_(None))
    elif status == "graded":
        query = query.filter(Submission.score.isnot(None))

    return render_template("facilitator/grading.html", title="Grade Submissions", courses=_my_courses(),
                           submissions=query.order_by(Submission.submitted_at).all(),
                           course_id=course_id, assignment_id=assignment_id, status=status)


@facilitator_bp.route("/grading/<int:submission_id>", methods=["POST"])
@facilitator_required
def grade(submission_id):
    submission = db.session.get(Submission, submission_id) or abort(404)
    if submission.assignment.course_id not in _my_course_ids():
        abort(404)                                    # not one of this facilitator's courses
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
    status = request.args.get("status", "")          # active / retake
    search = request.args.get("q", "").strip()

    query = User.query.filter_by(role=ROLE_INTERN)
    if programme:
        query = query.join(Programme).filter(Programme.code == programme)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.full_name.ilike(like), User.intern_id.ilike(like), User.email.ilike(like)))

    my_ids = _my_course_ids()
    rows = []
    for intern in query.order_by(User.intern_id).all():
        progress = intern.current_progress            # only interns currently in one of my courses
        if progress is None or progress.course_id not in my_ids or (course_id and progress.course_id != course_id):
            continue
        if (status == "active" and not progress.is_active) or (status == "retake" and not progress.is_failed):
            continue
        next_progress = get_next_progress(progress)
        rows.append({
            "intern": intern,
            "progress": progress,
            "average": _average_score(intern, progress.course),
            "next_course": next_progress.course if next_progress else None,
        })

    pending_interns = []                              # new accounts waiting for approval
    if _teaches_first_course():
        pending_interns = (User.query.filter_by(role=ROLE_INTERN, enrollment_status=ENROLL_PENDING)
                           .order_by(User.created_at).all())

    return render_template("facilitator/interns.html", title="Interns & Results", rows=rows,
                           pending_interns=pending_interns,
                           programmes=Programme.query.order_by(Programme.id).all(), courses=_my_courses(),
                           filters={"programme": programme, "course": course_id, "status": status, "q": search})


@facilitator_bp.route("/interns/<int:intern_id>/approve", methods=["POST"])
@facilitator_required
def approve(intern_id):
    """Approve or decline a new intern account. Only facilitators of the first course may do this."""
    intern = db.session.get(User, intern_id)
    if intern is None or not intern.is_intern or not _teaches_first_course():
        abort(404)
    try:
        approved = request.form.get("decision") == "approve"
        approve_intern(intern, approved)
        if approved:
            flash(f"{intern.full_name} ({intern.intern_id}) is approved and can now sign in.", "success")
        else:
            flash(f"{intern.full_name}'s account was declined and cannot be used.", "warning")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("facilitator.interns"))


@facilitator_bp.route("/results/<int:progress_id>", methods=["POST"])
@facilitator_required
def save_result(progress_id):
    """Save a final course result. services.record_final_result applies the pass mark and unlocks the next course."""
    progress = db.session.get(CourseProgress, progress_id) or abort(404)
    if progress.course_id not in _my_course_ids():
        abort(404)                                    # not one of this facilitator's courses
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
