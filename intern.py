"""
intern.py - Intern portal pages.

PHASE 3: Dashboard, Profile and Attendance are built.
Courses shows the sequential 6-month track. Assignments is still a placeholder (Phase 4).
"""
from flask import Blueprint, render_template, request
from flask_login import current_user

from decorators import intern_required
from models import COURSE_DURATION_WEEKS, Attendance
from services import attendance_label, attendance_summary, attendance_trend
from utils import now_wat

intern_bp = Blueprint("intern", __name__)


def _placeholder(title, phase, icon, description):
    return render_template("placeholder.html", title=title, phase=phase,
                           icon=icon, description=description)


def _attendance_data(progress):
    """Attendance figures for one course, shared by the Dashboard and Attendance pages."""
    if progress is None:
        return {"rate": 0.0, "label": attendance_label(None), "summary": None, "labels": [], "values": []}
    labels, values = attendance_trend(progress.intern_id, progress.course_id)
    rate = progress.live_attendance_rate
    return {
        "rate": rate,
        "label": attendance_label(rate) if values else attendance_label(None),
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


@intern_bp.route("/assignments")
@intern_required
def assignments():
    return _placeholder("Assignments", 4, "fa-solid fa-file-pen",
                        "View, submit and track your graded assignments.")
