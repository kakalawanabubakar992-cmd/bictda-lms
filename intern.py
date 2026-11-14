"""
intern.py - Intern portal pages.

Dashboard, Profile, Attendance, Courses (sequential 6-month track), Assignments and My Results.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from decorators import intern_required
from extensions import db
from models import COURSE_DURATION_WEEKS, Assignment, Attendance
from services import (attendance_label, attendance_summary, attendance_trend, pending_attendance_days,
                      submit_assignment)
from utils import now_wat

intern_bp = Blueprint("intern", __name__)


def _with_submissions(course, user):
    """[(assignment, this intern's submission or None), ...] for one course."""
    return [(a, a.submission_for(user)) for a in course.assignments]


def _attendance_data(progress):
    """Attendance figures for one course, shared by the Dashboard and Attendance pages."""
    if progress is None:
        return {"text": "No records", "label": attendance_label(None), "summary": None, "labels": [], "values": []}
    labels, values = attendance_trend(progress.intern_id, progress.course_id)
    pending = len(pending_attendance_days(progress))
    return {
        "text": progress.attendance_text,
        "label": attendance_label(progress.live_attendance_rate)
                 + (f" · {pending} training day{'s' if pending != 1 else ''} not yet marked" if pending else ""),
        "summary": attendance_summary(progress.intern_id, progress.course_id),
        "labels": labels,
        "values": values,
    }


@intern_bp.route("/dashboard")
@intern_required
def dashboard():
    user = current_user
    progress = user.current_progress          # None when every course is passed
    course = progress.course if progress else None

    # Assignments for the current course
    assignments = course.assignments if course else []
    submitted = sum(1 for a in assignments if a.submission_for(user))
    now = now_wat()
    upcoming = [(a, a.submission_for(user)) for a in assignments if a.due_date >= now][:5]

    # Average score (%) across all graded assignments
    graded = [s.percent for s in user.submissions if s.is_graded]
    average_score = round(sum(graded) / len(graded), 1) if graded else None

    # Course overview doughnut: completed / current / locked
    ordered = user.ordered_progress
    overview = [
        sum(1 for p in ordered if p.is_passed),
        sum(1 for p in ordered if p.is_current),
        sum(1 for p in ordered if p.is_locked),
    ]

    return render_template(
        "intern/dashboard.html",
        title="Dashboard",
        progress=progress,
        course=course,
        attendance=_attendance_data(progress),
        submitted=submitted,
        total_assignments=len(assignments),
        upcoming=upcoming,
        average_score=average_score,
        overview=overview,
    )


@intern_bp.route("/profile")
@intern_required
def profile():
    return render_template("intern/profile.html", title="My Profile")


@intern_bp.route("/attendance")
@intern_required
def attendance():
    user = current_user
    unlocked = [p for p in user.ordered_progress if not p.is_locked]

    # Selected course: ?course=<id>, otherwise the current course, otherwise the last one started
    requested = request.args.get("course", type=int)
    selected = next((p for p in unlocked if p.course_id == requested), None)
    selected = selected or user.current_progress or (unlocked[-1] if unlocked else None)

    records = []
    if selected:
        records = (Attendance.query.filter_by(intern_id=user.id, course_id=selected.course_id)
                   .order_by(Attendance.date.desc()).all())

    return render_template(
        "intern/attendance.html",
        title="Attendance",
        unlocked=unlocked,
        selected=selected,
        records=records,
        attendance=_attendance_data(selected),
    )


@intern_bp.route("/courses")
@intern_required
def courses():
    track = current_user.ordered_progress   # Course 1 -> 4, each with its status
    total_months = sum(p.duration_weeks for p in track) // COURSE_DURATION_WEEKS
    return render_template("intern/courses.html", title="My Courses", track=track, total_months=total_months)


@intern_bp.route("/results")
@intern_bp.route("/results/<int:progress_id>")
@intern_required
def results(progress_id=None):
    """My Results: graded courses only. With progress_id: the printable Certificate of Completion of a PASSED course."""
    graded = [p for p in current_user.ordered_progress if p.is_completed]
    if progress_id is None:
        return render_template("intern/results.html", title="My Results", graded=graded, slip=None)
    # Only this intern's own passed courses - anything else is "not found"
    slip = next((p for p in graded if p.id == progress_id and p.is_passed), None) or abort(404)
    return render_template("intern/results.html", title=f"Certificate - {slip.course.title}", graded=graded, slip=slip)


@intern_bp.route("/assignments")
@intern_required
def assignments():
    user = current_user
    current = user.current_progress
    items = _with_submissions(current.course, user) if current else []
    history = [(p.course, _with_submissions(p.course, user)) for p in user.ordered_progress if p.is_passed]

    graded = [s.percent for _, s in items if s and s.is_graded]
    stats = {
        "total": len(items),
        "submitted": sum(1 for _, s in items if s),
        "graded": len(graded),
        "average": round(sum(graded) / len(graded), 1) if graded else None,
    }
    return render_template("intern/assignments.html", title="Assignments", current=current,
                           items=items, history=history, stats=stats)


@intern_bp.route("/assignments/<int:assignment_id>/submit", methods=["POST"])
@intern_required
def submit(assignment_id):
    """Create or update a submission. All rules live in services.submit_assignment."""
    assignment = db.session.get(Assignment, assignment_id) or abort(404)
    try:
        submission = submit_assignment(current_user, assignment, request.form.get("response_text"),
                                       request.form.get("link_url"), request.files.get("file"))
        if submission.is_late:
            flash("Submission saved, but it was after the due date (marked Late).", "warning")
        else:
            flash("Assignment submitted successfully.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("intern.assignments", _anchor=f"assignment-{assignment_id}"))
