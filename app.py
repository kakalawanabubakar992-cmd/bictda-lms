"""
app.py - Main entry point for BICTDA LMS.

Run locally:      python app.py          -> http://127.0.0.1:5000
Run on Render:    gunicorn app:app

What happens here:
  1. Create the Flask app and load settings from config.py
  2. Connect the extensions (database, login manager, CSRF protection)
  3. Register the page groups (blueprints): auth, intern, facilitator
  4. Create the database tables and seed demo data if the database is empty
  5. Error pages, health check, notifications and template helpers
"""
import json
import os
from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from decorators import home_url_for
from extensions import csrf, db, login_manager
from models import PASS_MARK
from utils import now_wat, today_wat


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config.setdefault(
        "SHOW_DEMO_LOGINS", os.environ.get("SHOW_DEMO_LOGINS", "true").lower() == "true"
    )

    # Render sits behind a proxy: trust its headers so HTTPS links are generated correctly
    if app.config["IS_PRODUCTION"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ----- Extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"
    # "basic" (not "strong"): phone networks change IP addresses often, and "strong"
    # would sign interns out every time that happens.
    login_manager.session_protection = "basic"

    import models  # noqa: F401  (registers the tables and the user loader)
    from models import Notification

    @login_manager.unauthorized_handler
    def unauthorized():
        """Not signed in: send facilitator pages to Facilitator Sign In, the rest to Intern Sign In."""
        flash("Please sign in to continue.", "info")
        endpoint = "auth.login_facilitator" if request.path.startswith("/facilitator") else "auth.login_intern"
        return redirect(url_for(endpoint, next=request.path))

    # ----- Blueprints (groups of pages)
    from auth import auth_bp
    from facilitator import facilitator_bp
    from intern import intern_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(intern_bp)
    app.register_blueprint(facilitator_bp)

    # ----- Database tables + demo data
    with app.app_context():
        db.create_all()
        from seed import seed_database, seed_issued_ids
        try:
            if app.config["AUTO_SEED"]:
                seed_database(verbose=True)
            seed_issued_ids()          # Facilitator IDs the admin added to seed.py since the last start
        except IntegrityError:
            # Another server process seeded at the same moment - safe to ignore
            db.session.rollback()

    # ----- Template helpers
    @app.context_processor
    def inject_globals():
        return {
            "app_name": app.config["APP_NAME"],
            "app_full_name": app.config["APP_FULL_NAME"],
            "agency_name": app.config["AGENCY_NAME"],
            "today": today_wat(),
            "current_year": now_wat().year,
            "home_url": home_url_for(current_user),
            "show_demo_logins": app.config["SHOW_DEMO_LOGINS"],
            "pass_mark": PASS_MARK,
        }

    @app.template_filter("date")
    def format_date(value, fmt="%d %b %Y"):
        return value.strftime(fmt) if value else "-"

    @app.template_filter("datetime")
    def format_datetime(value, fmt="%d %b %Y, %I:%M %p"):
        return value.strftime(fmt) if value else "-"

    @app.template_filter("timeago")
    def timeago(value):
        if not value:
            return ""
        seconds = int((now_wat() - value).total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60} min ago"
        if seconds < 86400:
            return f"{seconds // 3600} hr ago"
        days = seconds // 86400
        if days < 7:
            return f"{days} day{'s' if days != 1 else ''} ago"
        return value.strftime("%d %b %Y")

    # ----- Health check (Render uses this to know the app is alive)
    @app.route("/healthz")
    def healthz():
        try:
            db.session.execute(text("SELECT 1"))
            return {"status": "ok", "time_wat": now_wat().isoformat(timespec="seconds")}, 200
        except Exception:
            return {"status": "database_error"}, 500

    # ----- Installable app (PWA): manifest + service worker, both served from the site root
    @app.route("/manifest.webmanifest")
    def manifest():
        def icon(name, size, purpose="any"):
            return {"src": url_for("static", filename=f"icons/{name}"), "sizes": size, "type": "image/png", "purpose": purpose}
        data = {
            "name": app.config["APP_FULL_NAME"],
            "short_name": app.config["APP_NAME"],
            "description": f"{app.config['AGENCY_NAME']} - internship and learning portal for SIWES and NYSC.",
            "start_url": "/login",          # signed-in users go straight to their dashboard
            "scope": "/",
            "display": "standalone",
            "background_color": "#0a1a4f",
            "theme_color": "#0a1a4f",
            "icons": [icon("icon-192.png", "192x192"), icon("icon-512.png", "512x512"),
                      icon("icon-maskable-512.png", "512x512", "maskable")],
        }
        return Response(json.dumps(data), mimetype="application/manifest+json")

    @app.route("/service-worker.js")
    def service_worker():
        # Served from "/" so it controls every page. The version is filled in on each deploy.
        with open(os.path.join(app.static_folder, "service-worker.js"), encoding="utf-8") as f:
            script = f.read().replace("__APP_VERSION__", app.config["APP_VERSION"])
        return Response(script, mimetype="application/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    # ----- Notifications (bell icon)
    @app.route("/notifications/<int:notification_id>")
    @login_required
    def open_notification(notification_id):
        notification = db.session.get(Notification, notification_id)
        if notification is None or notification.user_id != current_user.id:
            abort(404)
        notification.is_read = True
        db.session.commit()
        return redirect(notification.link or home_url_for(current_user))

    @app.route("/notifications/read-all", methods=["POST"])
    @login_required
    def read_all_notifications():
        for notification in current_user.notifications:
            notification.is_read = True
        db.session.commit()
        flash("All notifications marked as read.", "success")
        return redirect(request.referrer or home_url_for(current_user))

    # ----- Error pages
    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html", title="Page Not Found"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html", title="Server Error"), 500

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        flash("Your session expired or the form was out of date. Please try again.", "warning")
        referrer = request.referrer or ""
        if referrer.startswith(request.host_url):
            return redirect(referrer)
        return redirect(url_for("auth.index"))

    return app


app = create_app()

if __name__ == "__main__":
    # debug=True reloads the server when you save a file (local development only)
    app.run(debug=not app.config["IS_PRODUCTION"], port=int(os.environ.get("PORT", 5000)))
