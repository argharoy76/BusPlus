"""
Flask extensions shared by the whole app.

They are created here without an app and attached in `create_app()` (the usual
Flask "application factory" pattern), so any module can import them safely.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for every database table (see models/records.py)."""


# Database access (SQLite file by default).
db = SQLAlchemy(model_class=Base)

# Rejects POST/PUT/DELETE requests that don't carry the page's CSRF token,
# so other websites can't make a signed-in browser change anything here.
csrf = CSRFProtect()

# Limits how fast one IP address may call sensitive endpoints (logins).
limiter = Limiter(key_func=get_remote_address)

# Security headers: Content-Security-Policy, HSTS, no framing, HTTPS redirect.
talisman = Talisman()
