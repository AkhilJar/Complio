from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv
import os
from database import query, insert_returning

load_dotenv()

app = Flask(__name__)

# CORS explanation:
# Browsers enforce a security rule: a webpage at localhost:5173
# cannot make requests to localhost:5000 unless the server explicitly allows it.
# This is called the Same-Origin Policy.
# CORS (Cross-Origin Resource Sharing) is how the server grants permission.
# We only allow our frontend origin — not the entire internet.
CORS(app, origins=["http://localhost:5173"])

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# How many recent messages to send to OpenAI each request.
# A "token" is roughly 4 characters. OpenAI charges per token.
# Sending 100 messages costs much more than sending 20.
# 20 messages gives enough context for any reasonable follow-up chain.
# gpt-4o-mini supports 128k tokens total — the max it can "see" at once
# across system prompt + history + response.
MAX_HISTORY = 20


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    """Simple route to confirm the server is running."""
    return jsonify({"status": "ok"})


# ─────────────────────────────────────────────
# BUSINESS ROUTES
# ─────────────────────────────────────────────

@app.route("/api/business", methods=["POST"])
def create_business():
    """
    Creates or returns the business profile.

    For MVP: if a business already exists, return it.
    Otherwise validate the body and create a new one.

    Sprint 2 will add auth so each user has their own business.
    For now we support exactly one business globally.
    """
    # Check if any business already exists.
    # LIMIT 1 stops scanning after the first row — efficient.
    existing = query("SELECT * FROM businesses LIMIT 1", fetch="one")
    if existing:
        # Business already set up — return it so the frontend can skip the form.
        return jsonify(dict(existing))

    data = request.json or {}

    # Validate that all required fields are present.
    required = ["name", "industry", "state", "business_type", "employee_count"]
    for field in required:
        if not data.get(field):
            # 400 = Bad Request — the client sent incomplete data.
            return jsonify({"error": f"{field} is required"}), 400

    name           = data["name"]
    industry       = data["industry"]
    state          = data["state"]
    business_type  = data["business_type"]
    employee_count = int(data["employee_count"])

    # RETURNING * gives us the full inserted row including the generated UUID.
    business = insert_returning(
        """INSERT INTO businesses (name, industry, state, business_type, employee_count)
           VALUES (%s, %s, %s, %s, %s)
           RETURNING *""",
        (name, industry, state, business_type, employee_count)
    )

    # 201 = Created. Use 201 when a new resource was made, not 200 (OK).
    return jsonify(dict(business)), 201


@app.route("/api/business", methods=["GET"])
def get_business():
    """
    Returns the current business profile, or null if none exists.
    The frontend calls this on page load to decide which screen to show.
    """
    business = query("SELECT * FROM businesses LIMIT 1", fetch="one")
    if not business:
        # jsonify(None) returns the JSON literal null.
        return jsonify(None)
    return jsonify(dict(business))


@app.route("/api/business/<business_id>", methods=["PUT"])
def update_business(business_id):
    """
    Updates any subset of the business profile fields.

    We build the SET clause dynamically so the client only has to
    send the fields they want to change, not the entire record.
    """
    data = request.json or {}

    # Only allow updating these specific fields — nothing else.
    allowed = ["name", "industry", "state", "business_type", "employee_count"]

    # Build a list of "field = %s" pairs for only the fields that were sent.
    updates = []
    values  = []
    for field in allowed:
        if field in data:
            updates.append(f"{field} = %s")
            values.append(data[field])

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    # Append the business_id at the end — it becomes the %s in WHERE.
    values.append(business_id)

    # ", ".join builds "name = %s, industry = %s" etc.
    sql = f"UPDATE businesses SET {', '.join(updates)} WHERE id = %s RETURNING *"

    business = insert_returning(sql, tuple(values))
    if not business:
        return jsonify({"error": "Business not found"}), 404

    return jsonify(dict(business))


# ─────────────────────────────────────────────
# MESSAGE ROUTES
# ─────────────────────────────────────────────

@app.route("/api/messages/<business_id>", methods=["GET"])
def get_messages(business_id):
    """
    Returns all messages for a business in chronological order.
    Called on page load to restore conversation history from the DB.
    """
    messages = query(
        "SELECT * FROM messages WHERE business_id = %s ORDER BY created_at ASC",
        (business_id,)  # trailing comma makes this a tuple, not just parentheses
    )
    # Convert each RealDictRow to a plain dict for JSON serialization.
    return jsonify([dict(m) for m in messages])


