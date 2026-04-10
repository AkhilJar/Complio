from flask import request, jsonify
from config import app, openai_client, MAX_HISTORY
from database import query, insert_returning


# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
# BUSINESS
# ─────────────────────────────────────────────

@app.route("/api/business", methods=["POST"])
def create_business():
    """
    If a business already exists return it (MVP supports one business).
    Otherwise validate the body and create a new one.
    """
    existing = query("SELECT * FROM businesses LIMIT 1", fetch="one")
    if existing:
        return jsonify(dict(existing))

    data = request.json or {}

    required = ["name", "industry", "state", "business_type", "employee_count"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"{field} is required"}), 400

    business = insert_returning(
        """INSERT INTO businesses (name, industry, state, business_type, employee_count)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING *""",
        (data["name"], data["industry"], data["state"],
         data["business_type"], int(data["employee_count"]))
    )
    return jsonify(dict(business)), 201  # 201 = Created


@app.route("/api/business", methods=["GET"])
def get_business():
    """Returns the current business profile, or null if none exists."""
    business = query("SELECT * FROM businesses LIMIT 1", fetch="one")
    return jsonify(dict(business) if business else None)


@app.route("/api/business/<business_id>", methods=["PUT"])
def update_business(business_id):
    """Updates any subset of business fields sent in the request body."""
    data    = request.json or {}
    allowed = ["name", "industry", "state", "business_type", "employee_count"]

    # Build "col = %s" pairs only for fields that were actually sent.
    updates = [f"{f} = %s" for f in allowed if f in data]
    values  = [data[f] for f in allowed if f in data]

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    values.append(business_id)  # goes into the WHERE id = %s placeholder

    # f-string is safe here — `updates` comes from our hardcoded `allowed`
    # list, never from user input, so there is no injection risk.
    business = insert_returning(
        f"UPDATE businesses SET {', '.join(updates)} WHERE id = %s RETURNING *",
        tuple(values)
    )
    if not business:
        return jsonify({"error": "Business not found"}), 404
    return jsonify(dict(business))


# ─────────────────────────────────────────────
# MESSAGES
# ─────────────────────────────────────────────

@app.route("/api/messages/<business_id>", methods=["GET"])
def get_messages(business_id):
    """Returns all messages for a business in chronological order."""
    messages = query(
        "SELECT * FROM messages WHERE business_id = %s ORDER BY created_at ASC",
        (business_id,)
    )
    return jsonify([dict(m) for m in messages])


@app.route("/api/messages/<business_id>", methods=["DELETE"])
def clear_messages(business_id):
    """Deletes all messages for a business."""
    query("DELETE FROM messages WHERE business_id = %s", (business_id,), fetch=None)
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# CHAT
# ─────────────────────────────────────────────

@app.route("/api/chat/<business_id>", methods=["POST"])
def chat(business_id):
    """
    Receives a user message, calls OpenAI with business context +
    conversation history, saves both messages to the DB, returns the reply.
    """
    # 1. Load business
    business = query("SELECT * FROM businesses WHERE id = %s", (business_id,), fetch="one")
    if not business:
        return jsonify({"error": "Business not found"}), 404

    # 2. Validate body
    message = (request.json or {}).get("message", "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    # 3. Load recent history from DB
    # Slicing with [-MAX_HISTORY:] keeps only the last N items in the list.
    history = query(
        "SELECT role, content FROM messages WHERE business_id = %s ORDER BY created_at ASC",
        (business_id,)
    )
    recent = list(history)[-MAX_HISTORY:]

    # 4. Build system prompt — injected once at the top of every API call.
    # The AI reads this as background context for the whole conversation.
    system_prompt = f"""You are a knowledgeable legal and compliance assistant \
for small business owners in the United States.
Provide clear, practical, specific guidance on business law, \
employment law, and regulatory compliance.

Always tailor your answers to this specific business.
Be direct — owners need actionable information.
When a situation requires a licensed attorney, say so at the end,
but give as much useful information as you can first.

BUSINESS CONTEXT:
Name:           {business['name']}
Industry:       {business['industry']}
State:          {business['state']}
Business Type:  {business['business_type']}
Employees:      {business['employee_count']}"""

    # 5. Build the messages array for the OpenAI API.
    # Format: [system, ...history, new user message]
    messages_for_api = [{"role": "system", "content": system_prompt}]
    for row in recent:
        messages_for_api.append({"role": row["role"], "content": row["content"]})
    messages_for_api.append({"role": "user", "content": message})

    # 6. Call OpenAI
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_for_api,
            max_tokens=1000,
            temperature=0.3  # low = more consistent; high = more creative
        )
        reply = response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI error: {e}")
        return jsonify({"error": "AI service error, please try again"}), 500

    # 7. Persist both messages.
    # We save AFTER the AI responds so a failed API call leaves no orphan messages.
    insert_returning(
        "INSERT INTO messages (business_id, role, content) VALUES (%s, %s, %s) RETURNING *",
        (business_id, "user", message)
    )
    insert_returning(
        "INSERT INTO messages (business_id, role, content) VALUES (%s, %s, %s) RETURNING *",
        (business_id, "assistant", reply)
    )

    # 8. Return the reply
    return jsonify({"reply": reply})
