# Turso startup optimization

When Turso is configured, startup checks whether the existing core schema is
already present. If it is, the original local SQLite migration chain is
skipped to avoid replaying many remote statements during every Gunicorn start.
Local SQLite behavior remains unchanged.
