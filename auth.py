"""
auth.py - Landing portal, Intern Sign In, Facilitator Sign In and Logout.

    /                   Landing portal (programmes, course tracks, sign-in cards)
    /login/intern          Intern Sign In  (Email | Intern ID | Phone Number + Password)
    /login/facilitator     Facilitator Sign In (Facilitator ID + Password)
    /register/intern       Intern Sign Up (full name, email, phone, programme, password)
    /register/facilitator  Facilitator Sign Up (BICTDA-issued ID, password, courses offered)
    /logout                Sign out (POST only, protected by CSRF)
"""
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from decorators import home_url_for
from models import ENROLL_SUSPENDED, ROLE_FACILITATOR, ROLE_INTERN, Course, Programme, User
from services import register_facilitator, register_intern
from utils import normalize_phone

auth_bp = Blueprint("auth", __name__)

# The three ways an intern can identify themselves
INTERN_METHODS = {
    "email": "Email",
    "intern_id": "Intern ID",
    "phone": "Phone Number",
}

# Same message for every failure, so we never reveal which field was wrong
GENERIC_ERROR = "Invalid sign-in details. Please check them and try again."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_next_url(target):
    """Only allow redirects to pages on this site (prevents open-redirect attacks)."""
    if not target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def find_intern(method, identifier):
    """Look up an intern by email, Intern ID or phone number."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    query = User.query.filter(User.role == ROLE_INTERN)

    if method == "email":
        return query.filter(func.lower(User.email) == identifier.lower()).first()
    if method == "intern_id":
        return query.filter(func.upper(User.intern_id) == identifier.upper()).first()
    if method == "phone":
        phone = normalize_phone(identifier)   # 0803..., +234803..., 234803... all match
        if not phone:
            return None
        return query.filter(User.phone == phone).first()
    return None


def find_facilitator(identifier):
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    return User.query.filter(
        User.role == ROLE_FACILITATOR,
        func.upper(User.facilitator_id) == identifier.upper(),
    ).first()


def demo_accounts():
    """Demo login list shown on the sign-in page (can be switched off with SHOW_DEMO_LOGINS=false)."""
    if not current_app.config.get("SHOW_DEMO_LOGINS"):
        return {"interns": [], "facilitators": [], "intern_password": "", "facilitator_password": ""}
    from seed import FACILITATOR_PASSWORD, INTERN_PASSWORD
    interns = User.query.filter_by(role=ROLE_INTERN).order_by(User.id).limit(6).all()
    facilitators = User.query.filter_by(role=ROLE_FACILITATOR).order_by(User.id).limit(3).all()
    return {
        "interns": interns,
        "facilitators": facilitators,
        "intern_password": INTERN_PASSWORD,
        "facilitator_password": FACILITATOR_PASSWORD,
    }


def _portal_page(portal, mode="signin", method="email", identifier=""):
    """Render login.html for one portal (intern/facilitator) in sign-in or sign-up mode."""
    titles = {"signin": "Sign In", "signup": "Sign Up"}
    return render_template(
        "login.html",
        title=f"{portal.title()} {titles[mode]}",
        portal=portal,
        mode=mode,
        method=method,
        methods=INTERN_METHODS,
        identifier=identifier,
        form=request.form,
        programmes=Programme.query.order_by(Programme.id).all(),
        courses=Course.query.order_by(Course.sequence_order).all(),
        demo=demo_accounts(),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@auth_bp.route("/")
def index():
    """Landing portal page."""
    programmes = Programme.query.order_by(Programme.id).all()
    courses = Course.query.order_by(Course.sequence_order).all()
    stats = {
        "interns": User.query.filter_by(role=ROLE_INTERN).count(),
        "facilitators": User.query.filter_by(role=ROLE_FACILITATOR).count(),
        "courses": Course.query.count(),
    }
    return render_template("index.html", programmes=programmes, courses=courses, stats=stats)


@auth_bp.route("/login")
def login():
    return redirect(url_for("auth.login_intern"))


@auth_bp.route("/login/intern", methods=["GET", "POST"])
def login_intern():
    if current_user.is_authenticated:
        return redirect(home_url_for(current_user))

    method = request.values.get("method", "email")
    if method not in INTERN_METHODS:
        method = "email"
    identifier = ""

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = find_intern(method, identifier) if identifier and password else None

        if user is None or not user.check_password(password):
            flash(GENERIC_ERROR, "error")
        elif user.enrollment_status == ENROLL_SUSPENDED:
            flash("Your internship account is suspended. Please contact BICTDA.", "warning")
        else:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.full_name.split()[0]}!", "success")
            return redirect(safe_next_url(request.args.get("next")) or url_for("intern.dashboard"))

    return _portal_page("intern", method=method, identifier=identifier)


@auth_bp.route("/login/facilitator", methods=["GET", "POST"])
def login_facilitator():
    if current_user.is_authenticated:
        return redirect(home_url_for(current_user))

    identifier = ""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = find_facilitator(identifier) if identifier and password else None

        if user is None or not user.check_password(password):
            flash(GENERIC_ERROR, "error")
        else:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.full_name}!", "success")
            return redirect(safe_next_url(request.args.get("next")) or url_for("facilitator.dashboard"))

    return _portal_page("facilitator", identifier=identifier)


@auth_bp.route("/register/intern", methods=["GET", "POST"])
def register_intern_page():
    if current_user.is_authenticated:
        return redirect(home_url_for(current_user))
    if request.method == "POST":
        form = request.form
        try:
            intern = register_intern(form.get("full_name"), form.get("email"), form.get("phone"),
                                     form.get("programme"), form.get("password"), form.get("confirm_password"))
            login_user(intern)
            flash(f"Welcome, {intern.full_name.split()[0]}! Your BICTDA Intern ID is {intern.intern_id}.", "success")
            return redirect(url_for("intern.dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return _portal_page("intern", mode="signup")


@auth_bp.route("/register/facilitator", methods=["GET", "POST"])
def register_facilitator_page():
    if current_user.is_authenticated:
        return redirect(home_url_for(current_user))
    if request.method == "POST":
        form = request.form
        try:
            facilitator = register_facilitator(form.get("facilitator_id"), form.get("password"),
                                               form.get("confirm_password"), form.getlist("courses"))
            login_user(facilitator)
            flash(f"Welcome, {facilitator.full_name}! Your facilitator account is ready.", "success")
            return redirect(url_for("facilitator.dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return _portal_page("facilitator", mode="signup")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have signed out successfully.", "info")
    return redirect(url_for("auth.index"))
