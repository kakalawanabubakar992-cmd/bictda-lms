"""
models.py - Database models (tables) for BICTDA LMS.

Tables:
    programmes        SIWES and NYSC
    users             Interns AND Facilitators (one table, separated by "role")
    issued_facilitator_ids  Facilitator IDs issued by BICTDA (needed to sign up as a facilitator)
    facilitator_courses     Which courses each facilitator offers (a course can have several)
    courses           4 sequential courses shared by SIWES and NYSC (6 months in total)
    course_progress   One row per intern per course (LOCKED / ACTIVE / PASSED / FAILED)
    attendance        Daily attendance with punctuality credit (100 / 50 / 0)
    assignments       Posted by facilitators for a course
    submissions       An intern's answer to an assignment, plus grade
    notifications     Messages shown under the bell icon
"""
from datetime import timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, login_manager
from utils import format_phone_display, now_wat, today_wat

# ---------------------------------------------------------------------------
# Constants (business rules live here so they are easy to find and explain)
# ---------------------------------------------------------------------------
ROLE_INTERN = "intern"
ROLE_FACILITATOR = "facilitator"

# Course progress status
STATUS_LOCKED = "LOCKED"
STATUS_ACTIVE = "ACTIVE"
STATUS_PASSED = "COMPLETED_PASSED"
STATUS_FAILED = "COMPLETED_FAILED"

# Enrollment status of an intern
ENROLL_ACTIVE = "Active"
ENROLL_COMPLETED = "Completed"
ENROLL_SUSPENDED = "Suspended"

# Attendance status -> daily attendance credit (%)
ATT_PUNCTUAL = "PUNCTUAL"
ATT_LATE = "LATE"
ATT_ABSENT = "ABSENT"
ATTENDANCE_CREDITS = {
    ATT_PUNCTUAL: 100,   # on time      -> full credit
    ATT_LATE: 50,        # late arrival -> half credit (punctuality penalty)
    ATT_ABSENT: 0,       # absent       -> no credit
}

# PASS MARK - the ONE place to change it. An intern passes a course when the
# final score is EQUAL TO OR GREATER than this value (so exactly 50% is a PASS).
PASS_MARK = 50

COURSE_DURATION_WEEKS = 4                          # 1 month = 4 weeks
COURSE_DURATION_DAYS = COURSE_DURATION_WEEKS * 7   # 28 days = 1 month

# Departments are profile information only: every intern follows the same course track.
DEPT_CYBERSECURITY = "Cybersecurity"
DEPT_SOFTWARE_DATA = "Software & Data"
DEPARTMENTS = [DEPT_SOFTWARE_DATA, DEPT_CYBERSECURITY]


def months_label(weeks):
    """4 -> '1 month', 8 -> '2 months'."""
    months = weeks // COURSE_DURATION_WEEKS
    return f"{months} month{'s' if months != 1 else ''}"


# Link table: facilitator <-> courses they offer (many-to-many)
facilitator_courses = db.Table(
    "facilitator_courses",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("course_id", db.Integer, db.ForeignKey("courses.id"), primary_key=True),
)


# ---------------------------------------------------------------------------
# Programme (SIWES / NYSC)
# ---------------------------------------------------------------------------
class Programme(db.Model):
    __tablename__ = "programmes"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)   # "SIWES" or "NYSC"
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    badge_color = db.Column(db.String(20), default="emerald")      # used by the UI

    interns = db.relationship("User", back_populates="programme")

    def __repr__(self):
        return f"<Programme {self.code}>"


