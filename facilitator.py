"""
facilitator.py - Facilitator portal pages.

PHASE 2 VERSION: placeholders so the sidebar links work and you can test
sign-in. Phase 5 replaces this whole file.
"""
from flask import Blueprint, render_template

from decorators import facilitator_required

facilitator_bp = Blueprint("facilitator", __name__, url_prefix="/facilitator")


def _placeholder(title, icon, description):
    return render_template("placeholder.html", title=title, phase=5,
                           icon=icon, description=description)


@facilitator_bp.route("/dashboard")
@facilitator_required
def dashboard():
    return _placeholder("Facilitator Dashboard", "fa-solid fa-gauge-high",
                        "Intern totals, today's attendance, pending grading and course progress chart.")


@facilitator_bp.route("/attendance")
@facilitator_required
def attendance():
    return _placeholder("Mark Attendance", "fa-solid fa-user-check",
                        "Mark interns Punctual (100%), Late (50%) or Absent (0%).")


@facilitator_bp.route("/assignments")
@facilitator_required
def assignments():
    return _placeholder("Assignments", "fa-solid fa-file-pen",
                        "Post new assignments with instructions, due date and maximum score.")


@facilitator_bp.route("/grading")
@facilitator_required
def grading():
    return _placeholder("Grade Submissions", "fa-solid fa-clipboard-check",
                        "Review intern submissions, give scores and feedback.")


@facilitator_bp.route("/results")
@facilitator_required
def results():
    return _placeholder("Final Results", "fa-solid fa-award",
                        "Enter final course results - above 50% unlocks the next course.")


@facilitator_bp.route("/interns")
@facilitator_required
def interns():
    return _placeholder("Interns", "fa-solid fa-users",
                        "All interns with programme and course filters.")
