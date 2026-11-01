"""
intern.py - Intern portal pages.

PHASE 2 VERSION: every page shows a "coming soon" placeholder so the sidebar
links work and you can test sign-in. Phase 3 and Phase 4 replace this whole file.
"""
from flask import Blueprint, render_template

from decorators import intern_required

intern_bp = Blueprint("intern", __name__)


def _placeholder(title, phase, icon, description):
    return render_template("placeholder.html", title=title, phase=phase,
                           icon=icon, description=description)


@intern_bp.route("/dashboard")
@intern_required
def dashboard():
    return _placeholder("Dashboard", 3, "fa-solid fa-gauge-high",
                        "Metric cards, attendance trend chart and course overview.")


@intern_bp.route("/profile")
@intern_required
def profile():
    return _placeholder("My Profile", 3, "fa-solid fa-id-badge",
                        "Your BICTDA ID, programme badge, current course and enrollment status.")


@intern_bp.route("/attendance")
@intern_required
def attendance():
    return _placeholder("Attendance", 3, "fa-solid fa-calendar-check",
                        "Your punctuality log and attendance trend chart.")


@intern_bp.route("/courses")
@intern_required
def courses():
    return _placeholder("My Courses", 4, "fa-solid fa-layer-group",
                        "Locked, active and completed courses with final scores.")


@intern_bp.route("/assignments")
@intern_required
def assignments():
    return _placeholder("Assignments", 4, "fa-solid fa-file-pen",
                        "View, submit and track your graded assignments.")
