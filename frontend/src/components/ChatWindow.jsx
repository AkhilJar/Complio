import { useState, useEffect, useRef } from "react"

// ChatWindow is shown after the business profile is set up.
//
// Props:
//   business — the business object from the DB (has .id, .name, .industry, etc.)
//   onReset  — called when user clicks "New Business", takes them back to the form
//   API      — base URL of the Flask backend (e.g. "http://localhost:5000")
export default function ChatWindow({ business, onReset, API }) {
  const [messages, setMessages] = useState([])
  const [input, setInput]       = useState("")
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  // useRef creates a reference to a DOM element.
  // We attach it to an invisible div at the bottom of the message list.
  // Calling bottomRef.current.scrollIntoView() scrolls the page down to it.
  const bottomRef = useRef(null)

  // On mount: load conversation history from the DB.
  // This is why we persist to PostgreSQL — if the user refreshes the page,
  // the conversation is still here. React state alone would be wiped.
  useEffect(() => {
    fetch(`${API}/api/messages/${business.id}`)
      .then((res) => res.json())
      .then((data) => setMessages(data))
      .catch(() => {/* silently fail — empty messages is fine */})
  }, [business.id]) // re-run if business.id changes (won't happen this sprint)

  // Auto-scroll to the bottom whenever the messages array changes.
  // The optional chaining (?.) means "only call scrollIntoView if bottomRef.current exists".
  // This prevents an error on the first render before the ref is attached.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  async function handleSend(text) {
    // Accept a text argument (for example chips) or fall back to the input field.
    const userMessage = (text ?? input).trim()
    if (!userMessage || loading) return

    setInput("")
    setLoading(true)
    setError(null)

    // Optimistic UI: add the user's message to the screen immediately,
    // before the server responds. WHY? The chat feels instant.
    // Without this there is a visible delay between pressing Send and
    // seeing your own message appear.
    // We use a fake id so React has a stable key while this message is pending.
    setMessages((prev) => [...prev, { role: "user", content: userMessage, id: "optimistic" }])

    try {
      const res = await fetch(`${API}/api/chat/${business.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessage }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Server error")

      // Append the AI reply. The optimistic user message stays — it will be
      // replaced when the user refreshes (at that point it comes from the DB
      // with a real UUID). For a single session this is fine.
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }])
    } catch (err) {
      setError("Something went wrong. Please try again.")
      // Remove the optimistic message if the request failed,
      // so the user isn't left with an unanswered message.
      setMessages((prev) => prev.filter((m) => m.id !== "optimistic"))
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    // Send on Enter, but allow Shift+Enter to insert a newline.
    // This is standard chat app behavior (same as iMessage, Slack, etc.)
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault() // prevent Enter from inserting a newline
      handleSend()
    }
  }

  async function handleClearChat() {
    await fetch(`${API}/api/messages/${business.id}`, { method: "DELETE" })
    setMessages([])
  }

  // Example questions shown in the empty state.
  // Template literals use backticks and ${} to inject variables into strings.
  const EXAMPLE_QUESTIONS = [
    `What licenses do I need to operate in ${business.state}?`,
    `What are my obligations as an employer with ${business.employee_count} employees?`,
    `What is the difference between a contractor and an employee?`,
  ]

  return (
    <div style={s.container}>
      {/* ── Header ──────────────────────────────────────── */}
      <div style={s.header}>
        <div>
          <h2 style={s.headerTitle}>Complio</h2>
          <p style={s.headerMeta}>
            {business.name} · {business.industry} · {business.state}
          </p>
        </div>
        <div style={s.headerActions}>
          <button style={s.ghostBtn} onClick={handleClearChat}>Clear Chat</button>
          <button style={s.ghostBtn} onClick={onReset}>New Business</button>
        </div>
      </div>

      {/* ── Message List ─────────────────────────────────── */}
      <div style={s.messageList}>
        {messages.length === 0 && !loading ? (
          /* Empty state — shown before the first message is sent */
          <div style={s.emptyState}>
            <p style={s.emptyTitle}>
              Ask me anything about running <strong>{business.name}</strong>
            </p>
            <div style={s.chips}>
              {EXAMPLE_QUESTIONS.map((q) => (
                <button key={q} style={s.chip} onClick={() => handleSend(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* Render each message in the conversation */
          messages.map((msg, idx) => {
            const isUser = msg.role === "user"
            return (
              <div key={msg.id ?? idx} style={{ ...s.messageRow, justifyContent: isUser ? "flex-end" : "flex-start" }}>
                <div style={isUser ? s.userBubble : s.aiBubble}>
                  <span style={s.roleLabel}>{isUser ? "You" : "Complio"}</span>
                  {/* white-space: pre-wrap preserves newlines from the AI response.
                      Without it, paragraph breaks would collapse into a single line. */}
                  <p style={s.messageText}>{msg.content}</p>
                </div>
              </div>
            )
          })
        )}

        {/* Loading indicator — shown while waiting for AI response */}
        {loading && (
          <div style={{ ...s.messageRow, justifyContent: "flex-start" }}>
            <div style={s.aiBubble}>
              <span style={s.roleLabel}>Complio</span>
              <p style={{ ...s.messageText, color: "#888" }}>Thinking…</p>
            </div>
          </div>
        )}

        {/* Invisible div at the bottom — we scroll to this when new messages arrive */}
        <div ref={bottomRef} />
      </div>

      {/* ── Input Area ───────────────────────────────────── */}
      <div style={s.inputArea}>
        {error && <p style={s.error}>{error}</p>}
        <div style={s.inputRow}>
          {/* textarea instead of input so the user can write multi-line questions.
              rows=1 with CSS resize:none keeps it compact until they type. */}
          <textarea
            style={s.textarea}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a legal or compliance question… (Enter to send, Shift+Enter for newline)"
            rows={1}
            disabled={loading}
          />
          <button
            style={{ ...s.sendBtn, opacity: loading ? 0.6 : 1 }}
            onClick={() => handleSend()}
            disabled={loading}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

const s = {
  container: {
    display: "flex",
    flexDirection: "column",
    width: "100%",
    maxWidth: 760,
    height: "calc(100vh - 48px)", // full viewport minus the page padding
    background: "#fff",
    borderRadius: 12,
    boxShadow: "0 2px 16px rgba(0,0,0,0.08)",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px",
    borderBottom: "1px solid #eee",
    flexShrink: 0, // don't let the header shrink when messages fill up
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 700,
    color: "#111",
  },
  headerMeta: {
    fontSize: 13,
    color: "#777",
    marginTop: 2,
  },
  headerActions: {
    display: "flex",
    gap: 8,
  },
  ghostBtn: {
    padding: "6px 14px",
    border: "1.5px solid #ddd",
    borderRadius: 8,
    background: "transparent",
    fontSize: 13,
    cursor: "pointer",
    color: "#444",
  },
  messageList: {
    flex: 1,           // takes all remaining vertical space between header and input
    overflowY: "auto", // scrollable when messages overflow
    padding: "20px 20px 8px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  emptyState: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
    gap: 20,
    padding: "40px 0",
  },
  emptyTitle: {
    fontSize: 16,
    color: "#555",
    textAlign: "center",
  },
  chips: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    width: "100%",
    maxWidth: 560,
  },
  chip: {
    padding: "12px 16px",
    borderRadius: 10,
    border: "1.5px solid #e0e7ff",
    background: "#f5f7ff",
    color: "#3b5bdb",
    fontSize: 14,
    cursor: "pointer",
    textAlign: "left",
    lineHeight: 1.4,
  },
  messageRow: {
    display: "flex",
  },
  userBubble: {
    background: "#2563eb",
    color: "#fff",
    padding: "10px 14px",
    borderRadius: "14px 14px 4px 14px",
    maxWidth: "75%",
  },
  aiBubble: {
    background: "#f3f4f6",
    color: "#111",
    padding: "10px 14px",
    borderRadius: "14px 14px 14px 4px",
    maxWidth: "85%",
  },
  roleLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    opacity: 0.6,
    display: "block",
    marginBottom: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 1.6,
    // pre-wrap preserves newlines (\n) in the AI response.
    // Without this, all paragraphs would collapse into one block.
    whiteSpace: "pre-wrap",
  },
  inputArea: {
    padding: "12px 16px 16px",
    borderTop: "1px solid #eee",
    flexShrink: 0,
  },
  inputRow: {
    display: "flex",
    gap: 10,
    alignItems: "flex-end",
  },
  textarea: {
    flex: 1,
    padding: "10px 14px",
    border: "1.5px solid #ddd",
    borderRadius: 10,
    fontSize: 15,
    outline: "none",
    resize: "none",
    fontFamily: "inherit",
    lineHeight: 1.5,
    maxHeight: 120,
    overflowY: "auto",
  },
  sendBtn: {
    padding: "10px 20px",
    borderRadius: 10,
    border: "none",
    background: "#2563eb",
    color: "#fff",
    fontSize: 15,
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
  },
  error: {
    color: "#c0392b",
    fontSize: 13,
    marginBottom: 8,
    padding: "6px 10px",
    background: "#fdecea",
    borderRadius: 6,
  },
}
