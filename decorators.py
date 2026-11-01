"""
decorators.py - Role-based access control.

    @intern_required       -> only logged-in interns can open the page
    @facilitator_required  -> only logged-in facilitators can open the page

Anyone else is sent back to their own dashboard (or to sign in).
"""
from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user, login_required

from models import ROLE_FACILITATOR, ROLE_INTERN


def home_url_for(user):
    """Where a user should land: their own dashboard, or the portal page if not signed in."""
    if user is not None and user.is_authenticated:
        if user.is_facilitator:
            return url_for("facilitator.dashboard")
        return url_for("intern.dashboard")
    return url_for("auth.index")


def role_required(*roles):
    """Allow the view only for users whose role is in `roles`."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash("You do not have permission to open that page.", "warning")
                return redirect(home_url_for(current_user))
            return view(*args, **kwargs)
        # login_required runs first: not signed in -> sign-in page
        return login_required(wrapped)
    return decorator


intern_required = role_required(ROLE_INTERN)
facilitator_required = role_required(ROLE_FACILITATOR)
