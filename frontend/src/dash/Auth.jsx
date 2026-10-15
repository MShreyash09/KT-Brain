import { useState } from "react";
import { api } from "../ui.jsx";

// ponytail: demo credentials printed on the page for one-click sign-in; remove before real customers sign up
const DEMO_PASSWORD = "demo123";
const DEMO = [
  ["admin@tiffinbox.example", "TiffinBox admin", "Sees every employee's graph, offboards people and picks successors"],
  ["meera@tiffinbox.example", "Meera, new backend developer", "Succeeded Arjun and Priya, so she can read both of their brains"],
  ["kavya@tiffinbox.example", "Kavya, frontend", "Sees only her own graph"],
  ["rohan@tiffinbox.example", "Rohan, AI/ML", "Sees only his own graph"],
  ["arjun@tiffinbox.example", "Arjun, left Sep 30", "Offboarded, so sign-in is blocked"],
];

function Field({ label, ...input }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input required {...input} />
    </label>
  );
}

export function Login({ onIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const signIn = async (e, p) => {
    setBusy(true);
    setError("");
    try {
      onIn(await api("auth/login", { email: e, password: p }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <form className="card auth-card" onSubmit={(e) => { e.preventDefault(); signIn(email, password); }}>
        <h1>Sign in</h1>
        <Field label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Password" type="password" autoComplete="current-password" value={password}
          onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="muted small">New company? <a href="#/register">Register your company</a></p>
      </form>

      <section className="card auth-card demo-accounts">
        <h2>Demo accounts</h2>
        <p className="muted small">All use the password <code>{DEMO_PASSWORD}</code>. Click one to sign in.</p>
        {DEMO.map(([e, who, what]) => (
          <button key={e} className="row clickable" onClick={() => signIn(e, DEMO_PASSWORD)} disabled={busy}>
            <span className="item-label"><b>{who}</b><br /><span className="muted small">{what}</span></span>
            <code className="small">{e}</code>
          </button>
        ))}
      </section>
    </main>
  );
}

export function Register({ onIn }) {
  const [form, setForm] = useState({ company: "", name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onIn(await api("auth/register", form));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Register your company</h1>
        <p className="muted small">You become the admin. Your company gets its own graph, and you add employees next.</p>
        <Field label="Company name" value={form.company} onChange={set("company")} />
        <Field label="Your name" autoComplete="name" value={form.name} onChange={set("name")} />
        <Field label="Work email" type="email" autoComplete="username" value={form.email} onChange={set("email")} />
        <Field label="Password (6+ characters)" type="password" minLength={6} autoComplete="new-password"
          value={form.password} onChange={set("password")} />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="btn primary" disabled={busy}>{busy ? "Creating…" : "Create company"}</button>
        <p className="muted small">Already registered? <a href="#/login">Sign in</a></p>
      </form>
    </main>
  );
}
