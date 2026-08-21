# CopierStore Catalog Upgrade

This version keeps the existing working storefront/login/order system and adds optional catalog organization:

- Category -> Subcategory
- Brand
- Model
- Customer subcategory and brand filters
- Search now matches name, category, subcategory, brand, and model
- Product cards/details show the new fields when provided

Existing products remain valid because the new fields are nullable. Startup migration only adds missing columns/table and seeds default subcategories; it does not delete products or orders.

## Suggested first data entry
When editing products, fill Brand and Model for copier/printer items. Choose a Subcategory when useful.
