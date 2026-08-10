import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ClipboardCheck, Filter, FlaskConical,
  GitBranch, Plus, ShieldCheck, Target
} from "lucide-react";
import { studyApi } from "../api/client";
import { Badge, Button, Card, DataTable, Field, Notice, PageHeader } from "../components/UI";

const initial = {
  name: "", ml_task: "", domain: "", focus_issue: "",
  target_column: "", primary_metric: "", objective: "",
  research_question: "", hypothesis: "", baseline_model: "",
  validation_strategy: "", random_seed: "", feature_scope: "",
  intended_use_case: ""
};

function valueOrPending(v) { return v?.trim() || "Not specified"; }
function compactLines(lines) { return lines.filter(l => !l.endsWith(": ")); }

function buildProtocol(form) {
  const taskLabel = form.ml_task
    ? form.ml_task.charAt(0).toUpperCase() + form.ml_task.slice(1)
    : "Not specified";
  return {
    taskLabel,
    target: form.ml_task === "clustering"
      ? valueOrPending(form.feature_scope)
      : valueOrPending(form.target_column),
    domain:    valueOrPending(form.domain),
    objective: valueOrPending(form.objective),
    question:  valueOrPending(form.research_question),
    hypothesis:valueOrPending(form.hypothesis),
    intendedUse:valueOrPending(form.intended_use_case),
  };
}

function readinessScore(form) {
  const checks = [
    form.name, form.domain, form.focus_issue, form.ml_task,
    form.ml_task === "clustering" || form.target_column,
    form.primary_metric, form.objective || form.research_question,
    form.validation_strategy, form.random_seed,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

/* Readiness progress bar */
function ReadinessBar({ value }) {
  const cls = value >= 80 ? "complete" : value >= 50 ? "partial" : "low";
  const color = value >= 80
    ? "var(--color-success)"
    : value >= 50 ? "var(--color-warning)" : "var(--color-danger)";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: 11, color: "var(--color-text-muted)", fontWeight: 600 }}>Protocol readiness</span>
        <span style={{ fontSize: 13, fontWeight: 700, color, letterSpacing: "-0.02em" }}>{value}%</span>
      </div>
      <div style={{
        height: 6, background: "var(--color-surface-3)",
        borderRadius: "var(--radius-full)", overflow: "hidden",
      }}>
        <div style={{
          height: "100%", width: `${value}%`,
          background: color,
          borderRadius: "var(--radius-full)",
          transition: "width 0.5s var(--ease-out)",
        }} />
      </div>
    </div>
  );
}

