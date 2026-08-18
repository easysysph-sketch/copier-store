# Turso + Render setup

This version keeps the existing SQLite code and transparently switches the
database connection to Turso when these two environment variables are set:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`

Local development remains on `orders.db` when those variables are absent.

On Render, add the two variables to the existing Copier Store Web Service.
Do not put the auth token in source code or commit it to Git.

The first deployment against an empty Turso database will run the existing
`init_db()` and create the application's tables there.
