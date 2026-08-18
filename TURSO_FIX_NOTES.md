# Turso fix

This is based on the last known-good Copier Store version. It keeps the existing SQLite code, uses Turso remotely when TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are set, and treats Turso/libSQL duplicate-column ValueErrors like the existing SQLite OperationalError migration handling.
