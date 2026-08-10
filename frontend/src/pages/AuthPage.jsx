import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ArrowRight, Database, FlaskConical, ShieldCheck, Workflow } from "lucide-react";
import { authApi } from "../api/client";
import { Button, Field, Notice } from "../components/UI";
import { useAuth } from "../context/AuthContext";

const PROOF_POINTS = [
  { icon: ShieldCheck, title: "Deterministic",  body: "All metrics are computed by versioned, auditable services — never AI." },
  { icon: FlaskConical, title: "Reproducible",  body: "Fingerprinted dataset versions guarantee recreation from any checkpoint." },
  { icon: Database, title: "Evidence-first",    body: "Register, profile, and diagnose before any experiment begins." },
];

export default function AuthPage() {
  const { authenticated, setToken } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);

  if (authenticated) return <Navigate to="/dashboard" replace />;

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const payload = mode === "login"
        ? { email: form.email, password: form.password }
        : form;
      const result = await authApi[mode](payload);
      setToken(result.access_token);
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Authentication failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      {/* ── Left visual panel ── */}
      <section className="auth-visual" aria-hidden="true">
        <div className="auth-brand">
          <span className="brand-mark">
            <Workflow size={19} strokeWidth={2.2} />
          </span>
          FedRepro
        </div>

        <div className="auth-message">
          <p>Data-centric ML research platform</p>
          <h1>Evidence before experimentation.</h1>
          <p>
            Register immutable datasets, profile task-specific risk, generate
            preprocessing variants, and preserve a fully reproducible research trail
            — all before a model touches the data.
          </p>
        </div>

        <div className="auth-proof">
          {PROOF_POINTS.map(({ icon: Icon, title, body }) => (
            <div key={title}>
              <strong>
                <Icon size={13} style={{ verticalAlign: "-2px", marginRight: 5 }} />
                {title}
              </strong>
              <span>{body}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Right form panel ── */}
      <section className="auth-form-side">
        <form className="auth-card stack" onSubmit={submit} noValidate>
          {/* Header */}
          <div>
            <p className="eyebrow">
              {mode === "login" ? "Welcome back" : "Get started free"}
            </p>
            <h1>{mode === "login" ? "Sign in to FedRepro" : "Create your account"}</h1>
            <p className="subtitle" style={{ marginTop: 4 }}>
              {mode === "login"
                ? "Continue to your evidence research workspace."
                : "Start a secure Phase I research workspace."}
            </p>
          </div>

          {/* Fields */}
          {mode === "register" && (
            <Field label="Researcher name">
              <input
                id="auth-name"
                autoComplete="name"
                value={form.name}
                onChange={set("name")}
                placeholder="Your full name"
                required
              />
            </Field>
          )}

          <Field label="Email address">
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={set("email")}
              placeholder="researcher@institution.edu"
              required
            />
          </Field>

          <Field label="Password" hint={mode === "register" ? "Minimum 8 characters" : undefined}>
            <input
              id="auth-password"
              type="password"
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={form.password}
              onChange={set("password")}
              placeholder="••••••••"
              required
            />
          </Field>

          {error && <Notice error>{error}</Notice>}

          <Button id="auth-submit-btn" loading={loading} style={{ marginTop: 4 }}>
            {mode === "login" ? "Sign in" : "Create account"}
            {!loading && <ArrowRight size={15} />}
          </Button>

          <button
            type="button"
            className="button auth-switch"
            onClick={() => { setMode(m => m === "login" ? "register" : "login"); setError(""); }}
          >
            {mode === "login"
              ? "Don't have an account? Register →"
              : "Already have an account? Sign in →"}
          </button>
        </form>
      </section>
    </div>
  );
}
