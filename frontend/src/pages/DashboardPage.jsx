import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity, ArrowRight, Database,
  FileStack, FlaskConical, Plus, ShieldAlert,
  ShieldCheck, TrendingDown, TrendingUp
} from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell,
  ResponsiveContainer, Tooltip, XAxis, YAxis
} from "recharts";
import { dashboardApi, getApiErrorMessage } from "../api/client";
import {
  Badge, Button, Card, DataTable,
  MetricCard, Notice, PageHeader, SkeletonCard
} from "../components/UI";

/* Custom chart tooltip */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "var(--color-surface)",
      border: "1px solid var(--color-border)",
      borderRadius: "var(--radius-md)",
      padding: "10px 14px",
      boxShadow: "var(--shadow-3)",
      fontSize: 12,
    }}>
      <p style={{ margin: "0 0 6px", color: "var(--color-text-muted)", fontWeight: 700, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>
        Version {label}
      </p>
      {payload.map(entry => (
        <div key={entry.dataKey} style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: entry.color, flexShrink: 0 }} />
          <span style={{ color: "var(--color-text-soft)" }}>{entry.name}</span>
          <strong style={{ marginLeft: "auto", color: "var(--color-text)", paddingLeft: 12 }}>
            {Number(entry.value).toFixed(1)}
          </strong>
        </div>
      ))}
    </div>
  );
}

/* Risk level badge for the activity table */
function RiskBadge({ score }) {
  if (score == null) return <span style={{ color: "var(--color-text-subtle)" }}>—</span>;
  const tone = score >= 70 ? "high" : score >= 40 ? "medium" : "low";
  return <Badge tone={tone}>{score.toFixed(0)}</Badge>;
}

