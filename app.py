
@app.route("/api/chat/send", methods=["POST"])
def chat_send_api():
    """Send a customer/admin chat message. Delivery is committed before any secondary work."""
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

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        if conv_id:
            cur.execute("SELECT * FROM chat_conversations WHERE id=?", (conv_id,))
            conv = cur.fetchone()
            if not conv:
                return jsonify({"success": False, "error": "Conversation not found."}), 404
            if not is_admin and conv["customer_id"] != session.get("customer_id"):
                return jsonify({"success": False, "error": "Forbidden."}), 403
            customer_id = conv["customer_id"]
            order_id = conv["order_id"]
        else:
            if is_admin:
                if not customer_id:
                    return jsonify({"success": False, "error": "Customer is required."}), 400
                cur.execute("SELECT id FROM customers WHERE id=?", (customer_id,))
                if not cur.fetchone():
                    return jsonify({"success": False, "error": "Customer not found."}), 404
            else:
                customer_id = session.get("customer_id")
                if not customer_id:
                    return jsonify({"success": False, "error": "Login required."}), 401

            if order_id is not None:
                cur.execute("SELECT id FROM orders WHERE id=? AND customer_id=?", (order_id, customer_id))
                if not cur.fetchone():
                    return jsonify({"success": False, "error": "Invalid order for customer."}), 403

            cur.execute(
                """SELECT id FROM chat_conversations
                   WHERE customer_id=?
                     AND ((order_id IS NULL AND ? IS NULL) OR order_id=?)
                     AND status='open'
                   ORDER BY id DESC LIMIT 1""",
                (customer_id, order_id, order_id),
            )
            row = cur.fetchone()
            if row:
                conv_id = row["id"]
            else:
                cur.execute(
                    "INSERT INTO chat_conversations(customer_id,order_id) VALUES (?,?)",
                    (customer_id, order_id),
                )
                conv_id = cur.lastrowid

        sender = "admin" if is_admin else "customer"
        cur.execute(
            """INSERT INTO chat_messages
               (customer_id,sender_type,message,is_read,conversation_id,order_id)
               VALUES (?,?,?,?,?,?)""",
            (customer_id, sender, message, 0, conv_id, order_id),
        )
        msg_id = cur.lastrowid

        # This is the only operation that must succeed for Send to succeed.
        # Commit it immediately so Turso latency/stale streams in secondary work
        # can never cause the browser to report a successful message as failed.
        conn.commit()

        # Do NOT perform notification writes in this request. They can involve a
        # second Turso round-trip and make the HTTP response appear to hang even
        # though the message is already stored. The support UI already polls the
        # conversation/message tables, so notification bookkeeping is optional.
        return jsonify({"success": True, "conversation_id": conv_id, "message_id": msg_id}), 200
    except sqlite3.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        app.logger.exception("Chat send failed")
        return jsonify({"success": False, "error": "Message could not be sent. Please try again."}), 500
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        app.logger.exception("Unexpected chat send failure")
        return jsonify({"success": False, "error": "Message could not be sent. Please try again."}), 500
    finally:
        conn.close()
