"""
services.py - Business logic for BICTDA LMS.

The important rules of the system are kept here, in plain functions, so they
are easy to test and to explain in the project report:

    1. calculate_attendance_rate()  - punctuality-weighted attendance %
    2. record_final_result()        - the ">50% unlocks the next course" rule
    3. mark_attendance()            - one record per intern per course per day
    4. submit_assignment() / grade_submission()
    5. ID generators                - BICTDA-SIWES-001, BICTDA-NYSC-001, BICTDA-FAC-001
"""
import re
from datetime import datetime, time, timedelta

from sqlalchemy import func

from extensions import db
from models import (
    ATTENDANCE_CREDITS,
    COURSE_DURATION_DAYS,
    ENROLL_ACTIVE,
    ENROLL_COMPLETED,
    PASS_MARK,
    STATUS_ACTIVE,
    STATUS_FAILED,
    STATUS_LOCKED,
    STATUS_PASSED,
    Attendance,
    CourseProgress,
    Notification,
    Submission,
    User,
)
from utils import now_wat, today_wat


# ===========================================================================
# 1. ATTENDANCE
# ===========================================================================
def calculate_attendance_rate(intern_id, course_id):
    """
    Punctuality-weighted attendance percentage for ONE course.

        Daily credit:  Punctual = 100,  Late = 50,  Absent = 0

        Attendance % = (sum of daily credits / number of class days marked)

    Example: 4 days marked -> Punctual, Punctual, Late, Absent
             (100 + 100 + 50 + 0) / 4 = 62.5%

    Returns 0.0 when no days have been marked yet.
    """
    total_credit, days_marked = (
        db.session.query(func.coalesce(func.sum(Attendance.credit), 0), func.count(Attendance.id))
        .filter(Attendance.intern_id == intern_id, Attendance.course_id == course_id)
        .one()
    )
    if not days_marked:
        return 0.0
    return round(float(total_credit) / days_marked, 1)


def attendance_label(rate):
    """Human-friendly label for an attendance percentage."""
    if rate is None:
        return "No Records"
    if rate >= 100:
        return "Perfect Attendance"
    if rate >= 75:
        return "Good"
    if rate >= 50:
        return "Fair"
    return "Poor"


def attendance_trend(intern_id, course_id):
    """
    Data for the Attendance Trend chart: the cumulative attendance %
    after each class day.  Returns (labels, values).
    """
    records = (
        Attendance.query.filter_by(intern_id=intern_id, course_id=course_id)
        .order_by(Attendance.date)
        .all()
    )
    labels, values = [], []
    running_total = 0
    for day_number, record in enumerate(records, start=1):
        running_total += record.credit
        labels.append(record.date.strftime("%d %b"))
        values.append(round(running_total / day_number, 1))
    return labels, values


def attendance_summary(intern_id, course_id):
    """Counts of punctual / late / absent days for one course."""
    rows = (
        db.session.query(Attendance.status, func.count(Attendance.id))
        .filter(Attendance.intern_id == intern_id, Attendance.course_id == course_id)
        .group_by(Attendance.status)
        .all()
    )
    summary = {status: 0 for status in ATTENDANCE_CREDITS}
    for status, count in rows:
        summary[status] = count
    summary["total"] = sum(summary[s] for s in ATTENDANCE_CREDITS)
    return summary


def can_mark_attendance(progress, on_date):
    """
    Check whether attendance may be marked for this intern's course on this date.
    Returns (True, "") or (False, "reason").
    """
    if progress is None or progress.is_locked or progress.is_passed:
        return False, "This course is not the intern's current course."
    if on_date > today_wat():
        return False, "You cannot mark attendance for a future date."
    if progress.start_date and on_date < progress.start_date:
        return False, "This date is before the intern started the course."
    # Active courses must stay inside the 4-week window.
    # Interns retaking a failed course may be marked after the window.
    if progress.is_active and progress.end_date and on_date > progress.end_date:
        return False, "This date is after the 1-month course period."
    return True, ""


def mark_attendance(intern, course, on_date, status, marked_by=None, commit=True):
    """
    Create or update ONE attendance record (intern + course + date).
    Marking the same day again UPDATES the record instead of duplicating it.
    """
    status = (status or "").upper()
    if status not in ATTENDANCE_CREDITS:
        raise ValueError("Attendance status must be PUNCTUAL, LATE or ABSENT.")

    record = Attendance.query.filter_by(
        intern_id=intern.id, course_id=course.id, date=on_date
    ).first()
    if record is None:
        record = Attendance(intern_id=intern.id, course_id=course.id, date=on_date)
        db.session.add(record)

    record.status = status
    record.credit = ATTENDANCE_CREDITS[status]
    record.marked_by_id = marked_by.id if marked_by else None
    record.marked_at = now_wat()

    if commit:
        db.session.commit()
    return record