export default function StudiesPage() {
  const navigate = useNavigate();
  const [studies,    setStudies]    = useState([]);
  const [search,     setSearch]     = useState("");
  const [taskFilter, setTaskFilter] = useState("");
  const [form,       setForm]       = useState(initial);
  const [error,      setError]      = useState("");
  const [creating,   setCreating]   = useState(false);

  const load = () => studyApi.list(search, taskFilter).then(setStudies);
  useEffect(() => { load(); }, []);

  const protocol  = buildProtocol(form);
  const readiness = readinessScore(form);
  const readTone  = readiness >= 80 ? "success" : readiness >= 50 ? "warning" : "neutral";

  const updateForm = patch => setForm(f => ({ ...f, ...patch }));

  const create = async (e) => {
    e.preventDefault();
    setError("");
    setCreating(true);
    const payload = {
      name:    form.name,
      ml_task: form.ml_task,
      description: compactLines([
        `Domain: ${form.domain.trim()}`,
        `Task: ${protocol.taskLabel}`,
        `Research question: ${form.research_question.trim()}`,
        `Hypothesis: ${form.hypothesis.trim()}`,
        `Target or grouping goal: ${(form.ml_task === "clustering" ? form.feature_scope : form.target_column).trim()}`,
      ]).join("\n") || null,
      problem_objective: form.objective.trim() || null,
      intended_use_case: compactLines([
        `Intended research use: ${form.intended_use_case.trim()}`,
        `Data quality focus: ${form.focus_issue.trim()}`,
        `Primary metric: ${form.primary_metric.trim()}`,
        `Controlled model: ${form.baseline_model.trim()}`,
        `Validation plan: ${form.validation_strategy.trim()}`,
        `Random seed: ${form.random_seed.trim()}`,
        `Feature scope: ${form.feature_scope.trim()}`,
      ]).join("\n") || null,
    };
    try {
      const study = await studyApi.create(payload);
      navigate(`/studies/${study.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not create study. Please try again.");
      setCreating(false);
    }
  };

  const dirColumns = [
    {
      key: "name", label: "Study", sortable: false,
      render: row => (
        <Link className="study-link" to={`/studies/${row.id}`}>
          <strong>{row.name}</strong>
          <span>Open workspace →</span>
        </Link>
      ),
    },
    {
      key: "ml_task", label: "Task", sortable: false,
      render: row => <Badge>{row.ml_task || "—"}</Badge>,
    },
    {
      key: "status", label: "Status", sortable: false,
      render: row => <Badge tone="success">{row.status || "active"}</Badge>,
    },
    {
      key: "updated_at", label: "Updated", sortable: false,
      render: row => (
        <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
          {new Date(row.updated_at).toLocaleDateString(undefined, {
            month: "short", day: "numeric", year: "numeric"
          })}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Research workspaces"
        title="ML Studies"
        description="Define research intent first, then collect immutable dataset evidence, configurations, profiles, and diagnoses inside one auditable workspace."
      />

      <div className="studies-layout">
        {/* ── Left: Study builder ── */}
        <div className="stack">
          <Card className="study-builder-card">
            <div className="row" style={{ marginBottom: "var(--sp-1)" }}>
              <div>
                <p className="eyebrow">Protocol builder</p>
                <h2 style={{ margin: 0 }}>New ML study</h2>
              </div>
              <span className="metric-icon">
                <ClipboardCheck size={16} />
              </span>
            </div>
            <p className="section-intro">
              Create a structured research protocol before any dataset is registered.
              These fields become the study context used by evidence, diagnosis, and reporting screens.
            </p>

            <form className="protocol-form" onSubmit={create} noValidate>
              {/* Section 1 */}
              <div className="protocol-section full">
                <div className="protocol-section-title">
                  <span aria-hidden="true">1</span>
                  <div>
                    <h3>Study identity</h3>
                    <p>Name the investigation and define its ML task.</p>
                  </div>
                </div>
                <div className="protocol-field-grid">
                  <Field label="Study name" full>
                    <input
                      id="study-name"
                      value={form.name}
                      onChange={e => updateForm({ name: e.target.value })}
                      placeholder="Name this research study"
                      required
                    />
                  </Field>
                  <Field label="Dataset domain">
                    <input
                      id="study-domain"
                      value={form.domain}
                      onChange={e => updateForm({ domain: e.target.value })}
                      placeholder="e.g. healthcare, finance, NLP"
                    />
                  </Field>
                  <Field label="ML task">
                    <select
                      id="study-ml-task"
                      value={form.ml_task}
                      onChange={e => updateForm({ ml_task: e.target.value })}
                      required
                    >
                      <option value="">Select ML task…</option>
                      <option value="classification">Classification</option>
                      <option value="regression">Regression</option>
                      <option value="clustering">Clustering</option>
                    </select>
                  </Field>
                </div>
              </div>

              {/* Section 2 */}
              <div className="protocol-section full">
                <div className="protocol-section-title">
                  <span aria-hidden="true">2</span>
                  <div>
                    <h3>Research intent</h3>
                    <p>State the data quality issue and the question the study should answer.</p>
                  </div>
                </div>
                <div className="protocol-field-grid">
                  <Field label="Data quality focus">
                    <input
                      value={form.focus_issue}
                      onChange={e => updateForm({ focus_issue: e.target.value })}
                      placeholder="e.g. class imbalance, missing values"
                    />
                  </Field>
                  <Field label="Primary evaluation metric">
                    <input
                      value={form.primary_metric}
                      onChange={e => updateForm({ primary_metric: e.target.value })}
                      placeholder="e.g. F1-score, RMSE, silhouette"
                    />
                  </Field>
                  {form.ml_task !== "clustering" && (
                    <Field label="Target column">
                      <input
                        value={form.target_column}
                        onChange={e => updateForm({ target_column: e.target.value })}
                        placeholder="Column name to predict"
                      />
                    </Field>
                  )}
                  <Field label={form.ml_task === "clustering" ? "Grouping goal" : "Feature scope"}>
                    <input
                      value={form.feature_scope}
                      onChange={e => updateForm({ feature_scope: e.target.value })}
                      placeholder={form.ml_task === "clustering" ? "Describe the grouping goal" : "Describe included features"}
                    />
                  </Field>
                  <Field label="Research objective" full>
                    <textarea
                      value={form.objective}
                      onChange={e => updateForm({ objective: e.target.value })}
                      placeholder="State the objective in your own words…"
                    />
                  </Field>
                  <Field label="Research question" full>
                    <textarea
                      value={form.research_question}
                      onChange={e => updateForm({ research_question: e.target.value })}
                      placeholder="What question should this study answer?"
                    />
                  </Field>
                  <Field label="Hypothesis" full>
                    <textarea
                      value={form.hypothesis}
                      onChange={e => updateForm({ hypothesis: e.target.value })}
                      placeholder="State the expected effect, or leave blank if not yet known"
                    />
                  </Field>
                </div>
              </div>

              {/* Section 3 */}
              <div className="protocol-section full">
                <div className="protocol-section-title">
                  <span aria-hidden="true">3</span>
                  <div>
                    <h3>Reproducibility controls</h3>
                    <p>Lock the settings that must stay fixed across dataset variants.</p>
                  </div>
                </div>
                <div className="protocol-field-grid">
                  <Field label="Controlled baseline model">
                    <input
                      value={form.baseline_model}
                      onChange={e => updateForm({ baseline_model: e.target.value })}
                      placeholder="e.g. LogisticRegression, RandomForest"
                    />
                  </Field>
                  <Field label="Validation strategy">
                    <input
                      value={form.validation_strategy}
                      onChange={e => updateForm({ validation_strategy: e.target.value })}
                      placeholder="e.g. 5-fold cross-validation"
                    />
                  </Field>
                  <Field label="Random seed" hint="Required for reproducibility">
                    <input
                      value={form.random_seed}
                      onChange={e => updateForm({ random_seed: e.target.value })}
                      inputMode="numeric"
                      placeholder="e.g. 42"
                    />
                  </Field>
                  <Field label="Intended research use">
                    <textarea
                      value={form.intended_use_case}
                      onChange={e => updateForm({ intended_use_case: e.target.value })}
                      placeholder="How will this protocol support later analysis?"
                    />
                  </Field>
                </div>
              </div>

              {error && (
                <div className="field full">
                  <Notice error>{error}</Notice>
                </div>
              )}

              <div className="field full">
                <Button
                  id="create-study-submit-btn"
                  loading={creating}
                  style={{ alignSelf: "flex-start" }}
                >
                  <FlaskConical size={15} />
                  Create research workspace
                </Button>
              </div>
            </form>
          </Card>
        </div>

        {/* ── Right column: Protocol preview + Directory ── */}
        <div className="stack">
          {/* Protocol preview card */}
          <Card className="protocol-preview-card">
            <div className="row" style={{ marginBottom: "var(--sp-3)" }}>
              <div>
                <p className="eyebrow">Live protocol</p>
                <h2 style={{ margin: 0 }}>Protocol preview</h2>
              </div>
              <Badge tone={readTone}>{readiness}% ready</Badge>
            </div>

            {/* Workflow pipeline figure */}
            <div
              className="protocol-figure"
              aria-label="Study workflow stages"
              style={{ marginBottom: "var(--sp-4)" }}
            >
              {["Study", "Evidence", "Diagnosis", "Variants", "Findings"].map((stage, i) => (
                <span key={stage} style={{
                  background: i === 0 && form.name ? "var(--color-primary-soft)" : undefined,
                  borderColor: i === 0 && form.name ? "var(--color-primary-line)" : undefined,
                  color: i === 0 && form.name ? "var(--color-primary)" : undefined,
                  fontWeight: i === 0 && form.name ? 700 : undefined,
                }}>
                  {stage}
                </span>
              ))}
            </div>

            {/* Readiness bar */}
            <ReadinessBar value={readiness} />

            {/* Readiness message */}
            <p style={{
              margin: "var(--sp-3) 0 var(--sp-4)",
              fontSize: 12,
              color: "var(--color-text-muted)",
              lineHeight: 1.6,
            }}>
              {readiness >= 80
                ? "✓ The protocol has enough structure to begin evidence registration."
                : "Complete the missing research fields to make this study easier to reproduce and report."}
            </p>

            {/* Protocol field preview */}
            <div className="protocol-preview-list">
              <div>
                <Target size={14} />
                <span>
                  <strong>Research question</strong>
                  {protocol.question}
                </span>
              </div>
              <div>
                <GitBranch size={14} />
                <span>
                  <strong>Objective</strong>
                  {protocol.objective}
                </span>
              </div>
              <div>
                <ShieldCheck size={14} />
                <span>
                  <strong>Reproducibility controls</strong>
                  Model: {valueOrPending(form.baseline_model)};
                  validation: {valueOrPending(form.validation_strategy)};
                  seed: {valueOrPending(form.random_seed)}
                </span>
              </div>
            </div>
          </Card>

          {/* Study directory */}
          <Card className="study-directory-card">
            <div className="directory-header">
              <div>
                <p className="eyebrow">Workspace directory</p>
                <h2 style={{ marginBottom: 4 }}>Existing studies</h2>
                <p>Open a saved research workspace or narrow the list by name and task.</p>
              </div>
              <Badge tone={studies.length > 0 ? "info" : "neutral"}>
                {studies.length} {studies.length === 1 ? "study" : "studies"}
              </Badge>
            </div>

            <div className="directory-filter-row">
              <Field label="Search">
                <input
                  aria-label="Search studies by name"
                  placeholder="Search by study name…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && load()}
                />
              </Field>
              <Field label="ML task">
                <select
                  aria-label="Filter by ML task"
                  value={taskFilter}
                  onChange={e => setTaskFilter(e.target.value)}
                >
                  <option value="">All tasks</option>
                  <option value="classification">Classification</option>
                  <option value="regression">Regression</option>
                  <option value="clustering">Clustering</option>
                </select>
              </Field>
              <div className="directory-filter-action">
                <Button
                  id="studies-filter-btn"
                  variant="secondary"
                  onClick={load}
                  aria-label="Apply filters"
                >
                  <Filter size={14} />
                  Filter
                </Button>
              </div>
            </div>

            <div className="directory-table">
              <DataTable
                rows={studies}
                columns={dirColumns}
                empty="No studies match the current filters. Create one using the protocol builder."
              />
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
