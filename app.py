from flask import Flask, render_template, request, session, redirect, flash, jsonify, g, has_app_context
import sqlite3 as _sqlite3

# --- Turso / SQLite compatibility layer ---
# The application was originally written for Python's sqlite3 API.  Turso's
# libsql driver is SQLite-compatible but its remote Connection object does not
# expose sqlite3's row_factory attribute.  This adapter preserves the small
# sqlite3 surface used by CopierStore while sending the actual database work
# to Turso whenever the two TURSO_* environment variables are present.
try:
    import libsql as _turso_libsql
except ImportError:
    _turso_libsql = None


# Track only connections created inside the current Flask application context.
# Each request gets its own `g`, so one request can never close another
# request's Turso/libSQL connection. Connections created during startup
# (before a Flask context exists) continue to be managed by the existing
# explicit close() calls.
def _register_turso_connection(connection):
    if not has_app_context():
        return
    connections = getattr(g, "_turso_connections", None)
    if connections is None:
        connections = []
        g._turso_connections = connections
    connections.append(connection)


def _unregister_turso_connection(connection):
    if not has_app_context():
        return
    connections = getattr(g, "_turso_connections", None)
    if not connections:
        return
    try:
        connections.remove(connection)
    except ValueError:
        pass


def _close_turso_connections():
    if not has_app_context():
        return
    connections = list(getattr(g, "_turso_connections", ()))
    # Clear the request-local collection first so close() cannot mutate the
    # list while it is being iterated. close() itself is idempotent below.
    g._turso_connections = []
    for connection in connections:
        try:
            connection.close()
        except Exception:
            # Request cleanup must never replace the original Flask response
            # with a connection-close exception.
            pass


class _CompatRow:
    """Small sqlite3.Row-compatible mapping/sequence wrapper."""
    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):
        self._keys = tuple(keys or ())
        self._values = tuple(values or ())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        key_l = str(key).lower()
        for i, name in enumerate(self._keys):
            if str(name).lower() == key_l:
                return self._values[i]
        raise IndexError(key)

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._keys)

    def __repr__(self):
        return repr(dict(zip(self._keys, self._values)))


class _CompatCursor:
    def __init__(self, raw, connection):
        self.raw = raw
        self.connection = connection

    @property
    def description(self):
        return getattr(self.raw, "description", None)

    @property
    def lastrowid(self):
        return getattr(self.raw, "lastrowid", None)

    @property
    def rowcount(self):
        return getattr(self.raw, "rowcount", -1)

    def execute(self, sql, parameters=()):
        try:
            if parameters is None:
                self.raw.execute(sql)
            else:
                self.raw.execute(sql, parameters)
            return self
        except Exception as exc:
            message = str(exc).lower()
            # Turso/HRANA streams can expire while a long-lived Render worker
            # is still holding a libsql connection. Reconnect once and retry the
            # exact statement. The cursor itself must also be replaced: a new
            # connection with an old cursor still points at the dead HRANA stream.
            if "stream not found" in message and hasattr(self.connection, "_reconnect"):
                self.connection._reconnect()
                self.raw = self.connection.raw.cursor()
                try:
                    if parameters is None:
                        self.raw.execute(sql)
                    else:
                        self.raw.execute(sql, parameters)
                    return self
                except Exception as retry_exc:
                    retry_message = str(retry_exc).lower()
                    if "duplicate column name" in retry_message or "already exists" in retry_message:
                        raise _sqlite3.OperationalError(str(retry_exc)) from retry_exc
                    raise
            # Existing CopierStore migrations intentionally attempt ADD COLUMN
            # on older databases. SQLite used to raise OperationalError here;
            # libsql surfaces it as a different exception type. Normalize only
            # these expected migration errors so the existing try/except blocks
            # continue to work exactly as they did with sqlite3.
            if "duplicate column name" in message or "already exists" in message:
                raise _sqlite3.OperationalError(str(exc)) from exc
            raise

    def fetchone(self):
        row = self.raw.fetchone()
        return self.connection._convert_row(row, self.description)

    def fetchall(self):
        rows = self.raw.fetchall()
        return [self.connection._convert_row(row, self.description) for row in rows]

    def fetchmany(self, size=None):
        rows = self.raw.fetchmany(size) if size is not None else self.raw.fetchmany()
        return [self.connection._convert_row(row, self.description) for row in rows]

    def __iter__(self):
        for row in self.raw:
            yield self.connection._convert_row(row, self.description)

    def __getattr__(self, name):
        return getattr(self.raw, name)


