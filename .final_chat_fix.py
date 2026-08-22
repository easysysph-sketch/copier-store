from pathlib import Path
import re

ROOT = Path('.')
app_path = ROOT / 'app.py'
app = app_path.read_text(encoding='utf-8')

# Replace the three live-chat API handlers as a unit. The new handlers keep
# polling read-only and make message delivery independent from notification and
# timestamp bookkeeping. Stale Turso commits are verified/replayed once.
start = app.index('@app.route("/api/chat/conversations", methods=["GET","POST"])')
end = app.index('@app.route("/admin/accounting", methods=["GET", "POST"])', start)

new_routes = r'''@app.route("/api/chat/conversations", methods=["GET", "POST"])
def chat_conversations_api():
    if _api_rate_limited("chat"):
        return jsonify({"success": False, "error": "Too many chat requests. Please wait a moment."}), 429
    ensure_live_chat_tables()
    is_admin = bool(session.get("admin_logged_in"))

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        if request.method == "GET":
            if not is_admin and not session.get("customer_id"):
                return jsonify({"success": False, "error": "Login required."}), 401

            if is_admin:
                cur.execute("""
                    SELECT c.id, c.customer_id, c.order_id, c.status, c.created_at, c.updated_at,
                           cu.name AS customer_name, cu.email AS customer_email,
                           (SELECT m.message FROM chat_messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_message,
                           (SELECT COUNT(*) FROM chat_messages m2 WHERE m2.conversation_id=c.id AND m2.sender_type='customer' AND m2.is_read=0) AS unread
                    FROM chat_conversations c
                    JOIN customers cu ON cu.id=c.customer_id
                    ORDER BY COALESCE(c.updated_at,c.created_at) DESC, c.id DESC
                    LIMIT 100
                """)
                rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM chat_messages WHERE sender_type='customer' AND is_read=0")
                unread_total = cur.fetchone()[0]
            else:
                cid = session.get("customer_id")
                cur.execute("""
                    SELECT c.id, c.customer_id, c.order_id, c.status, c.created_at, c.updated_at,
                           cu.name AS customer_name, cu.email AS customer_email,
                           (SELECT m.message FROM chat_messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_message,
                           (SELECT COUNT(*) FROM chat_messages m2 WHERE m2.conversation_id=c.id AND m2.sender_type='admin' AND m2.is_read=0) AS unread
                    FROM chat_conversations c
                    JOIN customers cu ON cu.id=c.customer_id
                    WHERE c.customer_id=?
                    ORDER BY COALESCE(c.updated_at,c.created_at) DESC, c.id DESC
                    LIMIT 100
                """, (cid,))
                rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM chat_messages WHERE customer_id=? AND sender_type='admin' AND is_read=0", (cid,))
                unread_total = cur.fetchone()[0]

            return jsonify({"success": True, "conversations": [dict(r) for r in rows], "unread_total": unread_total})

        data = request.get_json(silent=True) or request.form
        requested_customer = data.get("customer_id")
        order_id = data.get("order_id")
        try:
            requested_customer = int(requested_customer) if requested_customer not in (None, "") else None
            order_id = int(order_id) if order_id not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Invalid customer or order."}), 400

        customer_id = requested_customer if is_admin else session.get("customer_id")
        if not customer_id:
            return jsonify({"success": False, "error": "Customer is required."}), 400

        if is_admin:
            cur.execute("SELECT id FROM customers WHERE id=?", (customer_id,))
            if not cur.fetchone():
                return jsonify({"success": False, "error": "Customer not found."}), 404
        elif customer_id != session.get("customer_id"):
            return jsonify({"success": False, "error": "Forbidden."}), 403

        if order_id is not None:
            cur.execute("SELECT id FROM orders WHERE id=? AND customer_id=?", (order_id, customer_id))
            if not cur.fetchone():
                return jsonify({"success": False, "error": "Invalid order for customer."}), 403

        cur.execute("""
            SELECT id FROM chat_conversations
            WHERE customer_id=?
              AND ((order_id IS NULL AND ? IS NULL) OR order_id=?)
              AND status='open'
            ORDER BY id DESC LIMIT 1
        """, (customer_id, order_id, order_id))
        existing = cur.fetchone()
        if existing:
            return jsonify({"success": True, "conversation_id": existing[0]})

        try:
            cur.execute("INSERT INTO chat_conversations(customer_id,order_id) VALUES (?,?)", (customer_id, order_id))
            conv_id = cur.lastrowid
            conn.commit()
        except Exception as exc:
            if "stream not found" not in str(exc).lower():
                raise
            # The INSERT may already have reached Turso even though COMMIT lost
            # its HRANA stream. Reconnect and verify before replaying it.
            try:
                conn.close()
            except Exception:
                pass
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM chat_conversations
                WHERE customer_id=?
                  AND ((order_id IS NULL AND ? IS NULL) OR order_id=?)
                  AND status='open'
                ORDER BY id DESC LIMIT 1
            """, (customer_id, order_id, order_id))
            existing = cur.fetchone()
            if existing:
                conv_id = existing[0]
            else:
                cur.execute("INSERT INTO chat_conversations(customer_id,order_id) VALUES (?,?)", (customer_id, order_id))
                conv_id = cur.lastrowid
                conn.commit()

        return jsonify({"success": True, "conversation_id": conv_id})
    except sqlite3.Error as exc:
        try: conn.rollback()
        except Exception: pass
        app.logger.exception("Chat conversation failure")
        return jsonify({"success": False, "error": "Chat is temporarily unavailable. Please try again."}), 503
    except Exception:
        try: conn.rollback()
        except Exception: pass
        app.logger.exception("Unexpected chat conversation failure")
        return jsonify({"success": False, "error": "Chat is temporarily unavailable. Please try again."}), 503
    finally:
        conn.close()


@app.route("/api/chat/messages")
def chat_messages_api():
    # Polling is deliberately read-only. Do not update read receipts or commit
    # anything here: chat polling must be cheap and cannot block on Turso writes.
    if _api_rate_limited("chat"):
        return jsonify({"success": False, "error": "Too many chat requests. Please wait a moment."}), 429
    ensure_live_chat_tables()
    is_admin = bool(session.get("admin_logged_in"))
    conv_id = request.args.get("conversation_id", type=int)
    requested_customer = request.args.get("customer_id", type=int)
    if not is_admin and not session.get("customer_id"):
        return jsonify({"success": False, "error": "Login required"}), 401

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        if conv_id:
            cur.execute("SELECT * FROM chat_conversations WHERE id=?", (conv_id,))
            conv = cur.fetchone()
            if not conv:
                return jsonify({"success": False, "error": "Conversation not found"}), 404
            if not is_admin and conv["customer_id"] != session.get("customer_id"):
                return jsonify({"success": False, "error": "Forbidden"}), 403
        else:
            cid = requested_customer if is_admin and requested_customer else session.get("customer_id")
            if not cid:
                return jsonify({"success": False, "error": "Conversation required"}), 400
            cur.execute("SELECT * FROM chat_conversations WHERE customer_id=? ORDER BY COALESCE(updated_at,created_at) DESC LIMIT 1", (cid,))
            conv = cur.fetchone()
            if not conv:
                return jsonify({"success": True, "conversation": None, "messages": [], "unread_total": 0})
            conv_id = conv["id"]

        after_id = max(0, request.args.get("after_id", 0, type=int) or 0)
        cur.execute("""
            SELECT id, conversation_id, customer_id, order_id, sender_type, message, is_read, created_at
            FROM chat_messages
            WHERE conversation_id=? AND id>?
            ORDER BY id ASC LIMIT 100
        """, (conv_id, after_id))
        messages = [dict(r) for r in cur.fetchall()]

        recipient = "customer" if is_admin else "admin"
        if is_admin:
            cur.execute("SELECT COUNT(*) FROM chat_messages WHERE sender_type='customer' AND is_read=0")
        else:
            cur.execute("SELECT COUNT(*) FROM chat_messages WHERE customer_id=? AND sender_type='admin' AND is_read=0", (session.get("customer_id"),))
        unread_total = cur.fetchone()[0]

        cur.execute("""
            SELECT c.*, cu.name AS customer_name, cu.email AS customer_email
            FROM chat_conversations c JOIN customers cu ON cu.id=c.customer_id
            WHERE c.id=?
        """, (conv_id,))
        conv_row = cur.fetchone()
        if not conv_row:
            return jsonify({"success": False, "error": "Conversation no longer exists"}), 404
        return jsonify({"success": True, "conversation": dict(conv_row), "messages": messages, "unread_total": unread_total})
    except Exception:
        app.logger.exception("Chat message polling failure")
        return jsonify({"success": False, "error": "Chat is temporarily unavailable. Please refresh and try again."}), 503
    finally:
        conn.close()


@app.route("/api/chat/send", methods=["POST"])
def chat_send_api():
    """Store exactly one chat message and return immediately after its commit."""
    if _api_rate_limited("chat"):
        return jsonify({"success": False, "error": "Too many chat requests. Please wait a moment."}), 429
    ensure_live_chat_tables()
    message = (request.form.get("message") or "").strip()[:1000]
    if not message:
        return jsonify({"success": False, "error": "Message cannot be empty."}), 400

    is_admin = bool(session.get("admin_logged_in"))
    conv_id = request.form.get("conversation_id", type=int)
    customer_id = request.form.get("customer_id", type=int)
    order_id = request.form.get("order_id", type=int)
    sender = "admin" if is_admin else "customer"

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        if conv_id:
            cur.execute("SELECT customer_id, order_id FROM chat_conversations WHERE id=?", (conv_id,))
            conv = cur.fetchone()
            if not conv:
                return jsonify({"success": False, "error": "Conversation not found."}), 404
            if not is_admin and conv["customer_id"] != session.get("customer_id"):
                return jsonify({"success": False, "error": "Forbidden."}), 403
            customer_id = conv["customer_id"]
            order_id = conv["order_id"]
        else:
            customer_id = customer_id if is_admin else session.get("customer_id")
            if not customer_id:
                return jsonify({"success": False, "error": "Login required."}), 401
            if order_id is not None:
                cur.execute("SELECT id FROM orders WHERE id=? AND customer_id=?", (order_id, customer_id))
                if not cur.fetchone():
                    return jsonify({"success": False, "error": "Invalid order for customer."}), 403
            cur.execute("""
                SELECT id, order_id FROM chat_conversations
                WHERE customer_id=? AND ((order_id IS NULL AND ? IS NULL) OR order_id=?) AND status='open'
                ORDER BY id DESC LIMIT 1
            """, (customer_id, order_id, order_id))
            row = cur.fetchone()
            if row:
                conv_id = row["id"]
                order_id = row["order_id"]
            else:
                cur.execute("INSERT INTO chat_conversations(customer_id,order_id) VALUES (?,?)", (customer_id, order_id))
                conv_id = cur.lastrowid

        # The message is the only required write in this request.
        cur.execute("""
            INSERT INTO chat_messages(customer_id,sender_type,message,is_read,conversation_id,order_id)
            VALUES (?,?,?,?,?,?)
        """, (customer_id, sender, message, 0, conv_id, order_id))
        msg_id = cur.lastrowid

        try:
            conn.commit()
        except Exception as exc:
            if "stream not found" not in str(exc).lower():
                raise
            # A failed remote COMMIT is ambiguous. Never blindly duplicate the
            # message. Reconnect, look for the exact just-sent row, and replay
            # only when it is definitely absent.
            try: conn.close()
            except Exception: pass
            conn = sqlite3.connect(DATABASE_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, conversation_id FROM chat_messages
                WHERE conversation_id=? AND customer_id=? AND sender_type=? AND message=?
                ORDER BY id DESC LIMIT 1
            """, (conv_id, customer_id, sender, message))
            existing = cur.fetchone()
            if existing:
                msg_id = existing["id"]
                conv_id = existing["conversation_id"]
            else:
                cur.execute("""
                    INSERT INTO chat_messages(customer_id,sender_type,message,is_read,conversation_id,order_id)
                    VALUES (?,?,?,?,?,?)
                """, (customer_id, sender, message, 0, conv_id, order_id))
                msg_id = cur.lastrowid
                conn.commit()

        # Do NOT perform notification writes, read-receipt writes, timestamp
        # commits, or secondary Turso calls here. The next conversation listing
        # derives its last-message ordering directly from chat_messages.
        return jsonify({"success": True, "conversation_id": conv_id, "message_id": msg_id})
    except sqlite3.Error:
        try: conn.rollback()
        except Exception: pass
        app.logger.exception("Chat send failed")
        return jsonify({"success": False, "error": "Message could not be sent. Please try again."}), 503
    except Exception:
        try: conn.rollback()
        except Exception: pass
        app.logger.exception("Unexpected chat send failure")
        return jsonify({"success": False, "error": "Message could not be sent. Please try again."}), 503
    finally:
        conn.close()

'''
app = app[:start] + new_routes + app[end:]
app_path.write_text(app, encoding='utf-8')

