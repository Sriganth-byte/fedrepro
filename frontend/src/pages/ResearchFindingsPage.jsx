import { useEffect, useState } from "react";
import { ArrowUpRight, BookOpenCheck, Database, FileStack, TrendingDown } from "lucide-react";
import { Link } from "react-router-dom";
import { getApiErrorMessage, studyApi } from "../api/client";
import { Badge, Card, Empty, Notice, PageHeader, SkeletonCard } from "../components/UI";

/* Risk badge for MLRS scores */
function RiskBadge({ score }) {
  if (score == null) return <span style={{ color: "var(--color-text-subtle)", fontSize: 11 }}>No diagnosis</span>;
  const n = Number(score);
  const tone = n >= 70 ? "high" : n >= 40 ? "medium" : "low";
  return <Badge tone={tone}>MLRS {n.toFixed(1)}</Badge>;
}

export default function ResearchFindingsPage() {
  const [items,   setItems]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");

  useEffect(() => {
    let cancelled = false;
    studyApi.allFindings()
      .then((result) => {
        if (!cancelled) setItems(result);
      })
      .catch((err) => {
        if (!cancelled) setError(getApiErrorMessage(err, "Could not load research findings."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <PageHeader
        eyebrow="Phase I evidence"
        title="Research Findings"
        description="Consolidated dataset evolution and risk evidence across all studies. Phase I reports evidence only and makes no model-training claims."
      />

      {/* Loading skeleton */}
      {loading && (
        <div className="stack">
          {[0, 1, 2].map(i => <SkeletonCard key={i} lines={4} />)}
        </div>
      )}

      {!loading && error && <Notice error>{error}</Notice>}

      {/* Empty state */}
      {!loading && !error && !items?.length && (
        <Card>
          <Empty icon={BookOpenCheck}>
            No research findings are available yet. Run a diagnosis on a dataset version to generate the first evidence report.
          </Empty>
        </Card>
      )}

      {/* Findings list */}
      {!loading && items?.length > 0 && (
        <div className="stack">
          {items.map(({ study, evidence }) => {
            /* Aggregate stats */
            const totalVersions  = evidence.datasets.reduce((a, d) => a + d.versions.length, 0);
            const allMLRS        = evidence.datasets
              .flatMap(d => d.versions)
              .map(v => v.diagnosis?.mlrs_score)
              .filter(s => s != null);
            const avgMLRS        = allMLRS.length
              ? (allMLRS.reduce((a, b) => a + b, 0) / allMLRS.length).toFixed(1)
              : null;
            const maxRisk        = allMLRS.length ? Math.max(...allMLRS) : null;
            const riskTone       = maxRisk == null ? "neutral" : maxRisk >= 70 ? "high" : maxRisk >= 40 ? "medium" : "low";

            return (
              <Card key={study.id} className="no-hover">
                {/* Study header */}
                <div className="row" style={{ marginBottom: "var(--sp-4)", alignItems: "flex-start" }}>
                  <div style={{ minWidth: 0 }}>
                    <p className="eyebrow">
                      <BookOpenCheck size={12} style={{ verticalAlign: "-2px", marginRight: 5 }} />
                      {study.ml_task || "ML"} study
                    </p>
                    <h2 style={{ marginBottom: "var(--sp-2)" }}>{study.name}</h2>

                    {/* Quick stats strip */}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-3)", alignItems: "center" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--color-text-muted)" }}>
                        <Database size={13} />
                        {evidence.datasets.length} dataset{evidence.datasets.length !== 1 ? "s" : ""}
                      </span>
                      <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--color-text-muted)" }}>
                        <FileStack size={13} />
                        {totalVersions} version{totalVersions !== 1 ? "s" : ""}
                      </span>
                      {avgMLRS != null && (
                        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12, color: "var(--color-text-muted)" }}>
                          <TrendingDown size={13} />
                          Avg MLRS {avgMLRS}
                        </span>
                      )}
                      <Badge tone="neutral">{study.ml_task || "—"}</Badge>
                      {maxRisk != null && <Badge tone={riskTone}>Peak risk {maxRisk.toFixed(1)}</Badge>}
                    </div>
                  </div>

                  <Link
                    className="button secondary compact"
                    to={`/studies/${study.id}`}
                    style={{ flexShrink: 0 }}
                  >
                    Open workspace
                    <ArrowUpRight size={14} />
                  </Link>
                </div>

                {/* Dataset summary grid */}
                {evidence.datasets.length > 0 ? (
                  <div className="finding-summary-grid">
                    {evidence.datasets.map(row => {
                      const latest     = row.versions.at(-1);
                      const latestMLRS = latest?.diagnosis?.mlrs_score;
                      const latestLRS  = latest?.diagnosis?.lrs_score;

                      return (
                        <div key={row.dataset.id} className="finding-summary">
                          <strong title={row.dataset.name}>{row.dataset.name}</strong>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: "var(--sp-2)" }}>
                            <span style={{ fontSize: 10, color: "var(--color-text-muted)" }}>
                              {row.versions.length} version{row.versions.length !== 1 ? "s" : ""}
                            </span>
                          </div>
                          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: "var(--sp-1)" }}>
                            <RiskBadge score={latestMLRS} />
                            {latestLRS != null && (
                              <Badge tone={latestLRS >= 70 ? "high" : latestLRS >= 40 ? "medium" : "low"}>
                                LRS {Number(latestLRS).toFixed(1)}
                              </Badge>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>
                    No datasets registered in this study yet.
                  </p>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
