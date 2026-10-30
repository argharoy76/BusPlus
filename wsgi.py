"""
Entry point for production servers (gunicorn): `gunicorn -c gunicorn.conf.py wsgi:app`.
"""

from app import create_app

app = create_app()
