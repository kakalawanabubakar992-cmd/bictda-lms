"""
auth.py - Landing portal, Intern Sign In, Facilitator Sign In and Logout.

    /                   Landing portal (programmes, course tracks, sign-in cards)
    /login/intern          Intern Sign In  (Email | Intern ID | Phone Number + Password)
    /login/facilitator     Facilitator Sign In (Facilitator ID + Password)
    /register/intern       Intern Sign Up (full name, email, phone, programme, password)
    /register/facilitator  Facilitator Sign Up (BICTDA-issued ID, email, password, courses offered)
    /forgot-password/<portal>  Ask for a password-reset link by email
    /reset-password/<token>    Choose a new password from the emailed link (1 hour, one use)
    /logout                Sign out (POST only, protected by CSRF)
"""
from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from decorators import home_url_for
from models import ENROLL_PENDING, ENROLL_SUSPENDED, ROLE_FACILITATOR, ROLE_INTERN, Course, Programme, User
from services import (make_reset_token, register_facilitator, register_intern, reset_password,
                      send_password_reset_email, user_from_reset_token)
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
# Same message whether or not the account exists, so nobody can test which accounts exist
RESET_SENT = ("If an account matches those details, a password reset link has been sent to its email address. "
              "Check your inbox and spam folder - the link works for 1 hour. "
              "No email on your account? Please contact the BICTDA admin.")


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


def find_account(portal, identifier):
    """Forgot password: interns by email, Intern ID or phone; facilitators by Facilitator ID or email."""
    if portal == "intern":
        return next((user for method in INTERN_METHODS if (user := find_intern(method, identifier))), None)
    user = find_facilitator(identifier)
    if user is None and "@" in (identifier or ""):
        user = User.query.filter(User.role == ROLE_FACILITATOR,
                                 func.lower(User.email) == identifier.strip().lower()).first()
    return user


def _portal_page(portal, mode="signin", method="email", identifier="", token=None, account=None):
    """Render login.html for one portal (intern/facilitator): sign in, sign up, forgot or reset password."""
    titles = {"signin": "Sign In", "signup": "Sign Up", "forgot": "Forgot Password", "reset": "New Password"}
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
        token=token,
        account=account,
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
        elif user.enrollment_status == ENROLL_PENDING:
            flash("Your account is waiting for approval by a BICTDA facilitator. Please try again later.", "info")
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
            flash(f"Account created. Your BICTDA Intern ID is {intern.intern_id}. "
                  "You can sign in after a BICTDA facilitator approves your account.", "success")
            return redirect(url_for("auth.login_intern"))
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
            facilitator = register_facilitator(form.get("facilitator_id"), form.get("email"), form.get("password"),
                                               form.get("confirm_password"), form.getlist("courses"))
            login_user(facilitator)
            flash(f"Welcome, {facilitator.full_name}! Your facilitator account is ready.", "success")
            return redirect(url_for("facilitator.dashboard"))
        except ValueError as error:
            flash(str(error), "error")
    return _portal_page("facilitator", mode="signup")


@auth_bp.route("/forgot-password/<portal>", methods=["GET", "POST"])
def forgot_password(portal):
    """Step 1: the user enters their email or ID; we email a reset link if the account exists."""
    if portal not in ("intern", "facilitator"):
        abort(404)
    if current_user.is_authenticated:
        return redirect(home_url_for(current_user))
    if request.method == "POST":
        user = find_account(portal, request.form.get("identifier"))
        if user and user.email:
            link = url_for("auth.reset_password_page", token=make_reset_token(user), _external=True)
            logo = url_for("static", filename="icons/bictda-logo.png", _external=True)
            if not send_password_reset_email(user, link, logo):
                flash("We could not send the email right now. Please try again later or contact the BICTDA admin.", "error")
                return _portal_page(portal, mode="forgot", identifier=request.form.get("identifier", ""))
        flash(RESET_SENT, "info")
        return redirect(url_for(f"auth.login_{portal}"))
    return _portal_page(portal, mode="forgot")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_page(token):
    """Step 2: from the emailed link, choose a new password, then sign in with it."""
    user = user_from_reset_token(token)
    if user is None:
        flash("This reset link is invalid, has expired or was already used. Please ask for a new one.", "error")
        return redirect(url_for("auth.forgot_password", portal="intern"))
    portal = "intern" if user.is_intern else "facilitator"
    if request.method == "POST":
        try:
            reset_password(user, request.form.get("password"), request.form.get("confirm_password"))
            logout_user()
            flash("Your password has been changed. Please sign in with your new password.", "success")
            return redirect(url_for(f"auth.login_{portal}"))
        except ValueError as error:
            flash(str(error), "error")
    return _portal_page(portal, mode="reset", token=token, account=user)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()   # also deletes the "Remember me" cookie - do not call session.clear() after it
    flash("You have signed out successfully.", "info")
    return redirect(url_for("auth.index"))