/* Stat row for quick overview strip */
function StatStrip({ data }) {
  const items = [
    { label: "Avg MLRS", value: data.avg_mlrs?.toFixed(1) ?? "—", icon: TrendingDown, desc: "Mean risk score" },
    { label: "Avg LRS",  value: data.avg_lrs?.toFixed(1)  ?? "—", icon: ShieldCheck,  desc: "Mean leakage score" },
    { label: "Versions", value: data.total_versions        ?? "—", icon: FileStack,    desc: "Registered versions" },
    { label: "At risk",  value: data.high_risk_studies     ?? "—", icon: ShieldAlert,  desc: "Studies with high MLRS" },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--sp-4)" }}>
      {items.map(({ label, value, icon: Icon, desc }) => (
        <div key={label} style={{
          display: "flex", flexDirection: "column", gap: 4,
          padding: "var(--sp-4)", border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)", background: "var(--color-surface)",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "var(--color-text-muted)", letterSpacing: "0.07em", textTransform: "uppercase" }}>{label}</span>
            <Icon size={14} style={{ color: "var(--color-text-subtle)" }} />
          </div>
          <span style={{ fontSize: 22, fontWeight: 700, color: "var(--color-text)", letterSpacing: "-0.04em", lineHeight: 1 }}>{value}</span>
          <span style={{ fontSize: 11, color: "var(--color-text-muted)" }}>{desc}</span>
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    dashboardApi.get()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(getApiErrorMessage(err, "Could not load dashboard data."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <>
        <PageHeader
          eyebrow="Framework overview"
          title="Research Dashboard"
          description="A concise view of registered evidence, version activity, and deterministic risk signals across your research workspace."
        />
        <Notice error>{error}</Notice>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <PageHeader
          eyebrow="Framework overview"
          title="Research Dashboard"
          description="Loading your evidence workspace overview…"
        />
        <div className="grid grid-4" style={{ marginBottom: "var(--sp-5)" }}>
          {[0,1,2,3].map(i => <SkeletonCard key={i} lines={2} />)}
        </div>
        <div className="grid grid-2">
          <SkeletonCard lines={6} />
          <SkeletonCard lines={6} />
        </div>
      </>
    );
  }

  const metrics = [
    { label: "Total studies",     value: data.total_studies,     icon: FlaskConical },
    { label: "Datasets registered", value: data.total_datasets,  icon: Database     },
    { label: "Dataset versions",  value: data.total_versions,    icon: FileStack    },
    { label: "High-risk studies", value: data.high_risk_studies, icon: ShieldAlert  },
  ];

  const chartData = (data.recent_diagnoses || []).map(d => ({
    ...d,
    version_id: `V${d.version_id}`,
  }));

  const activityColumns = [
    { key: "action",      label: "Activity",      sortable: false,
      render: row => (
        <span style={{ fontWeight: 600, color: "var(--color-text-soft)", fontSize: 12 }}>
          {row.action}
        </span>
      )
    },
    { key: "entity_type", label: "Type",          sortable: false,
      render: row => <Badge tone="neutral">{row.entity_type}</Badge>
    },
    { key: "created_at",  label: "Time",          sortable: false,
      render: row => (
        <span style={{ color: "var(--color-text-muted)", fontSize: 12 }}>
          {new Date(row.created_at).toLocaleString(undefined, {
            month: "short", day: "numeric",
            hour: "2-digit", minute: "2-digit"
          })}
        </span>
      )
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Framework overview"
        title="Research Dashboard"
        description="A concise view of registered evidence, version activity, and deterministic risk signals across your research workspace."
        action={
          <Link to="/studies">
            <Button id="dashboard-create-study-btn">
              <Plus size={15} />
              New study
            </Button>
          </Link>
        }
      />

      {/* KPI metric cards */}
      <div className="grid grid-4" style={{ marginBottom: "var(--sp-5)" }}>
        {metrics.map(({ label, value, icon }) => (
          <MetricCard key={label} label={label} value={value} icon={icon} />
        ))}
      </div>

      {/* Charts + activity row */}
      <div className="grid grid-2" style={{ marginBottom: "var(--sp-5)" }}>
        {/* Risk chart */}
        <Card className="no-hover">
          <div className="row" style={{ marginBottom: "var(--sp-4)" }}>
            <div>
              <p className="eyebrow">Risk monitoring</p>
              <h2 style={{ margin: 0 }}>Recent diagnosis risk scores</h2>
            </div>
            <span className="metric-icon">
              <Activity size={15} />
            </span>
          </div>

          {chartData.length === 0 ? (
            <div style={{ height: 220, display: "grid", placeItems: "center", color: "var(--color-text-muted)", fontSize: 13 }}>
              No diagnosis data yet. Run your first diagnosis to see risk scores here.
            </div>
          ) : (
            <>
              {/* Legend */}
              <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
                {[
                  { label: "MLRS", color: "var(--indigo-500)" },
                  { label: "LRS",  color: "var(--blue-400)"   },
                ].map(({ label, color }) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--color-text-muted)" }}>
                    <span style={{ width: 10, height: 10, borderRadius: 3, background: color, flexShrink: 0 }} />
                    {label}
                  </div>
                ))}
              </div>

              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barGap={4}>
                  <CartesianGrid
                    stroke="var(--chart-grid)"
                    vertical={false}
                    strokeDasharray="0"
                  />
                  <XAxis
                    dataKey="version_id"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--color-text-muted)", fontSize: 10 }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "var(--color-text-muted)", fontSize: 10 }}
                  />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--color-surface-2)" }} />
                  <Bar dataKey="mlrs_score" name="MLRS" fill="var(--indigo-500)" radius={[4, 4, 0, 0]} maxBarSize={28}>
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={entry.mlrs_score >= 70 ? "var(--color-danger)" : entry.mlrs_score >= 40 ? "var(--color-warning)" : "var(--indigo-500)"} />
                    ))}
                  </Bar>
                  <Bar dataKey="lrs_score"  name="LRS"  fill="var(--blue-400)"   radius={[4, 4, 0, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>

              <p style={{ margin: "var(--sp-3) 0 0", fontSize: 11, color: "var(--color-text-muted)" }}>
                MLRS coloring: <span style={{ color: "var(--color-success)" }}>■</span> Low &nbsp;
                <span style={{ color: "var(--color-warning)" }}>■</span> Medium &nbsp;
                <span style={{ color: "var(--color-danger)"  }}>■</span> High
              </p>
            </>
          )}
        </Card>

        {/* Activity feed */}
        <Card className="no-hover">
          <div className="row" style={{ marginBottom: "var(--sp-4)" }}>
            <div>
              <p className="eyebrow">Audit trail</p>
              <h2 style={{ margin: 0 }}>Recent evidence activity</h2>
            </div>
            <Link to="/studies">
              <Button variant="ghost" className="compact">
                View studies <ArrowRight size={13} />
              </Button>
            </Link>
          </div>
          <DataTable
            rows={data.recent_activity}
            columns={activityColumns}
            empty="No evidence activity has been recorded yet."
          />
        </Card>
      </div>

      {/* Quick-access navigation cards */}
      <div className="grid grid-3">
        {[
          {
            to: "/studies",
            icon: FlaskConical,
            color: "var(--color-primary)",
            bg: "var(--color-primary-soft)",
            border: "var(--color-primary-line)",
            title: "ML Studies",
            desc: "Create a study, register datasets, run diagnoses, and generate preprocessing variants.",
          },
          {
            to: "/studies",
            icon: Database,
            color: "var(--color-secondary)",
            bg: "var(--color-secondary-soft)",
            border: "var(--color-secondary-line)",
            title: "Dataset Evidence",
            desc: "Register, fingerprint, and version raw datasets with schema-aware integrity checking.",
          },
          {
            to: "/findings",
            icon: ShieldCheck,
            color: "var(--color-success)",
            bg: "var(--color-success-soft)",
            border: "var(--color-success-line)",
            title: "Research Findings",
            desc: "Review consolidated deterministic evidence across all studies and versions.",
          },
        ].map(({ to, icon: Icon, color, bg, border, title, desc }) => (
          <Link key={to + title} to={to} style={{ textDecoration: "none" }}>
            <Card style={{
              display: "flex", flexDirection: "column", gap: "var(--sp-3)",
              height: "100%", cursor: "pointer",
              transition: "transform var(--duration-fast), box-shadow var(--duration-fast)",
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: "var(--radius-md)",
                background: bg, border: `1px solid ${border}`,
                display: "grid", placeItems: "center", color,
              }}>
                <Icon size={18} />
              </div>
              <div>
                <h3 style={{ margin: "0 0 4px", color: "var(--color-text)" }}>{title}</h3>
                <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>{desc}</p>
              </div>
              <div style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: 600, color }}>
                Open <ArrowRight size={13} />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </>
  );
}
