"""Fast, stateless live-chat backend for CopierStore.

The normal application uses Python libsql connections. Live chat is unusually
sensitive to idle Hrana stream expiry because browsers poll it repeatedly. This
module uses Turso's stateless HTTP v2 pipeline for chat only: each request gets a
fresh HTTP call and explicitly closes the stream, so chat never depends on a
long-lived HRANA stream.
"""
import json
import os
import urllib.request
import urllib.error
from flask import request, session, jsonify


def _cfg():
    url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
    token = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    url = url.rstrip("/")
    if not url:
        raise RuntimeError("TURSO_DATABASE_URL is not configured")
    if not token:
        raise RuntimeError("TURSO_AUTH_TOKEN is not configured")
    return url + "/v2/pipeline", token


def _val(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def _decode(v):
    if not isinstance(v, dict):
        return v
    t = v.get("type")
    if t == "null": return None
    if t == "integer":
        try: return int(v.get("value", 0))
        except Exception: return v.get("value")
    if t == "float": return v.get("value")
    if t == "text": return v.get("value", "")
    return v.get("value")


def _execute(sql, args=(), want_rows=True):
    endpoint, token = _cfg()
    stmt = {
        "sql": sql,
        "args": [_val(x) for x in args],
        "want_rows": bool(want_rows),
    }
    body = json.dumps({"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"]}).encode()
    req = urllib.request.Request(endpoint, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    })
    with urllib.request.urlopen(req, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = payload.get("results") or []
    if not results:
        raise RuntimeError("Turso returned no result")
    first = results[0]
    if first.get("type") == "error":
        err = first.get("error") or {}
        raise RuntimeError(err.get("message") or str(err))
    return first.get("response", {}).get("result", {})


def _rows(result):
    cols = [c.get("name") for c in result.get("cols", [])]
    return [dict(zip(cols, [_decode(v) for v in row])) for row in result.get("rows", [])]


def _one(sql, args=()):
    rows = _rows(_execute(sql, args, True))
    return rows[0] if rows else None


def _scalar(sql, args=()):
    row = _one(sql, args)
    if not row: return 0
    return next(iter(row.values()))


def _last_id(result):
    value = result.get("last_insert_rowid")
    if value is None: return None
    try: return int(value)
    except Exception: return value


def _auth(is_admin=False):
    if is_admin:
        return True
    return bool(session.get("customer_id"))


def conversations():
    is_admin = bool(session.get("admin_logged_in"))
    if not _auth(is_admin):
        return jsonify({"success": False, "error": "Login required."}), 401
    if is_admin:
        rows = _rows(_execute("""SELECT c.id,c.customer_id,c.order_id,c.status,c.created_at,c.updated_at,
            cu.name customer_name,cu.email customer_email,
            (SELECT m.message FROM chat_messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) last_message,
            (SELECT COUNT(*) FROM chat_messages m2 WHERE m2.conversation_id=c.id AND m2.sender_type='customer' AND m2.is_read=0) unread
            FROM chat_conversations c JOIN customers cu ON cu.id=c.customer_id
            ORDER BY COALESCE(c.updated_at,c.created_at) DESC,c.id DESC LIMIT 100"""))
        unread = _scalar("SELECT COUNT(*) AS n FROM chat_messages WHERE sender_type='customer' AND is_read=0")
    else:
        cid = session["customer_id"]
        rows = _rows(_execute("""SELECT c.id,c.customer_id,c.order_id,c.status,c.created_at,c.updated_at,
            cu.name customer_name,cu.email customer_email,
            (SELECT m.message FROM chat_messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) last_message,
            (SELECT COUNT(*) FROM chat_messages m2 WHERE m2.conversation_id=c.id AND m2.sender_type='admin' AND m2.is_read=0) unread
            FROM chat_conversations c JOIN customers cu ON cu.id=c.customer_id
            WHERE c.customer_id=? ORDER BY COALESCE(c.updated_at,c.created_at) DESC,c.id DESC LIMIT 100""", (cid,)))
        unread = _scalar("SELECT COUNT(*) AS n FROM chat_messages WHERE customer_id=? AND sender_type='admin' AND is_read=0", (cid,))
    return jsonify({"success": True, "conversations": rows, "unread_total": unread})


def create_conversation():
    is_admin = bool(session.get("admin_logged_in"))
    if not _auth(is_admin):
        return jsonify({"success": False, "error": "Login required."}), 401
    data = request.get_json(silent=True) or request.form
    try:
        requested_customer = data.get("customer_id")
        order_id = data.get("order_id")
        customer_id = int(requested_customer) if is_admin and requested_customer not in (None, "") else session.get("customer_id")
        order_id = int(order_id) if order_id not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid customer or order."}), 400
    if not customer_id:
        return jsonify({"success": False, "error": "Customer is required."}), 400
    if is_admin:
        if not _one("SELECT id FROM customers WHERE id=?", (customer_id,)):
            return jsonify({"success": False, "error": "Customer not found."}), 404
    if order_id is not None and not _one("SELECT id FROM orders WHERE id=? AND customer_id=?", (order_id, customer_id)):
        return jsonify({"success": False, "error": "Invalid order for customer."}), 403
    existing = _one("""SELECT id FROM chat_conversations
        WHERE customer_id=? AND ((order_id IS NULL AND ? IS NULL) OR order_id=?)
        AND status='open' ORDER BY id DESC LIMIT 1""", (customer_id, order_id, order_id))
    if existing:
        return jsonify({"success": True, "conversation_id": existing["id"]})
    result = _execute("INSERT INTO chat_conversations(customer_id,order_id) VALUES (?,?)", (customer_id, order_id), False)
    conv_id = _last_id(result)
    # Some Turso configurations return a null rowid for remote writes; verify.
    if conv_id is None:
        existing = _one("""SELECT id FROM chat_conversations
            WHERE customer_id=? AND ((order_id IS NULL AND ? IS NULL) OR order_id=?)
            AND status='open' ORDER BY id DESC LIMIT 1""", (customer_id, order_id, order_id))
        conv_id = existing["id"] if existing else None
    return jsonify({"success": True, "conversation_id": conv_id})


def messages():
    is_admin = bool(session.get("admin_logged_in"))
    if not _auth(is_admin):
        return jsonify({"success": False, "error": "Login required"}), 401
    conv_id = request.args.get("conversation_id", type=int)
    requested_customer = request.args.get("customer_id", type=int)
    if not conv_id:
        cid = requested_customer if is_admin and requested_customer else session.get("customer_id")
        if not cid:
            return jsonify({"success": False, "error": "Conversation required"}), 400
        conv = _one("SELECT * FROM chat_conversations WHERE customer_id=? ORDER BY COALESCE(updated_at,created_at) DESC LIMIT 1", (cid,))
        if not conv:
            return jsonify({"success": True, "conversation": None, "messages": [], "unread_total": 0})
        conv_id = conv["id"]
    else:
        conv = _one("SELECT * FROM chat_conversations WHERE id=?", (conv_id,))
        if not conv:
            return jsonify({"success": False, "error": "Conversation not found"}), 404
        if not is_admin and conv["customer_id"] != session.get("customer_id"):
            return jsonify({"success": False, "error": "Forbidden"}), 403
    after_id = max(0, request.args.get("after_id", 0, type=int) or 0)
    rows = _rows(_execute("""SELECT id,conversation_id,customer_id,order_id,sender_type,message,is_read,created_at
        FROM chat_messages WHERE conversation_id=? AND id>? ORDER BY id ASC LIMIT 100""", (conv_id, after_id)))
    conv = _one("""SELECT c.*,cu.name customer_name,cu.email customer_email
        FROM chat_conversations c JOIN customers cu ON cu.id=c.customer_id WHERE c.id=?""", (conv_id,))
    if is_admin:
        unread = _scalar("SELECT COUNT(*) AS n FROM chat_messages WHERE sender_type='customer' AND is_read=0")
    else:
        unread = _scalar("SELECT COUNT(*) AS n FROM chat_messages WHERE customer_id=? AND sender_type='admin' AND is_read=0", (session.get("customer_id"),))
    return jsonify({"success": True, "conversation": conv, "messages": rows, "unread_total": unread})


def send():
    is_admin = bool(session.get("admin_logged_in"))
    if not _auth(is_admin):
        return jsonify({"success": False, "error": "Login required."}), 401
    message = (request.form.get("message") or "").strip()[:1000]
    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400
    conv_id = request.form.get("conversation_id", type=int)
    customer_id = request.form.get("customer_id", type=int) if is_admin else session.get("customer_id")
    order_id = request.form.get("order_id", type=int)
    sender = "admin" if is_admin else "customer"
    if conv_id:
        conv = _one("SELECT customer_id,order_id FROM chat_conversations WHERE id=?", (conv_id,))
        if not conv:
            return jsonify({"success": False, "error": "Conversation not found."}), 404
        if not is_admin and conv["customer_id"] != session.get("customer_id"):
            return jsonify({"success": False, "error": "Forbidden."}), 403
        customer_id, order_id = conv["customer_id"], conv["order_id"]
    else:
        if not customer_id:
            return jsonify({"success": False, "error": "Customer is required."}), 400
        if order_id is not None and not _one("SELECT id FROM orders WHERE id=? AND customer_id=?", (order_id, customer_id)):
            return jsonify({"success": False, "error": "Invalid order for customer."}), 403
        conv = _one("""SELECT id,order_id FROM chat_conversations
            WHERE customer_id=? AND ((order_id IS NULL AND ? IS NULL) OR order_id=?) AND status='open'
            ORDER BY id DESC LIMIT 1""", (customer_id, order_id, order_id))
        if conv:
            conv_id, order_id = conv["id"], conv["order_id"]
        else:
            result = _execute("INSERT INTO chat_conversations(customer_id,order_id) VALUES (?,?)", (customer_id, order_id), False)
            conv_id = _last_id(result)
            if conv_id is None:
                conv = _one("""SELECT id,order_id FROM chat_conversations
                    WHERE customer_id=? AND ((order_id IS NULL AND ? IS NULL) OR order_id=?) AND status='open'
                    ORDER BY id DESC LIMIT 1""", (customer_id, order_id, order_id))
                conv_id = conv["id"] if conv else None
    result = _execute("""INSERT INTO chat_messages(customer_id,sender_type,message,is_read,conversation_id,order_id)
        VALUES (?,?,?,?,?,?)""", (customer_id, sender, message, 0, conv_id, order_id), False)
    msg_id = _last_id(result)
    if msg_id is None:
        row = _one("""SELECT id FROM chat_messages WHERE conversation_id=? AND customer_id=?
            AND sender_type=? AND message=? ORDER BY id DESC LIMIT 1""", (conv_id, customer_id, sender, message))
        msg_id = row["id"] if row else None
    return jsonify({"success": True, "conversation_id": conv_id, "message_id": msg_id})


def apply(app):
    # Replace the existing Flask view functions without changing the URL map.
    # This keeps every existing template/route URL intact while moving only
    # live-chat traffic onto stateless Turso HTTP.
    app.view_functions["chat_conversations_api"] = conversations
    app.view_functions["chat_messages_api"] = messages
    app.view_functions["chat_send_api"] = send
