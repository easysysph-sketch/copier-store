"""
CopierStore - Reset test/demo data

Run this ONCE against your local orders.db before going live.
It removes customer/order/repair/chat/notification/accounting test data,
while preserving products, store settings, and payment settings.

Usage:
    py reset_test_data.py
"""

from pathlib import Path
import sqlite3
import shutil

BASE = Path(__file__).resolve().parent
DB = BASE / "orders.db"
PRIVATE_UPLOADS = BASE / "private_uploads"
PUBLIC_UPLOADS = BASE / "static" / "uploads"

if not DB.exists():
    print("No orders.db found. Nothing to clean.")
    raise SystemExit(0)

# Children first, then parent/customer/order records.
TABLES = [
    "accounting_lines",
    "accounting_transactions",
    "accounting_expenses",
    "order_items",
    "notifications",
    "admin_notifications",
    "chat_messages",
    "chat_conversations",
    "customer_addresses",
    "wishlist",
    "recently_viewed",
    "repair_requests",
    "orders",
    "customers",
    "automation_runs",
    "automation_alert_state",
    "security_audit_log",
    "reviews",
    "admin_credentials",
]

with sqlite3.connect(DB) as conn:
    conn.execute("PRAGMA foreign_keys = OFF")
    existing = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }

    counts = {}
    for table in TABLES:
        if table in existing:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            conn.execute(f"DELETE FROM [{table}]")

    # Reset AUTOINCREMENT counters for the cleaned transactional tables.
    if "sqlite_sequence" in {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }:
        for table in TABLES:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

    conn.commit()

# Remove test/private uploaded files. Do not remove the directories themselves.
removed_files = 0
for root in (PRIVATE_UPLOADS, PUBLIC_UPLOADS):
    if not root.exists():
        continue
    for item in root.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed_files += 1
        except OSError as exc:
            print(f"Warning: could not remove {item}: {exc}")

print("\nCopierStore test data reset complete.\n")
print("Cleared records:")
for table, count in counts.items():
    print(f"  {table}: {count}")
print(f"Removed upload folders/files: {removed_files}")
print("\nPreserved: products, store settings, payment settings, and app code.")
print("Admin login is environment-based, so it is not deleted by this reset.")
