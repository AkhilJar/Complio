import { useState, useEffect } from "react"
import BusinessForm from "./components/BusinessForm"
import ChatWindow from "./components/ChatWindow"
import "./App.css"

// The base URL of our Flask backend.
// We keep it in one place so if the port changes we only update it here.
const API = "http://localhost:5001"

export default function App() {
  // null   = still loading (we haven't checked the DB yet)
  // false  = checked DB, no business found → show the form
  // object = business profile loaded from DB → show chat
  const [business, setBusiness] = useState(null)

  // On mount: check if a business already exists in the DB.
  // The empty dependency array [] means "only run this once" —
  // not every time the component re-renders.
  // This is the key difference between DB persistence and React state:
  // React state disappears on refresh. The database does not.
  useEffect(() => {
    fetch(`${API}/api/business`)
      .then((res) => res.json())
      .then((data) => {
        // data is the business object from DB, or JSON null if none exists.
        // If null, set false so the render logic below shows the form.
        setBusiness(data ?? false)
      })
      .catch(() => {
        // If the backend is unreachable, default to showing the form.
        setBusiness(false)
      })
  }, [])

  // Called by BusinessForm after the user submits.
  // formData is { name, industry, state, business_type, employee_count }.
  // async/await lets us write async code that reads like sync code.
  // "await" pauses here until the fetch finishes, then continues.
  async function handleBusinessSubmit(formData) {
    const res = await fetch(`${API}/api/business`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formData),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.error || "Failed to save business")
    setBusiness(data)
  }

  // Resets the UI back to the form so the user can enter a different business.
  // Does NOT delete the business or messages from the DB.
  function handleReset() {
    setBusiness(false)
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (business === null) {
    // Still waiting for the /api/business fetch to complete.
    return <div className="loading">Loading…</div>
  }

  if (business === false) {
    // No business in the DB yet — show the setup form.
    return (
      <div className="page">
        <BusinessForm onSubmit={handleBusinessSubmit} />
      </div>
    )
  }

  // Business exists — go straight to the chat.
  return (
    <div className="page">
      <ChatWindow business={business} onReset={handleReset} API={API} />
    </div>
  )
}
