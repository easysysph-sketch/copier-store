COPIERSTORE CATALOG + STORE FEATURES PATCH

This patch is intentionally additive/conservative. It does not delete products, orders, customers, wishlist data, reviews, or existing categories.

Added:
- Admin product Brand, Model, and Compatible Models fields.
- Homepage search across product name, category, subcategory, brand, model, and compatible models.
- Homepage category + subcategory + brand filters.
- Default copier/printer/toner/parts/office-supply subcategories are seeded with INSERT OR IGNORE.
- Product specification panel and compatible-model display.
- Review average/count summary and related-product recommendations.
- In-stock / low-stock / out-of-stock presentation.
- Save for Later cart actions.
- Visual order tracking timeline.
- About Store page with store details/gallery.
- Repair Service entry points (the existing repair workflow is preserved).
- Read-only Supplier Portal at /supplier-login and /supplier-dashboard.
- Wishlist redirect fix: wishlist toggle now has the required url_for import and returns the customer to the product/wishlist instead of raw JSON.
- Category deletion route is preserved alongside subcategory add/edit/delete.

IMPORTANT ENVIRONMENT VARIABLES FOR SUPPLIER PORTAL:
SUPPLIER_NAME=Main Supplier
SUPPLIER_USERNAME=...
SUPPLIER_PASSWORD=...
SUPPLIER_COMMISSION_RATE=...

Set the commission rate only after the supplier/store owner agrees on the percentage.

DEPLOY:
1. Replace the local project folder with this patched folder.
2. Keep your current .env / Render environment variables; do not commit secrets.
3. Run: git status
4. Run: git add .
5. Run: git commit -m "Add catalog filters and store features"
6. Run: git push origin main
7. Wait for Render to finish deploying.

The startup migration is additive and also runs on Turso when the legacy core schema already exists, so the new product fields do not require deleting or recreating the database.