@app.route("/api/messages/<business_id>", methods=["DELETE"])
def clear_messages(business_id):
    """Deletes all messages for a business. Useful for starting a fresh chat."""
    query(
        "DELETE FROM messages WHERE business_id = %s",
        (business_id,),
        fetch=None  # DELETE returns no rows
    )
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# CHAT ROUTE
# ─────────────────────────────────────────────

@app.route("/api/chat/<business_id>", methods=["POST"])
def chat(business_id):
    """
    The core route. Receives a user message, sends it to OpenAI with
    business context and conversation history, saves both the user message
    and AI reply to the DB, and returns the AI reply.
    """
    # ── Step 1: Load business from DB ──────────────────────────────────
    business = query(
        "SELECT * FROM businesses WHERE id = %s",
        (business_id,),
        fetch="one"
    )
    if not business:
        return jsonify({"error": "Business not found"}), 404

    # ── Step 2: Validate request body ──────────────────────────────────
    message = (request.json or {}).get("message", "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    # ── Step 3: Load recent message history from DB ────────────────────
    # We load from the DB rather than having the frontend send history.
    # The DB is the source of truth — if the user opens a new tab,
    # the history loaded from DB is complete and consistent.
    history = query(
        """SELECT role, content FROM messages
           WHERE business_id = %s
           ORDER BY created_at ASC""",
        (business_id,)
    )
    # Limit to the most recent MAX_HISTORY messages to control token costs.
    recent = list(history)[-MAX_HISTORY:]

    # ── Step 4: Build system prompt with business context ──────────────
    # The system prompt is permanent background for the whole conversation.
    # The AI treats it as ground truth and references it in every reply.
    # We put business info here (not in the first user message) so the AI
    # never "forgets" it even after many conversation turns.
    system_prompt = f"""You are a knowledgeable legal and compliance assistant \
for small business owners in the United States.
Provide clear, practical, specific guidance on business law, \
employment law, and regulatory compliance.

Always tailor your answers to this specific business.
Be direct — owners need actionable information.
When a situation requires a licensed attorney, say so clearly \
at the end of your response, but still give as much useful \
information as you can first.

BUSINESS CONTEXT:
Name:           {business['name']}
Industry:       {business['industry']}
State:          {business['state']}
Business Type:  {business['business_type']}
Employees:      {business['employee_count']}"""

    # ── Step 5: Build messages array for OpenAI ────────────────────────
    # This array structure is the OpenAI Chat Completions format:
    #   "system"    — instructions to the AI, not shown in conversation
    #   "user"      — messages from the human
    #   "assistant" — previous AI replies (lets the AI maintain continuity)
    messages_for_api = [{"role": "system", "content": system_prompt}]

    for row in recent:
        messages_for_api.append({"role": row["role"], "content": row["content"]})

    # Append the new user message last.
    messages_for_api.append({"role": "user", "content": message})

    # ── Step 6: Call OpenAI ────────────────────────────────────────────
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_for_api,
            max_tokens=1000,
            # temperature 0.0 = always same answer (deterministic)
            # temperature 1.0 = very creative, unpredictable
            # temperature 0.3 = mostly consistent with natural phrasing variation
            # Legal questions need accuracy over creativity — keep this low.
            temperature=0.3
        )
        reply = response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI error: {e}")
        return jsonify({"error": "AI service error, please try again"}), 500

    # ── Step 7: Save both messages to DB ──────────────────────────────
    # WHY save after OpenAI responds, not before?
    # If OpenAI fails, we do not want a user message saved with no AI reply.
    # The pair should either both exist or neither exist.
    # (A proper implementation wraps both inserts in a transaction — Sprint 2.)
    insert_returning(
        "INSERT INTO messages (business_id, role, content) VALUES (%s, %s, %s) RETURNING *",
        (business_id, "user", message)
    )
    insert_returning(
        "INSERT INTO messages (business_id, role, content) VALUES (%s, %s, %s) RETURNING *",
        (business_id, "assistant", reply)
    )

    # ── Step 8: Return the reply ───────────────────────────────────────
    return jsonify({"reply": reply})


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # FLASK_DEBUG=1 in .env enables auto-reload on file save and detailed errors.
    # Never run debug=True in production — it exposes an interactive debugger.
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=5001)