class _CompatConnection:
    def __init__(self, raw):
        self.raw = raw
        self._row_factory = None
        self._closed = False
        _register_turso_connection(self)

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def _convert_row(self, row, description):
        if row is None:
            return None
        if self._row_factory is None:
            return row
        # Preserve the application's sqlite3.Row behavior for the only row
        # factory it uses: sqlite3.Row.
        if self._row_factory is _sqlite3.Row:
            names = [col[0] for col in (description or ())]
            return _CompatRow(names, row)
        try:
            return self._row_factory(None, row)
        except Exception:
            return row

    def cursor(self):
        return _CompatCursor(self.raw.cursor(), self)

    def _reconnect(self):
        """Replace an expired Turso connection with a fresh HRANA stream."""
        if self._closed:
            raise _sqlite3.ProgrammingError("Cannot reconnect a closed database connection")
        turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
        turso_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
        if not turso_url or not turso_token or _turso_libsql is None:
            raise RuntimeError("Turso connection recovery is unavailable")
        old_raw = self.raw
        try:
            old_raw.close()
        except Exception:
            pass
        self.raw = _turso_libsql.connect(database=turso_url, auth_token=turso_token)

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def commit(self):
        try:
            return self.raw.commit()
        except Exception as exc:
            # A commit can encounter the same stale-stream condition. Reconnect
            # and retry the commit once. This is safe for this application's
            # request-scoped transactions because all statements are completed
            # before commit and the connection is immediately reused/closed.
            message = str(exc).lower()
            if "stream not found" in message:
                self._reconnect()
                return self.raw.commit()
            raise

    def rollback(self):
        try:
            return self.raw.rollback()
        except Exception as exc:
            # If the remote Hrana stream has already expired, rollback cannot
            # reach that detached transaction. Do not mask the original error.
            message = str(exc).lower()
            if "stream not found" in message or (
                "hrana" in message and "status=404" in message and "not found" in message
            ):
                return None
            raise

    def close(self):
        if self._closed:
            return None
        try:
            return self.raw.close()
        finally:
            self._closed = True
            _unregister_turso_connection(self)

    def __getattr__(self, name):
        return getattr(self.raw, name)


class _SQLiteCompat:
    Row = _sqlite3.Row
    Error = _sqlite3.Error
    OperationalError = _sqlite3.OperationalError
    IntegrityError = _sqlite3.IntegrityError
    DatabaseError = _sqlite3.DatabaseError
    ProgrammingError = _sqlite3.ProgrammingError
    InterfaceError = _sqlite3.InterfaceError

    @staticmethod
    def connect(database, *args, **kwargs):
        turso_url = os.environ.get("TURSO_DATABASE_URL", "").strip()
        turso_token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
        if turso_url and turso_token:
            if _turso_libsql is None:
                raise RuntimeError(
                    "Turso credentials are configured but the libsql package is not installed."
                )
            raw = _turso_libsql.connect(database=turso_url, auth_token=turso_token)
            return _CompatConnection(raw)
        return _sqlite3.connect(database, *args, **kwargs)


sqlite3 = _SQLiteCompat

from pathlib import Path
import os
import re
import secrets
import hashlib
import hmac
import time
import mimetypes
import logging
import traceback
import json
import urllib.parse
import urllib.request
import urllib.error
import threading
import functools
import base64
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, session, redirect, flash, jsonify, g, has_app_context

# Load local .env when present (never committed to source control).
def _load_local_env():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass

_load_local_env()

# Always resolve the database from the application directory (or an explicit
# DATABASE_PATH). This prevents deployment failures when the process working
# directory differs from the project root.
DATABASE_PATH = os.path.abspath(os.environ.get(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.db")
))

# ...