# Reduce browser polling pressure and, importantly, stop the poll handler from
# recursively fetching the conversation list on every message poll.
for rel in ['templates/admin_messages.html', 'templates/live_chat.html']:
    p = ROOT / rel
    if not p.exists():
        continue
    s = p.read_text(encoding='utf-8')
    s = s.replace('await conversations();renderActive()', 'renderActive()')
    s = s.replace('await loadConversations();renderActive()', 'renderActive()')
    s = s.replace("setInterval(conversations,2500);setInterval(populateCustomers,10000);setInterval(()=>load(),2000);", "setInterval(conversations,6000);setInterval(populateCustomers,30000);setInterval(()=>load(),3500);")
    s = s.replace("setInterval(loadConversations,2500);setInterval(()=>loadMessages(),2000);", "setInterval(loadConversations,6000);setInterval(()=>loadMessages(),3500);")
    p.write_text(s, encoding='utf-8')

# Ensure the production start command is not stuck on a single-threaded-ish
# development-style Waitress setting. Keep compatibility with the existing
# Render setup by only changing the Procfile; Render may still have a manual
# command, which can be changed later if desired.
proc = ROOT / 'Procfile'
if proc.exists():
    proc.write_text('web: gunicorn --workers 2 --threads 4 --timeout 60 --access-logfile - --error-logfile - wsgi:app\n', encoding='utf-8')