# ---------------------------------------------------------------------------
# User (Intern or Facilitator)
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False, index=True)    # intern / facilitator
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, index=True)      # interns only (facilitators use their ID)
    phone = db.Column(db.String(20), unique=True, index=True)       # stored as +234...
    password_hash = db.Column(db.String(255), nullable=False)

    # Login IDs (only one of these is used, depending on role)
    intern_id = db.Column(db.String(30), unique=True, index=True)       # BICTDA-SIWES-001
    facilitator_id = db.Column(db.String(30), unique=True, index=True)  # BICTDA-FAC-001

    # Intern-only fields
    programme_id = db.Column(db.Integer, db.ForeignKey("programmes.id"))
    institution = db.Column(db.String(150))   # SIWES: school / NYSC: place of primary assignment
    department = db.Column(db.String(50), default=DEPT_SOFTWARE_DATA)   # profile info only
    enrollment_status = db.Column(db.String(20), default=ENROLL_ACTIVE)
    enrollment_date = db.Column(db.Date)

    # Facilitator-only field
    specialization = db.Column(db.String(150))

    created_at = db.Column(db.DateTime, default=now_wat)

    # Relationships
    programme = db.relationship("Programme", back_populates="interns")
    progress_records = db.relationship(
        "CourseProgress",
        back_populates="intern",
        foreign_keys="CourseProgress.intern_id",
        cascade="all, delete-orphan",
    )
    taught_courses = db.relationship(
        "Course", secondary=facilitator_courses, back_populates="facilitators", order_by="Course.sequence_order"
    )
    attendance_records = db.relationship(
        "Attendance",
        back_populates="intern",
        foreign_keys="Attendance.intern_id",
        cascade="all, delete-orphan",
    )
    submissions = db.relationship(
        "Submission",
        back_populates="intern",
        foreign_keys="Submission.intern_id",
        cascade="all, delete-orphan",
    )
    notifications = db.relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Notification.created_at.desc()",
    )

    # ----- Password helpers (Werkzeug hashing; plain passwords are never stored)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # ----- Role helpers
    @property
    def is_intern(self):
        return self.role == ROLE_INTERN

    @property
    def is_facilitator(self):
        return self.role == ROLE_FACILITATOR

    @property
    def login_id(self):
        """The BICTDA ID shown on screen: intern ID or facilitator ID."""
        return self.intern_id if self.is_intern else self.facilitator_id

    @property
    def initials(self):
        parts = [p for p in self.full_name.replace(".", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def phone_display(self):
        return format_phone_display(self.phone)

    # ----- Course progress helpers (interns)
    @property
    def ordered_progress(self):
        """All CourseProgress rows sorted Course 1 -> Course 4."""
        return sorted(self.progress_records, key=lambda p: p.course.sequence_order)

    @property
    def current_progress(self):
        """
        The course the intern is working on now:
          - the ACTIVE course, or
          - a FAILED course that must be retaken.
        Returns None when every course has been passed.
        """
        for progress in self.ordered_progress:
            if progress.status in (STATUS_ACTIVE, STATUS_FAILED):
                return progress
        return None

    @property
    def current_course(self):
        progress = self.current_progress
        return progress.course if progress else None

    @property
    def completed_courses_count(self):
        return sum(1 for p in self.progress_records if p.status == STATUS_PASSED)

    @property
    def total_courses_count(self):
        return len(self.progress_records)

    @property
    def unread_notifications_count(self):
        return sum(1 for n in self.notifications if not n.is_read)

    def __repr__(self):
        return f"<User {self.login_id} ({self.role})>"


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login calls this on every request to get the logged-in user."""
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Facilitator IDs issued by BICTDA (the admin adds them in seed.py -> ISSUED_FACILITATOR_IDS)
# ---------------------------------------------------------------------------
class IssuedFacilitatorID(db.Model):
    __tablename__ = "issued_facilitator_ids"

    id = db.Column(db.Integer, primary_key=True)
    facilitator_id = db.Column(db.String(30), unique=True, nullable=False)   # e.g. BICTDA-FAC-003
    full_name = db.Column(db.String(120))                                   # becomes the account name
    created_at = db.Column(db.DateTime, default=now_wat)

    def __repr__(self):
        return f"<IssuedFacilitatorID {self.facilitator_id}>"


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------
class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    sequence_order = db.Column(db.Integer, unique=True, nullable=False)  # 1, 2, 3, 4
    code = db.Column(db.String(20), unique=True, nullable=False)  # e.g. C1
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    duration_weeks = db.Column(db.Integer, default=COURSE_DURATION_WEEKS)  # expected length (1 month = 4 weeks)
    icon = db.Column(db.String(50), default="fa-solid fa-book-open")  # Font Awesome classes

    facilitators = db.relationship("User", secondary=facilitator_courses, back_populates="taught_courses")
    progress_records = db.relationship("CourseProgress", back_populates="course")
    assignments = db.relationship(
        "Assignment",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Assignment.due_date",
    )

    @property
    def facilitator(self):
        """The first facilitator offering this course (or None)."""
        return self.facilitators[0] if self.facilitators else None

    @property
    def order_label(self):
        return f"Course {self.sequence_order}"

    @property
    def length_label(self):
        """Expected duration, e.g. '1 month' or '2 months'."""
        return months_label(self.duration_weeks or COURSE_DURATION_WEEKS)

    def __repr__(self):
        return f"<Course {self.code}: {self.title}>"


# ---------------------------------------------------------------------------
# CourseProgress - one row per intern per course
# ---------------------------------------------------------------------------
class CourseProgress(db.Model):
    __tablename__ = "course_progress"
    __table_args__ = (
        db.UniqueConstraint("intern_id", "course_id", name="uq_progress_intern_course"),
    )

    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_LOCKED)

    start_date = db.Column(db.Date)        # set when the course becomes ACTIVE
    end_date = db.Column(db.Date)          # start_date + expected length (a target, not a lock)
    final_score = db.Column(db.Float)      # 0-100, entered by facilitator
    attendance_rate = db.Column(db.Float)  # course attendance % saved when the course is graded
    completed_at = db.Column(db.DateTime)
    graded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_at = db.Column(db.DateTime, default=now_wat, onupdate=now_wat)

    intern = db.relationship("User", back_populates="progress_records", foreign_keys=[intern_id])
    course = db.relationship("Course", back_populates="progress_records")
    graded_by = db.relationship("User", foreign_keys=[graded_by_id])

    # ----- Status helpers
    @property
    def is_locked(self):
        return self.status == STATUS_LOCKED

    @property
    def is_active(self):
        return self.status == STATUS_ACTIVE

    @property
    def is_passed(self):
        return self.status == STATUS_PASSED

    @property
    def is_failed(self):
        return self.status == STATUS_FAILED

    @property
    def is_completed(self):
        return self.status in (STATUS_PASSED, STATUS_FAILED)

    @property
    def is_current(self):
        """Active course, or failed course that needs a retake."""
        return self.status in (STATUS_ACTIVE, STATUS_FAILED)

    @property
    def status_label(self):
        return {
            STATUS_LOCKED: "Locked",
            STATUS_ACTIVE: "Active",
            STATUS_PASSED: "Passed",
            STATUS_FAILED: "Retake Required",
        }.get(self.status, self.status)

    # ----- Schedule helpers (expected course length - the same for every intern)
    @property
    def duration_weeks(self):
        return self.course.duration_weeks or COURSE_DURATION_WEEKS

    @property
    def duration_days(self):
        return self.duration_weeks * 7

    @property
    def length_label(self):
        return self.course.length_label

    @property
    def days_elapsed(self):
        if not self.start_date:
            return 0
        days = (today_wat() - self.start_date).days
        return max(0, min(days, self.duration_days))

    @property
    def time_progress_percent(self):
        """How far through the 4-week period we are (by days)."""
        if self.is_passed:
            return 100
        if not self.start_date:
            return 0
        return round(self.days_elapsed / self.duration_days * 100)

    @property
    def week_number(self):
        """Current week of the course (1-4 or 1-8)."""
        if not self.start_date:
            return 0
        return min(self.duration_weeks, self.days_elapsed // 7 + 1)

    @property
    def days_remaining(self):
        if not self.end_date:
            return 0
        return max(0, (self.end_date - today_wat()).days)

    # ----- Attendance helpers
    @property
    def live_attendance_rate(self):
        """Saved rate for graded courses; otherwise calculated live from attendance records."""
        if self.is_completed and self.attendance_rate is not None:
            return self.attendance_rate
        from services import calculate_attendance_rate   # imported here to avoid a circular import
        return calculate_attendance_rate(self.intern_id, self.course_id)

    @property
    def attendance_label(self):
        from services import attendance_label
        return attendance_label(self.live_attendance_rate)

    def __repr__(self):
        return f"<CourseProgress intern={self.intern_id} course={self.course_id} {self.status}>"


# ---------------------------------------------------------------------------
# Attendance - one row per intern per course per date
# ---------------------------------------------------------------------------
class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint("intern_id", "course_id", "date", name="uq_attendance_intern_course_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False)    # PUNCTUAL / LATE / ABSENT
    credit = db.Column(db.Integer, nullable=False)       # 100 / 50 / 0
    marked_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    marked_at = db.Column(db.DateTime, default=now_wat, onupdate=now_wat)

    intern = db.relationship("User", back_populates="attendance_records", foreign_keys=[intern_id])
    course = db.relationship("Course")
    marked_by = db.relationship("User", foreign_keys=[marked_by_id])

    @property
    def status_label(self):
        return {ATT_PUNCTUAL: "Punctual", ATT_LATE: "Late", ATT_ABSENT: "Absent"}.get(self.status, self.status)

    @property
    def badge_color(self):
        return {ATT_PUNCTUAL: "emerald", ATT_LATE: "amber", ATT_ABSENT: "rose"}.get(self.status, "slate")

    def __repr__(self):
        return f"<Attendance intern={self.intern_id} {self.date} {self.status}>"


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
class Assignment(db.Model):
    __tablename__ = "assignments"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    max_score = db.Column(db.Integer, nullable=False, default=100)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=now_wat)

    course = db.relationship("Course", back_populates="assignments")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    submissions = db.relationship(
        "Submission", back_populates="assignment", cascade="all, delete-orphan"
    )

    @property
    def is_overdue(self):
        return now_wat() > self.due_date

    def submission_for(self, intern):
        """The given intern's submission for this assignment, or None."""
        for sub in self.submissions:
            if sub.intern_id == intern.id:
                return sub
        return None

    @property
    def pending_count(self):
        return sum(1 for s in self.submissions if s.score is None)

    def __repr__(self):
        return f"<Assignment {self.title}>"


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
class Submission(db.Model):
    __tablename__ = "submissions"
    __table_args__ = (
        db.UniqueConstraint("assignment_id", "intern_id", name="uq_submission_assignment_intern"),
    )

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False, index=True)
    intern_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    response_text = db.Column(db.Text)
    link_url = db.Column(db.String(500))
    submitted_at = db.Column(db.DateTime, default=now_wat)
    updated_at = db.Column(db.DateTime, default=now_wat, onupdate=now_wat)
    is_late = db.Column(db.Boolean, default=False)

    score = db.Column(db.Float)          # None = not graded yet
    feedback = db.Column(db.Text)
    graded_at = db.Column(db.DateTime)
    graded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    assignment = db.relationship("Assignment", back_populates="submissions")
    intern = db.relationship("User", back_populates="submissions", foreign_keys=[intern_id])
    graded_by = db.relationship("User", foreign_keys=[graded_by_id])

    @property
    def is_graded(self):
        return self.score is not None

    @property
    def status_label(self):
        if self.is_graded:
            return "Graded"
        return "Late" if self.is_late else "Submitted"

    @property
    def percent(self):
        if self.score is None or not self.assignment.max_score:
            return None
        return round(self.score / self.assignment.max_score * 100, 1)

    def __repr__(self):
        return f"<Submission assignment={self.assignment_id} intern={self.intern_id}>"


# ---------------------------------------------------------------------------
# Notification (bell icon)
# ---------------------------------------------------------------------------
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(200))
    icon = db.Column(db.String(60), default="fa-solid fa-bell")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_wat)

    user = db.relationship("User", back_populates="notifications")

    def __repr__(self):
        return f"<Notification to={self.user_id} {self.message[:30]}>"
