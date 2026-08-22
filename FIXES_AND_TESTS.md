# CopierStore — Fixes and Verification

## Fixed

- Fixed storefront category filtering so dynamic/custom categories match the products' actual `category` values instead of only the old hard-coded category map.
- Fixed dynamic subcategory markup on the storefront (the generated `All` button had malformed HTML).
- Fixed subcategory database compatibility: older databases can now receive the missing `category` column safely, and fresh databases seed the standard subcategories.
- Fixed product creation so the selected subcategory is actually saved to `products.subcategory` and validated against the selected category.
- Fixed product editing so subcategories can be viewed, changed, validated, and saved.
- Fixed product detail URLs by using stable numeric product IDs for new links.
- Kept a legacy `/product/<path:product_name>` route so old product-name links containing spaces or `/` continue to work instead of returning 404.
- Fixed product review links to use product IDs while preserving legacy review URLs.
- Fixed customer/order delivery-status API used by customer order and tracking pages.
- Fixed customer order delivery-status JavaScript so Manual Courier polling is no longer incorrectly nested inside the Lalamove-only block.
- Preserved the existing checkout design: Standard Delivery is NOT a customer-facing option. Restored Lalamove as the checkout default and kept Manual Courier as the other customer-facing delivery option. Legacy Standard Delivery values remain supported only for existing/legacy orders.
- Added compatibility aliases for `/supplier-login` and `/supplier-dashboard`.
- Made public/private upload folders absolute to the application root, reducing path failures when the process working directory differs.
- Added graceful image fallbacks so missing product image files no longer display broken-image icons/alt text throughout the storefront/product/wishlist/dashboard views.

## Verification performed

- Python compile check: `app.py`, `wsgi.py`, and `reset_test_data.py` compile successfully.
- Jinja template parse: all 44 HTML templates parse successfully with zero template-syntax errors.
- JavaScript syntax check: all 25 inline script blocks pass Node.js syntax checking.
- SQL INSERT placeholder scan: all detected INSERT statements have matching column/value counts.
- Catalog SQL smoke test: storefront/admin category and subcategory queries execute successfully against the included SQLite database.
- Exact subcategory migration smoke test: fresh/older database migration creates the required columns and seeds 27 standard subcategories successfully.
- Exact product INSERT smoke test: product rows with category + subcategory insert successfully in a migrated database.
- Storefront render smoke test: dynamic category/subcategory data, product ID links, and image fallback markup render successfully.
- Product-page render smoke test: product-ID review links and missing-image fallback render successfully.
- Filter logic smoke test: a custom category such as `Printer Supplies / Toner / Ink` matches its products; toner powder does not incorrectly match reset-chip or blade products.
- Legacy product URL smoke test: product names containing `/` are compatible with the new path-based legacy route.

## Important deployment note

The deployment package does not contain the live Render/Turso product database or any external persistent product images. If the deployed database contains image filenames but the corresponding files in `static/uploads/` were lost because the host filesystem is ephemeral, the code now shows a safe fallback instead of a broken image, but the original image files must still be restored/re-uploaded and persistent storage should be configured for `static/uploads/`.

## Live-server limitation

A full browser/live HTTP test could not be executed inside this analysis environment because the uploaded project requires Flask/libsql/etc. and those Python packages are not installed in the isolated runtime; outbound package installation is unavailable here. The verification above therefore covers syntax, template compilation, route/link consistency, database migration/SQL behavior, rendered-template smoke tests, and client-side JavaScript syntax/logic rather than claiming a live Render deployment test.


## Follow-up review submission fix
- Fixed the review POST route ambiguity where Flask could match the legacy `<path:product_name>` route for numeric product IDs such as `/product/3/review`.
- Product pages and review submissions now use one `<path:product_ref>` route and resolve numeric references as product IDs first, while preserving legacy name-based URLs.
- Added validation for missing/invalid ratings so malformed review forms return a controlled 400 instead of a server exception.
- Recompiled `app.py` successfully after the change.

## Additional Fix — Guest Cart / Purchase Protection

- `/add-to-cart` now returns HTTP 401 with `{login_required: true}` for AJAX requests from unauthenticated visitors instead of redirecting to the login page and allowing the frontend to mistake the redirect as a successful add.
- Public storefront product cards now show **Login to Purchase** instead of Add to Cart / Buy Now when no customer session exists.
- The storefront JavaScript explicitly detects the 401 login-required response and redirects to `/customer-login` without showing an “Added to cart” success message.
- Normal non-AJAX POSTs remain protected by the server-side login redirect.
- Buy Now is also hidden for guests on the public storefront, and the existing backend authentication guard remains authoritative.
