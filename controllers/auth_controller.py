"""
Sign-in and sign-out for everyone.

  * Admin:    username + password, only for the backend (/backend).
  * Riders (students, teachers, staff ... see content/user_types.py): name + ID, no password.

(Buses report their own position from a GPS box - see controllers/device_controller.py.)

Login endpoints are rate-limited per IP address (Flask-Limiter) to stop password guessing.
"""

import hmac
import re
import time

from flask import Blueprint, current_app, redirect, session, url_for

from content import rules
from controllers.helpers import fail, json_body, ok
from extensions import limiter
from models.rider_types import rider_info
from services import store
from services.words import say

auth_bp = Blueprint("auth", __name__)

# A rider ID: letters, digits and - _ / . (e.g. "190212", "KU-2021-033").
RIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/.]{0,39}$")
# Not allowed in a name: links, code-like symbols and digits (names in any language are fine).
NAME_REFUSED_RE = re.compile(r"[<>{}\[\]\\/@#$%^*=+|~`\"\d]|https?:|www\.", re.IGNORECASE)


def _real_name(name: str) -> bool:
    """True for something that looks like a person's name (any language): letters, spaces and . ' -"""
    return (any(c.isalpha() for c in name) and all(c.isprintable() for c in name)
            and not NAME_REFUSED_RE.search(name))


def admin_signed_in() -> bool:
    """True while the backend admin is signed in, and for at most ADMIN_SESSION_HOURS after signing in."""
    since = session.get("admin_since")
    if not session.get("is_admin") or not isinstance(since, (int, float)):
        return False
    return time.time() - since < rules.ADMIN_SESSION_HOURS * 3600


def _start_fresh_session(keep_admin: bool = True) -> None:
    """
    Forget any previous sign-in in this browser. Keeps the page's CSRF token (so
    the open page keeps working) and, unless told otherwise, the backend admin sign-in.
    """
    kept = {key: session[key] for key in ("csrf_token", "is_admin", "admin_since") if key in session}
    if not keep_admin:
        kept.pop("is_admin", None)
        kept.pop("admin_since", None)
    session.clear()
    session.update(kept)


# ---------------------------------------------------------------------------
# Admin (backend only)
# ---------------------------------------------------------------------------
@auth_bp.post("/api/auth/admin/login")
@limiter.limit(rules.ADMIN_LOGIN_LIMIT)
def admin_login():
    """Sign the admin in. Compares in constant time so the password can't be guessed by timing."""
    data = json_body()
    # Spaces before / after are ignored (they sneak in when copying); the username is not case-sensitive.
    username = str(data.get("username") or "").strip().lower()
    password = str(data.get("password") or "").strip()
    expected_password = (current_app.config["ADMIN_PASSWORD"] or "").strip()
    good_user = hmac.compare_digest(username.encode(), current_app.config["ADMIN_USERNAME"].strip().lower().encode())
    good_pass = hmac.compare_digest(password.encode(), expected_password.encode())
    if not (good_user and good_pass and expected_password):
        return fail(say("Wrong username or password."), 401)
    _start_fresh_session(keep_admin=False)
    session["is_admin"] = True
    session["admin_since"] = time.time()           # signed out by itself after ADMIN_SESSION_HOURS
    return ok(redirect_url=url_for("admin.portal"))


@auth_bp.post("/backend/logout")
def admin_logout():
    """Sign the admin out of the backend (POST with the page's CSRF token, so other sites can't do it)."""
    session.pop("is_admin", None)
    session.pop("admin_since", None)
    return redirect(url_for("admin.login_page"))


# ---------------------------------------------------------------------------
# Students, teachers, staff and any other rider type from content/user_types.py
# ---------------------------------------------------------------------------
@auth_bp.post("/api/auth/<rider_type>/login")
@limiter.limit(rules.RIDER_LOGIN_LIMIT)
def rider_login(rider_type: str):
    """
    Sign-in for a rider type (e.g. /api/auth/student/login): just a name and an ID.
    Body: {"full_name": ..., "rider_id": ...}  (the older "<type>_id" key also works).
    """
    info = rider_info(rider_type)
    if info is None:
        return fail(say("Not found."), 404)
    data = json_body()
    rider_id = str(data.get("rider_id") or data.get(f"{rider_type}_id") or "").strip()[:40]
    full_name = " ".join(str(data.get("full_name") or "").split())[:60]
    if not rider_id or not full_name:
        return fail(say("Please enter your name and {id_label}.", id_label=info["id_label"]))
    if not RIDER_ID_RE.match(rider_id):
        return fail(say("{id_label} may only use letters, numbers and - _ / .", id_label=info["id_label"]))
    if not _real_name(full_name):
        return fail(say("Please enter your real name (letters only)."))
    store.record_rider(rider_type, rider_id, full_name)
    _start_fresh_session()
    session.permanent = True
    session.update(role=rider_type, rider_id=rider_id, rider_name=full_name)
    return ok(message=say("Welcome, {name}", name=full_name),
              redirect_url=url_for("views.rider_dashboard", rider_type=rider_type))


# ---------------------------------------------------------------------------
# Sign out (everyone except the backend admin, see /backend/logout)
# ---------------------------------------------------------------------------
@auth_bp.post("/api/auth/logout")
def logout():
    """Sign out of the rider map."""
    _start_fresh_session()
    return ok(message=say("Logged out."), redirect_url=url_for("views.landing"))