# ===========================================================================
# 2. ENROLLMENT & THE >50% SEQUENTIAL UNLOCK RULE
# ===========================================================================
def enroll_intern(intern, start_date=None, commit=True):
    """
    Create one CourseProgress row for every course in the intern's programme:
        Course 1 -> ACTIVE (starts on the enrollment date, lasts 28 days)
        Course 2, 3, 4 -> LOCKED
    """
    if intern.progress_records:
        return intern.ordered_progress   # already enrolled

    start = start_date or intern.enrollment_date or today_wat()
    intern.enrollment_date = start
    intern.enrollment_status = ENROLL_ACTIVE

    for course in intern.programme.courses:   # already ordered by sequence_order
        progress = CourseProgress(intern=intern, course=course, status=STATUS_LOCKED)
        if course.sequence_order == 1:
            progress.status = STATUS_ACTIVE
            progress.start_date = start
            progress.end_date = start + timedelta(days=COURSE_DURATION_DAYS)
        db.session.add(progress)

    if commit:
        db.session.commit()
    return intern.ordered_progress


def get_next_progress(progress):
    """The intern's CourseProgress row for the next course in sequence (or None)."""
    next_order = progress.course.sequence_order + 1
    for other in progress.intern.progress_records:
        if other.course.sequence_order == next_order:
            return other
    return None


def is_passing_score(score):
    """THE PASS RULE: score must be STRICTLY GREATER than 50. Exactly 50 fails."""
    return score is not None and float(score) > PASS_MARK


def record_final_result(progress, score, graded_by=None, effective_date=None, commit=True):
    """
    Save a facilitator's Final Course Result and apply the sequential unlock rule.

    Steps:
      1. Validate the score (0-100). Locked courses cannot be graded.
      2. Save the score and a snapshot of the 1-month attendance rate.
      3. If score > 50:
            - this course becomes COMPLETED_PASSED
            - the NEXT course is automatically unlocked (ACTIVE, starts today, 28 days)
            - if this was the last course, the intern's enrollment becomes "Completed"
         If score <= 50 (including exactly 50):
            - this course becomes COMPLETED_FAILED ("Retake Required")
            - the next course stays LOCKED
            - if the next course had been unlocked by an earlier passing grade
              that is now lowered, it is LOCKED again
      4. Notify the intern.

    effective_date lets the seeder simulate results given in the past.
    Returns a dict: {"passed": bool, "unlocked_course": Course or None}
    """
    if progress.is_locked:
        raise ValueError("A locked course cannot be graded.")

    try:
        score = float(score)
    except (TypeError, ValueError):
        raise ValueError("The final score must be a number between 0 and 100.")
    if not 0 <= score <= 100:
        raise ValueError("The final score must be between 0 and 100.")

    intern = progress.intern
    course = progress.course
    next_progress = get_next_progress(progress)
    passed = is_passing_score(score)
    when = effective_date or today_wat()

    # Protect the sequence: do not fail a course whose next course is already finished.
    if not passed and next_progress is not None and next_progress.is_completed:
        raise ValueError(
            f"Cannot lower this result: {next_progress.course.title} has already been graded."
        )

    # Save result + attendance snapshot
    progress.final_score = round(score, 1)
    progress.attendance_rate = calculate_attendance_rate(intern.id, course.id)
    progress.completed_at = datetime.combine(when, time(16, 0)) if effective_date else now_wat()
    progress.graded_by_id = graded_by.id if graded_by else None

    unlocked_course = None

    if passed:
        progress.status = STATUS_PASSED

        if next_progress is None:
            # Last course passed -> whole programme completed
            intern.enrollment_status = ENROLL_COMPLETED
            create_notification(
                intern,
                f"Congratulations! You passed {course.title} ({score:g}%) and completed "
                f"your {intern.programme.code} programme.",
                icon="fa-solid fa-trophy",
                commit=False,
            )
        else:
            if next_progress.is_locked:
                # >>> AUTOMATIC UNLOCK OF THE NEXT COURSE <<<
                next_progress.status = STATUS_ACTIVE
                next_progress.start_date = when
                next_progress.end_date = when + timedelta(days=COURSE_DURATION_DAYS)
                unlocked_course = next_progress.course
            create_notification(
                intern,
                f"You passed {course.title} with {score:g}%. "
                f"{next_progress.course.title} is now unlocked!",
                link="/courses",
                icon="fa-solid fa-unlock",
                commit=False,
            )
    else:
        progress.status = STATUS_FAILED

        if next_progress is not None and next_progress.is_active:
            # Grade was lowered after the next course was unlocked -> lock it again
            next_progress.status = STATUS_LOCKED
            next_progress.start_date = None
            next_progress.end_date = None
        if intern.enrollment_status == ENROLL_COMPLETED:
            intern.enrollment_status = ENROLL_ACTIVE

        create_notification(
            intern,
            f"Your final result for {course.title} is {score:g}%. A score above "
            f"{PASS_MARK}% is required to continue - retake required.",
            link="/courses",
            icon="fa-solid fa-rotate-right",
            commit=False,
        )

    if commit:
        db.session.commit()
    return {"passed": passed, "unlocked_course": unlocked_course}


