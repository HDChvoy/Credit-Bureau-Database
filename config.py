"""
Database connection settings.

Read from environment variables so no credentials are committed to the
source tree. The defaults match a stock local PostgreSQL install, which
is what the D2 build scripts assume, so on a normal dev machine the app
runs with no configuration at all.

Set these before running if your setup differs:

    PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
"""

import os

DB_SETTINGS = {
    "host":     os.environ.get("PGHOST",     "localhost"),
    "port":     int(os.environ.get("PGPORT", "5432")),
    "dbname":   os.environ.get("PGDATABASE", "experian_credit"),
    "user":     os.environ.get("PGUSER",     os.environ.get("USER", "postgres")),
}

# Only send a password if one was actually supplied. A local trust-auth
# install rejects the connection if an empty password is passed.
_password = os.environ.get("PGPASSWORD")
if _password:
    DB_SETTINGS["password"] = _password

# Flask needs a secret key to sign the session cookie that carries flash
# messages. Generated per-process if not supplied, which is fine for a
# single-user demo app but would be set from the environment in anything
# real, so that sessions survive a restart.
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())
