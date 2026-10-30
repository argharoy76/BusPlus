"""
gunicorn settings for the live server:  gunicorn -c gunicorn.conf.py wsgi:app

BusPlus keeps live bus positions in memory, so it must run as ONE process.
The gevent worker lets that single process hold hundreds of open live maps
(each map keeps one streaming connection open) at the same time.
"""

import os

# nginx forwards requests to this address; it is not reachable from the internet directly.
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

workers = 1                      # exactly one: all live data lives in this process
worker_class = "gevent"          # cooperative connections for the live map streams
worker_connections = 2000        # open connections this process may hold

timeout = 60                     # restart the worker if it stops answering for this long
graceful_timeout = 10            # on restart, give open requests this long to finish
keepalive = 5

# Log to stdout/stderr; systemd stores it (see: journalctl -u busplus)
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Trust the X-Forwarded-* headers only from nginx on this machine.
forwarded_allow_ips = "127.0.0.1"

# gunicorn's runtime control socket isn't used (systemd manages the process), and the
# service is not allowed to write to its home folder anyway.
control_socket_disable = True
