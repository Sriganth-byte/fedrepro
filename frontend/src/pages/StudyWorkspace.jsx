import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Database,
  Fingerprint,
  LayoutDashboard,
  Loader2,
  ShieldCheck,
  Zap
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { datasetApi, studyApi } from "../api/client";
import { Badge, Notice, PageHeader, Skeleton } from "../components/UI";
import {
  DiagnosisPanel,
  EnhancedEvidencePanel,
  EnhancedOverviewPanel,
  VariantGeneratorPanel,
  VersionPanel
} from "../features/studies/WorkspacePanels";

const TABS = [
  { id: "overview",  label: "Overview",              icon: LayoutDashboard, desc: "Study protocol & readiness"    },
  { id: "evidence",  label: "Dataset Evidence",       icon: Database,        desc: "Register & manage datasets"    },
  { id: "versions",  label: "Versions & Fingerprints",icon: Fingerprint,     desc: "Version analysis & lineage"   },
  { id: "diagnosis", label: "Diagnosis",              icon: ShieldCheck,     desc: "Risk profile & interventions"  },
  { id: "variants",  label: "Variant Generator",      icon: Zap,             desc: "Preprocessing pipeline builder"},
];

/* Loading skeleton for the workspace header */
function WorkspaceSkeleton() {
  return (
    <div className="workspace-shell" style={{ padding: "var(--sp-5) var(--sp-6)" }}>
      <Skeleton height={12} width={120} style={{ marginBottom: 16 }} />
      <Skeleton height={28} width="55%" style={{ marginBottom: 10 }} />
      <Skeleton height={14} width="40%" />
      <div style={{ display: "flex", gap: 8, marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--color-border)" }}>
        {[0,1,2,3,4].map(i => <Skeleton key={i} height={36} width={140} />)}
      </div>
    </div>
  );
}

export default function StudyWorkspace() {
  const { studyId } = useParams();
  const [study,             setStudy]             = useState(null);
  const [datasets,          setDatasets]          = useState([]);
  const [configuration,     setConfiguration]     = useState(null);
  const [active,            setActive]            = useState("overview");
  const [version,           setVersion]           = useState(null);
  const [profile,           setProfile]           = useState(null);
  const [diagnosis,         setDiagnosis]         = useState(null);
  const [diagnosisContract, setDiagnosisContract] = useState(null);
  const [semanticHistory,   setSemanticHistory]   = useState([]);
  const [versionStatus,     setVersionStatus]     = useState("");
  const [versionLoading,    setVersionLoading]    = useState(false);

  const refresh = async () => setDatasets(await datasetApi.list(studyId));

  useEffect(() => {
    Promise.all([
      studyApi.get(studyId),
      datasetApi.list(studyId),
      studyApi.currentConfiguration(studyId),
    ]).then(([studyResult, datasetResult, configResult]) => {
      setStudy(studyResult);
      setDatasets(datasetResult);
      setConfiguration(configResult);
    });
  }, [studyId]);

  const selectVersion = async (idOrVersion, nextActive = "versions") => {
    const id = typeof idOrVersion === "object" ? idOrVersion.id : idOrVersion;
    setVersionLoading(true);
    setVersionStatus("");
    try {
      const analysis = await datasetApi.analysis(id);
      setVersion(analysis.version);
      setProfile(analysis.profile);
      setDiagnosis(analysis.diagnosis);
      setDiagnosisContract(
        analysis.diagnosis
          ? await datasetApi.diagnosisContract(id).catch(() => null)
          : null
      );
      setSemanticHistory(analysis.timeline);
      setActive(nextActive);
    } catch (err) {
      setVersionStatus(err.response?.data?.detail || "Could not load this version's analysis.");
    } finally {
      setVersionLoading(false);
    }
  };

  const deleteVersion = async (id) => {
    setVersionStatus("Deleting version and its analysis…");
    try {
      await datasetApi.deleteVersion(id);
      if (version?.id === id) {
        setVersion(null); setProfile(null);
        setDiagnosis(null); setDiagnosisContract(null);
        setSemanticHistory([]);
      }
      await refresh();
      setVersionStatus("Version deleted successfully.");
    } catch (err) {
      setVersionStatus(err.response?.data?.detail || "Could not delete this version.");
    }
  };

  if (!study) return <WorkspaceSkeleton />;

  const taskLabel = study.ml_task
    ? study.ml_task.charAt(0).toUpperCase() + study.ml_task.slice(1)
    : "ML";

  const panels = {
    overview:  <EnhancedOverviewPanel
                 study={study} datasets={datasets} configuration={configuration}
                 onStudyUpdate={setStudy} onOpenEvidence={() => setActive("evidence")}
                 onOpenVersions={id => id ? selectVersion(id) : setActive("versions")}
                 onOpenDiagnosis={() => setActive("diagnosis")}
                 selectedVersion={version} diagnosis={diagnosis}
                 diagnosisContract={diagnosisContract}
               />,
    evidence:  <EnhancedEvidencePanel
                 study={study} datasets={datasets} refresh={refresh}
                 onVersion={selectVersion}
               />,
    versions:  <VersionPanel
                 study={study} datasets={datasets} selectedVersion={version}
                 profile={profile} semanticHistory={semanticHistory}
                 onVersion={selectVersion} onDelete={deleteVersion}
                 onOpenDiagnosis={() => setActive("diagnosis")}
                 status={versionStatus}
               />,
    diagnosis: <DiagnosisPanel
                 study={study} datasets={datasets} version={version}
                 profile={profile} diagnosis={diagnosis}
                 initialContract={diagnosisContract}
                 onVersion={id => selectVersion(id, "diagnosis")}
                 onOpenVariants={() => setActive("variants")}
               />,
    variants:  <VariantGeneratorPanel version={version} diagnosis={diagnosis} />,
  };

  return (
    <>
      <div className="workspace-shell">
        {/* Summary header */}
        <div className="workspace-summary">
          <Link
            className="eyebrow"
            to="/studies"
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              marginBottom: "var(--sp-3)", color: "var(--color-text-muted)",
              transition: "color var(--duration-fast)",
              textDecoration: "none",
            }}
            onMouseEnter={e => e.currentTarget.style.color = "var(--color-primary)"}
            onMouseLeave={e => e.currentTarget.style.color = "var(--color-text-muted)"}
          >
            <ArrowLeft size={12} aria-hidden="true" />
            All ML studies
          </Link>

          <PageHeader
            eyebrow={`${taskLabel} Study · ID ${study.id}`}
            title={study.name}
            description={`Deterministic, version-aware evidence pipeline · ${datasets.length} dataset${datasets.length !== 1 ? "s" : ""} registered`}
            action={
              <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", flexShrink: 0 }}>
                {versionLoading && (
                  <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--color-text-muted)" }}>
                    <Loader2 size={14} className="spin" /> Loading analysis…
                  </span>
                )}
                <Badge tone={datasets.length > 0 ? "success" : "neutral"}>
                  {datasets.length} dataset{datasets.length !== 1 ? "s" : ""}
                </Badge>
                {version && <Badge tone="info">V{version.id} selected</Badge>}
              </div>
            }
          />

          {versionStatus && !versionLoading && (
            <div style={{ marginBottom: "var(--sp-4)" }}>
              <Notice
                success={versionStatus.includes("deleted") || versionStatus.includes("success")}
                error={versionStatus.includes("Could not") || versionStatus.includes("error")}
              >
                {versionStatus}
              </Notice>
            </div>
          )}
        </div>

        {/* Tab navigation */}
        <nav className="workspace-tabs" aria-label="Study workflow sections">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={active === id ? "active" : ""}
              onClick={() => setActive(id)}
              aria-current={active === id ? "page" : undefined}
              title={TABS.find(t => t.id === id)?.desc}
              id={`workspace-tab-${id}`}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
            </button>
          ))}
        </nav>
      </div>

      {/* Panel content */}
      <div className="workspace-body" key={active}>
        {panels[active]}
      </div>
    </>
  );
}
