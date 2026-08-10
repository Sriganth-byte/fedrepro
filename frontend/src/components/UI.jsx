import { useEffect, useRef, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Copy, Info, Loader2, Moon, Sun } from "lucide-react";

/* ── Card ─────────────────────────────────────────────────── */
export function Card({ children, className = "", ...props }) {
  return (
    <section className={`card ${className}`.trim()} {...props}>
      {children}
    </section>
  );
}

/* ── Button ───────────────────────────────────────────────── */
export function Button({ children, variant = "", className = "", loading = false, ...props }) {
  return (
    <button
      className={`button ${variant} ${className}`.trim()}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading
        ? <><Loader2 size={14} className="spin" /><span>Loading…</span></>
        : children}
    </button>
  );
}

/* ── Field ────────────────────────────────────────────────── */
export function Field({ label, children, full = false, hint }) {
  return (
    <div className={`field${full ? " full" : ""}`}>
      {label && <label>{label}</label>}
      {children}
      {hint && <span style={{ fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.4 }}>{hint}</span>}
    </div>
  );
}

/* ── Badge ────────────────────────────────────────────────── */
export function Badge({ children, tone = "" }) {
  return <span className={`badge ${tone}`.trim()}>{children}</span>;
}

/* ── Notice ───────────────────────────────────────────────── */
const noticeIcon = { error: AlertCircle, warning: AlertTriangle, success: CheckCircle2, info: Info };
export function Notice({ children, error = false, warning = false, success = false, style }) {
  const tone = error ? "error" : warning ? "warning" : success ? "success" : "info";
  const Icon = noticeIcon[tone];
  return (
    <div className={`notice ${error ? "error" : warning ? "warning" : success ? "success" : ""}`.trim()} style={style}>
      <Icon size={15} style={{ flex: "0 0 auto", marginTop: 1 }} />
      <div>{children}</div>
    </div>
  );
}

/* ── PageHeader ───────────────────────────────────────────── */
export function PageHeader({ eyebrow, title, description, action }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="subtitle">{description}</p>}
      </div>
      {action}
    </header>
  );
}

/* ── Empty state ──────────────────────────────────────────── */
export function Empty({ children, icon: Icon, action }) {
  return (
    <div className="empty">
      {Icon && (
        <div className="empty-icon">
          <Icon size={22} />
        </div>
      )}
      <p style={{ margin: 0, maxWidth: 360, lineHeight: 1.6 }}>{children}</p>
      {action}
    </div>
  );
}

/* ── MetricCard ───────────────────────────────────────────── */
export function MetricCard({ icon: Icon, label, value, trend, trendLabel }) {
  return (
    <Card className="metric-card no-hover">
      <div className="metric-top">
        <p className="metric-label">{label}</p>
        {Icon && (
          <span className="metric-icon">
            <Icon size={16} strokeWidth={2} />
          </span>
        )}
      </div>
      <p className="metric-value">{value ?? "—"}</p>
      {trend != null && (
        <p style={{ margin: "6px 0 0", fontSize: 11, color: trend >= 0 ? "var(--color-success)" : "var(--color-danger)", display: "flex", alignItems: "center", gap: 3 }}>
          {trend >= 0
            ? <ChevronUp size={13} />
            : <ChevronDown size={13} />}
          {Math.abs(trend)}% {trendLabel || ""}
        </p>
      )}
    </Card>
  );
}

/* ── DataTable ────────────────────────────────────────────── */
export function DataTable({ columns, rows, empty = "No records available.", emptyIcon }) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  if (!rows?.length) return <Empty icon={emptyIcon}>{empty}</Empty>;

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("asc"); }
  };

  const sorted = sortKey
    ? [...rows].sort((a, b) => {
        const va = a[sortKey] ?? "";
        const vb = b[sortKey] ?? "";
        const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true });
        return sortDir === "asc" ? cmp : -cmp;
      })
    : rows;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map(col => (
              <th
                key={col.key}
                onClick={col.sortable !== false ? () => handleSort(col.key) : undefined}
                style={col.sortable !== false ? { cursor: "pointer", userSelect: "none" } : undefined}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  {col.label}
                  {sortKey === col.key && (
                    sortDir === "asc" ? <ChevronUp size={11} /> : <ChevronDown size={11} />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, idx) => (
            <tr key={row.id ?? idx}>
              {columns.map(col => (
                <td key={col.key}>
                  {col.render ? col.render(row) : String(row[col.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Skeleton ─────────────────────────────────────────────── */
export function Skeleton({ width = "100%", height = 16, radius = 4, style = {} }) {
  return (
    <div
      className="skeleton"
      style={{ width, height, borderRadius: radius, flexShrink: 0, ...style }}
    />
  );
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <Card style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Skeleton height={20} width="55%" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} height={13} width={i === lines - 1 ? "70%" : "100%"} />
      ))}
    </Card>
  );
}

/* ── CopyButton ───────────────────────────────────────────── */
export function CopyButton({ value, size = 13 }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };
  return (
    <button
      onClick={copy}
      title={copied ? "Copied!" : "Copy to clipboard"}
      style={{
        display: "inline-grid",
        placeItems: "center",
        width: 28, height: 28,
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-sm)",
        background: copied ? "var(--color-success-soft)" : "var(--color-surface)",
        color: copied ? "var(--color-success)" : "var(--color-text-muted)",
        cursor: "pointer",
        transition: "all var(--duration-fast)",
        flexShrink: 0,
      }}
    >
      {copied ? <CheckCircle2 size={size} /> : <Copy size={size} />}
    </button>
  );
}

/* ── ThemeToggle ──────────────────────────────────────────── */
export function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem("fedrepro-theme") === "dark"; }
    catch { return false; }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    try { localStorage.setItem("fedrepro-theme", dark ? "dark" : "light"); }
    catch {}
  }, [dark]);

  // Apply on initial load
  useEffect(() => {
    const saved = localStorage.getItem("fedrepro-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
  }, []);

  return (
    <button
      className="icon-button"
      onClick={() => setDark(d => !d)}
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      style={{ position: "relative" }}
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

/* ── StatusDot ────────────────────────────────────────────── */
export function StatusDot({ status }) {
  const colorMap = {
    active: "var(--color-success)",
    running: "var(--color-warning)",
    failed: "var(--color-danger)",
    pending: "var(--color-text-subtle)",
    completed: "var(--color-success)",
    idle: "var(--color-text-subtle)",
  };
  const color = colorMap[status] || "var(--color-text-subtle)";
  return (
    <span style={{
      display: "inline-block",
      width: 7, height: 7,
      borderRadius: "50%",
      background: color,
      flexShrink: 0,
      boxShadow: `0 0 0 2px ${color}33`,
    }} />
  );
}
