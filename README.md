# CopierStore — deployment package

Flask-based ecommerce and store-management system for CopierStore.

## Included

- Customer registration/login, profile and saved addresses
- Product catalog, cart, wishlist and checkout
- Server-side stock/price validation
- Customer/admin notifications and live support chat
- Repair requests and protected repair-photo storage
- Payment verification with protected receipt storage
- Delivery/location tools and optional Lalamove integration
- Optional Gemini AI customer support
- Accounting/bookkeeping dashboard
- Admin product/category/store/payment management
- Production WSGI configuration via Gunicorn
- HTTPS/proxy-aware sessions and request security
- CSRF protection for browser forms and same-origin protection for JSON APIs
- Login throttling and secure upload validation

## Production setup

1. Install Python 3.11+ and create a virtual environment.
2. Install dependencies:

   `python -m pip install -r requirements.txt`

3. Configure the environment variables from `.env.example` in your hosting dashboard (preferred) or in a local `.env` file. **Do not upload `.env`.**
4. Set a unique `SECRET_KEY` with at least 32 random characters.
5. Set a strong `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
6. Set `FLASK_ENV=production`, `FLASK_DEBUG=0`, and `SESSION_COOKIE_SECURE=1` behind HTTPS.
7. Configure the store's exact location and real payment details in the Admin dashboard after the first deployment.
8. Add real products and stock in **Admin → Products**.
9. Add real Lalamove/Gemini credentials only if those features are required.
10. Deploy with the included `Procfile` / Gunicorn WSGI server.

## Database persistence

This package includes a **sanitized, empty `orders.db`** containing the application schema and default categories/settings. It contains no customer accounts, orders, repairs, chats, receipts, or test uploads.

SQLite requires persistent writable storage. If your hosting provider uses an ephemeral filesystem, attach a persistent disk/volume for the directory containing `orders.db`, `private_uploads/`, and `static/uploads/`, or migrate the app to a production database before launch.

## Important security rules

- Never deploy `.env` or paste production secrets into source control.
- Rotate any API key/secret that was previously stored in a local test `.env`.
- Keep `private_uploads/` outside the public static directory.
- Use HTTPS in production.
- Back up the production database before major changes.
- Do not use Flask's development server for public traffic.

## Health check

After deployment, open `/health`. A healthy app returns:

`{"status":"ok"}`

## Local production-style run

Windows:

`start_production_windows.bat`

Or directly:

`gunicorn wsgi:app --workers 2 --threads 4 --timeout 120`

## Clean data reset

`reset_test_data.py` removes transactional/customer/test data and uploaded files while preserving the catalog/settings. Back up the database before running it.
