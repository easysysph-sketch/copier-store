from app import app

# Live chat uses a stateless Turso HTTP pipeline instead of long-lived libsql
# HRANA streams. This prevents idle-stream expiry from blocking chat requests.
try:
    from chat_patch import apply as _apply_chat_patch
    _apply_chat_patch(app)
except Exception:
    # Do not prevent the whole storefront from booting if the optional chat
    # patch cannot initialize; the normal Flask routes remain available.
    import logging
    logging.getLogger(__name__).exception("Live chat patch initialization failed")

__all__ = ["app"]
