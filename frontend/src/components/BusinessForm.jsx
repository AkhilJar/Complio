import { useState } from "react"

// All 50 US state abbreviations for the state dropdown.
const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
  "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
  "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
  "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
]

// BusinessForm is shown once, the first time the user visits the app.
// It collects info about the business that the AI will use in every answer.
//
// Props:
//   onSubmit(formData) — called with the form values when the user submits.
//                        Defined in App.jsx and sends a POST to the backend.
export default function BusinessForm({ onSubmit }) {
  // All form fields live in a single state object.
  // This is a common pattern: one useState instead of five separate ones.
  const [form, setForm] = useState({
    name: "",
    industry: "",
    state: "",
    business_type: "",
    employee_count: 1,
  })

  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  // Generic change handler for all inputs.
  // e.target.name matches the `name` attribute on each input/select.
  // e.target.value is what the user typed or selected.
  // The spread operator (...form) copies all existing fields,
  // then we overwrite just the one that changed.
  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value })
  }

  async function handleSubmit(e) {
    // Prevent the browser's default form behavior (page reload).
    e.preventDefault()
    setError(null)

    // Client-side validation before sending to the server.
    const required = ["name", "industry", "state", "business_type", "employee_count"]
    for (const field of required) {
      if (!form[field]) {
        setError(`Please fill in ${field.replace("_", " ")}`)
        return
      }
    }

    setLoading(true)
    try {
      // onSubmit is provided by App.jsx. It POSTs the data to the backend.
      // We await it so we stay in the loading state until it completes.
      await onSubmit({
        ...form,
        // Ensure employee_count is a number, not a string.
        // HTML inputs always give strings; our DB column expects INTEGER.
        employee_count: parseInt(form.employee_count, 10),
      })
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.")
    } finally {
      // finally runs whether the try succeeded or the catch ran.
      // Always turn off loading when we are done.
      setLoading(false)
    }
  }

  return (
    <div style={s.card}>
      {/* Header */}
      <div style={s.header}>
        <h1 style={s.title}>Welcome to Complio</h1>
        <p style={s.subtitle}>
          Tell us about your business so we can give you accurate legal guidance.
        </p>
      </div>

      <form onSubmit={handleSubmit} style={s.form}>
        {/* Business Name */}
        <div style={s.field}>
          <label style={s.label}>Business Name</label>
          <input
            style={s.input}
            type="text"
            name="name"
            value={form.name}
            onChange={handleChange}
            placeholder="e.g. Austin Coffee Co"
            required
          />
        </div>

        {/* Industry */}
        <div style={s.field}>
          <label style={s.label}>Industry</label>
          <select style={s.input} name="industry" value={form.industry} onChange={handleChange} required>
            <option value="">Select an industry…</option>
            <option>Food & Beverage</option>
            <option>Retail</option>
            <option>Professional Services</option>
            <option>Healthcare</option>
            <option>Construction</option>
            <option>Technology</option>
            <option>Other</option>
          </select>
        </div>

        {/* State */}
        <div style={s.field}>
          <label style={s.label}>State of Operation</label>
          <select style={s.input} name="state" value={form.state} onChange={handleChange} required>
            <option value="">Select a state…</option>
            {US_STATES.map((abbr) => (
              // Each option needs a unique `key` prop so React can track it efficiently.
              <option key={abbr} value={abbr}>{abbr}</option>
            ))}
          </select>
        </div>

        {/* Business Type */}
        <div style={s.field}>
          <label style={s.label}>Business Structure</label>
          <select style={s.input} name="business_type" value={form.business_type} onChange={handleChange} required>
            <option value="">Select a structure…</option>
            <option value="LLC">LLC</option>
            <option value="Sole Proprietor">Sole Proprietor</option>
            <option value="S-Corp">S-Corp</option>
            <option value="C-Corp">C-Corp</option>
            <option value="Partnership">Partnership</option>
          </select>
        </div>

        {/* Employee Count */}
        <div style={s.field}>
          <label style={s.label}>Number of Employees</label>
          <input
            style={s.input}
            type="number"
            name="employee_count"
            value={form.employee_count}
            onChange={handleChange}
            min="1"
            required
          />
        </div>

        {/* Error message — only shown when error state is set */}
        {error && <p style={s.error}>{error}</p>}

        {/* disabled while loading so the user can't double-submit */}
        <button style={s.button} type="submit" disabled={loading}>
          {loading ? "Setting up…" : "Get Started"}
        </button>
      </form>
    </div>
  )
}

// Inline styles — keeps the component self-contained.
const s = {
  card: {
    background: "#fff",
    borderRadius: 12,
    padding: "40px 36px",
    maxWidth: 480,
    width: "100%",
    boxShadow: "0 2px 16px rgba(0,0,0,0.08)",
  },
  header: {
    marginBottom: 28,
  },
  title: {
    fontSize: 26,
    fontWeight: 700,
    marginBottom: 8,
    color: "#111",
  },
  subtitle: {
    fontSize: 15,
    color: "#555",
    lineHeight: 1.5,
  },
  form: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  label: {
    fontSize: 14,
    fontWeight: 600,
    color: "#333",
  },
  input: {
    padding: "10px 12px",
    borderRadius: 8,
    border: "1.5px solid #ddd",
    fontSize: 15,
    outline: "none",
    width: "100%",
  },
  error: {
    color: "#c0392b",
    fontSize: 14,
    padding: "8px 12px",
    background: "#fdecea",
    borderRadius: 6,
  },
  button: {
    marginTop: 8,
    padding: "12px",
    borderRadius: 8,
    border: "none",
    background: "#2563eb",
    color: "#fff",
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
  },
}