# ===========================================================================
# 3. ASSIGNMENTS
# ===========================================================================
def submit_assignment(intern, assignment, response_text=None, link_url=None, commit=True):
    """
    Create or update an intern's submission.
      - Only allowed for the intern's CURRENT course (active or retake).
      - Cannot be edited after it has been graded.
      - Submissions after the due date are accepted but flagged as Late.
    """
    response_text = (response_text or "").strip()
    link_url = (link_url or "").strip()
    if not response_text and not link_url:
        raise ValueError("Please write a response or paste a link.")
    if link_url and not re.match(r"^https?://", link_url, re.IGNORECASE):
        raise ValueError("Links must start with http:// or https://")

    current = intern.current_progress
    if current is None or current.course_id != assignment.course_id:
        raise ValueError("You can only submit assignments for your current course.")

    submission = Submission.query.filter_by(
        assignment_id=assignment.id, intern_id=intern.id
    ).first()
    if submission and submission.is_graded:
        raise ValueError("This assignment has already been graded and can no longer be edited.")

    now = now_wat()
    if submission is None:
        submission = Submission(assignment_id=assignment.id, intern_id=intern.id, submitted_at=now)
        db.session.add(submission)

    submission.response_text = response_text or None
    submission.link_url = link_url or None
    submission.updated_at = now
    submission.is_late = now > assignment.due_date

    if commit:
        db.session.commit()
    return submission


def grade_submission(submission, score, feedback=None, graded_by=None, commit=True):
    """Save a facilitator's grade (0..max_score) and notify the intern."""
    max_score = submission.assignment.max_score
    try:
        score = float(score)
    except (TypeError, ValueError):
        raise ValueError(f"Score must be a number between 0 and {max_score}.")
    if not 0 <= score <= max_score:
        raise ValueError(f"Score must be between 0 and {max_score}.")

    submission.score = round(score, 1)
    submission.feedback = (feedback or "").strip() or None
    submission.graded_at = now_wat()
    submission.graded_by_id = graded_by.id if graded_by else None

    create_notification(
        submission.intern,
        f'"{submission.assignment.title}" was graded: {score:g}/{max_score}.',
        link="/assignments",
        icon="fa-solid fa-clipboard-check",
        commit=False,
    )
    if commit:
        db.session.commit()
    return submission


# ===========================================================================
# 4. ID GENERATORS
# ===========================================================================
def _next_number(column, prefix):
    """Find the highest existing number for a prefix, e.g. BICTDA-SIWES-007 -> 7."""
    existing = db.session.query(column).filter(column.like(f"{prefix}%")).all()
    highest = 0
    for (value,) in existing:
        match = re.search(r"(\d+)$", value or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def generate_intern_id(programme_code):
    """BICTDA-SIWES-001, BICTDA-SIWES-002, BICTDA-NYSC-001 ..."""
    prefix = f"BICTDA-{programme_code.upper()}-"
    return f"{prefix}{_next_number(User.intern_id, prefix):03d}"


def generate_facilitator_id():
    """BICTDA-FAC-001, BICTDA-FAC-002 ..."""
    prefix = "BICTDA-FAC-"
    return f"{prefix}{_next_number(User.facilitator_id, prefix):03d}"


# ===========================================================================
# 5. NOTIFICATIONS
# ===========================================================================
def create_notification(user, message, link=None, icon="fa-solid fa-bell", commit=True):
    notification = Notification(user=user, message=message[:300], link=link, icon=icon)
    db.session.add(notification)
    if commit:
        db.session.commit()
    return notification
