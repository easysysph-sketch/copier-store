# CopierStore deployment checklist

## Before going public

- [ ] Configure all values in `.env.example` through the hosting provider's environment settings.
- [ ] Generate a unique `SECRET_KEY` (32+ random characters).
- [ ] Set a strong `ADMIN_PASSWORD` and `ADMIN_RECOVERY_KEY`.
- [ ] Set `FLASK_ENV=production` and `FLASK_DEBUG=0`.
- [ ] Set `SESSION_COOKIE_SECURE=1` when HTTPS is enabled.
- [ ] Attach persistent storage if the host has an ephemeral filesystem.
- [ ] Confirm `/health` returns `{"status":"ok"}`.
- [ ] Configure **Admin → Store Settings** with the real store address/GPS coordinates.
- [ ] Configure **Admin → Payment Settings** with the real payment methods/details.
- [ ] Add the real product catalog, images, prices and stock.
- [ ] Configure Lalamove production credentials only if delivery quotes are required.
- [ ] Configure `GEMINI_API_KEY` only if AI support is required.

## Functional smoke test

- [ ] Homepage/storefront loads on desktop and mobile.
- [ ] Customer registration works.
- [ ] Customer login/logout works and does not redirect to external URLs.
- [ ] Product details, cart, wishlist and Buy Now work.
- [ ] Checkout recalculates price/stock server-side.
- [ ] Payment receipt upload accepts real PNG/JPG/JPEG/WEBP images and rejects invalid files.
- [ ] An order can be created and appears in the admin order list.
- [ ] Admin can update order/payment status.
- [ ] Customer can see only their own orders.
- [ ] Live chat works for customer ↔ admin.
- [ ] Repair request upload works and repair photos remain protected.
- [ ] Admin repair management works.
- [ ] Delivery/location tools work with the configured store location.
- [ ] Accounting dashboard/export works.
- [ ] Product/category/store/payment admin pages work.

## Security smoke test

- [ ] `/orders` requires admin login.
- [ ] `/order/<id>` requires admin login or the owning customer account.
- [ ] `/track-order` requires customer login and only returns that customer's order.
- [ ] `/repair-requests` and repair-status changes require admin login.
- [ ] Repair photos require the owning customer or admin session.
- [ ] Payment receipts require admin login.
- [ ] `.env`, backups, database copies and private uploads are not included in public source control.
- [ ] HTTPS is enabled before sharing the public URL.
- [ ] Production API secrets are newly generated/rotated and are not the local test credentials.
