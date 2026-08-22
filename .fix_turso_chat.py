from pathlib import Path

p = Path('app.py')
s = p.read_text(encoding='utf-8')

old = '''    def execute(self, sql, parameters=()):
        try:
            if parameters is None:
                self.raw.execute(sql)
            else:
                self.raw.execute(sql, parameters)
            return self
        except Exception as exc:
            message = str(exc).lower()
            # Existing CopierStore migrations intentionally attempt ADD COLUMN
            # on older databases.  SQLite used to raise OperationalError here;
            # libsql surfaces it as a different exception type.  Normalize only
            # these expected migration errors so the existing try/except blocks
            # continue to work exactly as they did with sqlite3.
            if "duplicate column name" in message or "already exists" in message:
                raise _sqlite3.OperationalError(str(exc)) from exc
            raise
'''
new = '''    def execute(self, sql, parameters=()):
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
            # exact statement. This is intentionally limited to the specific
            # stale-stream 404 so real SQL/database errors are never hidden.
            if "stream not found" in message and hasattr(self.connection, "_reconnect"):
                self.connection._reconnect()
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
'''
assert old in s, 'cursor execute block not found'
s = s.replace(old, new, 1)

old = '''    def cursor(self):
        return _CompatCursor(self.raw.cursor(), self)

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)
'''
new = '''    def cursor(self):
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
'''
assert old in s, 'connection cursor block not found'
s = s.replace(old, new, 1)

old = '''        msg_id = cur.lastrowid
        cur.execute(
            "UPDATE chat_conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (conv_id,),
        )

        # Notifications are secondary. A notification schema/plugin mismatch must
'''
new = '''        msg_id = cur.lastrowid
        # Commit the actual message before the non-essential conversation timestamp
        # and notification bookkeeping. This guarantees that a stale Turso stream
        # during secondary bookkeeping can never make the user's message vanish.
        conn.commit()
        try:
            cur.execute(
                "UPDATE chat_conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (conv_id,),
            )
            conn.commit()
        except sqlite3.Error:
            # Message delivery already succeeded; timestamp refresh is best-effort.
            pass

        # Notifications are secondary. A notification schema/plugin mismatch must
'''
assert old in s, 'chat send timestamp block not found'
s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
