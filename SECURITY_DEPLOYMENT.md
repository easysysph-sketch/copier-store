# CopierStore — production security & deployment

This package is prepared as a deployment baseline. It contains no customer accounts, orders, receipts, repair uploads, chat history, admin password hash, Git history, or backup databases.

## Required before going live

1. Set a unique `SECRET_KEY` (32+ random characters; 64+ is recommended).
2. Set a strong `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `ADMIN_RECOVERY_KEY` in the hosting provider's secret/environment settings.
3. Configure Turso with `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` for persistent production data. Do not rely on the local SQLite file for a public Render service unless persistent disk storage is explicitly configured.
4. Configure real store/payment settings in the admin dashboard.
5. Configure Gemini/Lalamove only when the corresponding features are needed.
6. Enable HTTPS and keep `SESSION_COOKIE_SECURE=1`.

## Security controls included

- HttpOnly + SameSite session cookies
- Secure cookies in production
- CSRF tokens for browser form POSTs
- Same-origin checks for JSON APIs
- Security headers including HSTS in HTTPS production
- No-store caching for authenticated responses
- Login/password-reset throttling
- API rate limiting, including chat polling/sending
- Password hashing with Werkzeug
- Server-side price/stock validation
- Safe local redirect validation
- Upload extension + file-signature validation
- Private payment/repair files outside `static/`
- Ownership checks for customer orders, chats, repairs and private files
- Stable numeric product URLs with legacy product-name URL compatibility
- Bounded chat polling payloads
- Production WSGI server configuration
- `/health` endpoint for hosting health checks

## Important limitation

No application can honestly be called "perfect" or "100% secure". Security also depends on Render/Turso configuration, secret rotation, DNS/HTTPS, database permissions, operating-system patching, payment-provider settings, and the code added after this package is deployed. Treat this package as a hardened deployment baseline and run a real HTTPS/browser smoke test after deployment.
