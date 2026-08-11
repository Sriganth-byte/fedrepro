import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ClipboardCheck, Copy, Database, Edit3, Eye, FileCheck2, FileStack, Gauge, GitBranch, GitCompare, Loader2, Network, ScanSearch, ShieldCheck, Sparkles, TableProperties, Target, Trash2, UploadCloud, Zap } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { aiApi, datasetApi, studyApi, variantApi } from "../../api/client";
import { Badge, Button, Card, CopyButton, DataTable, Empty, Field, MetricCard, Notice, Skeleton, SkeletonCard, StatusDot } from "../../components/UI";

const emptyProtocol = { name: "", ml_task: "", domain: "", focus_issue: "", target_column: "", primary_metric: "", objective: "", research_question: "", hypothesis: "", baseline_model: "", validation_strategy: "", random_seed: "", feature_scope: "", intended_use_case: "" };

function parseLines(text) {
  return String(text || "").split("\n").reduce((acc, line) => {
    const index = line.indexOf(":");
    if (index > -1) acc[line.slice(0, index).trim().toLowerCase()] = line.slice(index + 1).trim();
    return acc;
  }, {});
}

function protocolFromStudy(study) {
  const description = parseLines(study.description);
  const intended = parseLines(study.intended_use_case);
  return {
    ...emptyProtocol,
    name: study.name || "",
    ml_task: study.ml_task || "",
    domain: description.domain || "",
    target_column: description["target or grouping goal"] || "",
    objective: study.problem_objective || "",
    research_question: description["research question"] || "",
    hypothesis: description.hypothesis || "",
    intended_use_case: intended["intended research use"] || "",
    focus_issue: intended["data quality focus"] || "",
    primary_metric: intended["primary metric"] || "",
    baseline_model: intended["controlled model"] || "",
    validation_strategy: intended["validation plan"] || "",
    random_seed: intended["random seed"] || "",
    feature_scope: intended["feature scope"] || ""
  };
}

function protocolFromConfiguration(study, configuration) {
  if (!configuration) return protocolFromStudy(study);
  return {
    ...emptyProtocol,
    name: study.name || "",
    ml_task: configuration.ml_task || study.ml_task || "",
    domain: configuration.domain || "",
    focus_issue: configuration.data_quality_focus || "",
    target_column: configuration.target_column || "",
    primary_metric: configuration.primary_metric || "",
    objective: configuration.research_objective || "",
    research_question: configuration.research_question || "",
    hypothesis: configuration.hypothesis || "",
    baseline_model: configuration.baseline_model || "",
    validation_strategy: configuration.validation_strategy || "",
    random_seed: configuration.random_seed === null || configuration.random_seed === undefined ? "" : String(configuration.random_seed),
    feature_scope: configuration.feature_scope || "",
    intended_use_case: configuration.intended_use_case || ""
  };
}

function compactLines(lines) {
  return lines.filter((line) => !line.endsWith(": "));
}

function payloadFromProtocol(form) {
  return {
    name: form.name,
    ml_task: form.ml_task,
    description: compactLines([
      `Domain: ${form.domain.trim()}`,
      `Task: ${form.ml_task}`,
      `Research question: ${form.research_question.trim()}`,
      `Hypothesis: ${form.hypothesis.trim()}`,
      `Target or grouping goal: ${(form.ml_task === "clustering" ? form.feature_scope : form.target_column).trim()}`
    ]).join("\n") || null,
    problem_objective: form.objective.trim() || null,
    intended_use_case: compactLines([
      `Intended research use: ${form.intended_use_case.trim()}`,
      `Data quality focus: ${form.focus_issue.trim()}`,
      `Primary metric: ${form.primary_metric.trim()}`,
      `Controlled model: ${form.baseline_model.trim()}`,
      `Validation plan: ${form.validation_strategy.trim()}`,
      `Random seed: ${form.random_seed.trim()}`,
      `Feature scope: ${form.feature_scope.trim()}`
    ]).join("\n") || null
  };
}

function configurationPayloadFromProtocol(form) {
  const randomSeed = String(form.random_seed || "").trim();
  return {
    ml_task: form.ml_task,
    domain: form.domain,
    data_quality_focus: form.focus_issue,
    research_objective: form.objective,
    research_question: form.research_question,
    hypothesis: form.hypothesis,
    target_column: form.ml_task === "clustering" ? null : form.target_column,
    primary_metric: form.primary_metric,
    baseline_model: form.baseline_model,
    validation_strategy: form.validation_strategy,
    random_seed: randomSeed ? Number(randomSeed) : null,
    feature_scope: form.feature_scope,
    intended_use_case: form.intended_use_case,
    change_reason: "Updated from study workspace"
  };
}

function shown(value) {
  return value || "Not documented";
}

function workflowTone(status) {
  if (status === "Complete") return "low";
  if (status === "Current" || status === "Needs attention") return "medium";
  return "default";
}

function stageStatus(done, current) {
  if (done) return "Complete";
  return current ? "Current" : "Pending";
}

function evidenceQuality(metadata = {}) {
  const dataTypes = metadata.data_types || {};
  const missingValues = metadata.missing_values || {};
  const columns = metadata.column_names || [];
  const numericCount = Object.values(dataTypes).filter((type) => /int|float|double|decimal|number/i.test(String(type))).length;
  const suspiciousIdentifierColumns = columns.filter((column) => /(^id$|_id$|uuid|identifier|email|phone)/i.test(column));
  const issueColumns = columns.filter((column) => (missingValues[column] || 0) > 0 || suspiciousIdentifierColumns.includes(column));
  return {
    missingCells: metadata.missing_total ?? 0,
    duplicateRows: metadata.duplicate_count ?? 0,
    constantColumns: [],
    highCardinalityColumns: [],
    numericCount,
    categoricalCount: Math.max(0, columns.length - numericCount),
    suspiciousIdentifierColumns,
    issueColumns,
  };
}

function aiFallbackMessage() {
  return "Interpretation temporarily unavailable. The measured evidence remains available below.";
}

function overviewGaps({ hasDataset, configured, latest, hasDiagnosis, hasSemantic, hasContract, diagnosisContract, protocol, onOpenEvidence, onOpenVersions, onOpenDiagnosis }) {
  const gaps=[];
  if(!hasDataset)gaps.push({title:"No Dataset Registered",why:"The study has no dataset evidence to profile, fingerprint, or diagnose.",impact:"Versioning, diagnosis, variant planning, and experiments cannot start.",recommendation:"Register Dataset",action:onOpenEvidence});
  if(hasDataset&&!configured)gaps.push({title:"No Immutable Version",why:"Uploaded evidence has not been configured into a versioned research artifact.",impact:"Fingerprinting, profiling, and diagnosis remain unavailable.",recommendation:"Configure Evidence",action:onOpenEvidence});
  if(configured&&!latest?.configuration?.target_column&&!protocol.target_column)gaps.push({title:"Target Column Missing",why:"The study does not expose a target or grouping goal in the selected version/protocol.",impact:"Diagnosis and experiment planning have weaker task context.",recommendation:"Review Configuration",action:()=>onOpenVersions(latest?.id)});
  if(configured&&!hasDiagnosis)gaps.push({title:"Diagnosis Not Generated",why:"Risk findings and intervention planning require a persisted diagnosis report.",impact:"Variant planning and experiment cautions cannot be produced.",recommendation:"Open Version",action:()=>onOpenVersions(latest?.id)});
  if(configured&&!hasSemantic&&latest?.parent_version_id)gaps.push({title:"Semantic Diff Unavailable",why:"The selected revision does not expose a semantic comparison with its predecessor.",impact:"Cross-version comparability cannot be reviewed.",recommendation:"Open Versioning",action:()=>onOpenVersions(latest?.id)});
  if(configured&&!latest?.fingerprint)gaps.push({title:"Recreation Bundle Missing",why:"A recreation bundle depends on fingerprint and configuration evidence.",impact:"A candidate CSV cannot be verified as the same version.",recommendation:"Open Fingerprints",action:()=>onOpenVersions(latest?.id)});
  if(hasContract&&diagnosisContract?.human_decisions?.length)gaps.push({title:"Pending Human Decisions",why:"Some interventions require researcher approval before variant generation.",impact:"The future variant generator should not apply these actions automatically.",recommendation:"Review Diagnosis",action:onOpenDiagnosis});
  if(hasDiagnosis&&!hasContract)gaps.push({title:"Variant Planning Not Started",why:"Diagnosis exists, but no diagnosis contract is loaded for intervention planning.",impact:"Generator handoff and experiment constraints are not ready.",recommendation:"Open Diagnosis",action:onOpenDiagnosis});
  return gaps;
}

function overviewTimeline(study, datasets, versions, diagnosis) {
  const events=[];
  if(study?.created_at)events.push({label:"Study Created",date:study.created_at});
  datasets.forEach((dataset)=>{if(dataset.created_at)events.push({label:`Dataset Registered: ${dataset.name}`,date:dataset.created_at});});
  versions.forEach((version)=>{
    if(version.created_at)events.push({label:`Version Created: V${version.version_number}`,date:version.created_at});
    if(version.fingerprint&&version.created_at)events.push({label:`Fingerprint Generated: V${version.version_number}`,date:version.created_at});
  });
  if(diagnosis?.created_at)events.push({label:"Diagnosis Generated",date:diagnosis.created_at});
  return events.filter((item)=>item.date).sort((a,b)=>new Date(a.date)-new Date(b.date));
}

function overviewClaims({ hasDataset, configured, hasDiagnosis, hasFingerprint, hasContract }) {
  return [
    {title:"Dataset Registered",supported:hasDataset,reason:hasDataset?"At least one dataset record exists in the study evidence registry.":"No dataset registration is available yet."},
    {title:"Diagnosis Complete",supported:hasDiagnosis,reason:hasDiagnosis?"A diagnosis report is available for the selected/latest version.":"Diagnosis findings are not available for the selected/latest version."},
    {title:"Dataset Version Verified",supported:hasFingerprint&&configured,reason:hasFingerprint&&configured?"An immutable version and fingerprint evidence exist.":"A version fingerprint is required before this claim is supported."},
    {title:"Reproducibility Proven",supported:false,reason:"A recreated candidate dataset must be verified against the recreation bundle before this claim is supported."},
    {title:"Intervention Improves Performance",supported:false,reason:"Experiments are required; diagnosis can propose interventions but cannot prove metric improvement."},
    {title:"Experiments Required",supported:hasContract,reason:hasContract?"Diagnosis produced downstream intervention/experiment inputs that must be tested.":"A diagnosis contract is needed before experiment requirements can be formalized."}
  ];
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function ReportActions({ study, compact = false }) {
  return null;
}

export function EnhancedOverviewPanel({ study, datasets, configuration: configurationProp, onStudyUpdate, onOpenEvidence, onOpenVersions, onOpenDiagnosis, selectedVersion, diagnosis, diagnosisContract }) {
  const [editing,setEditing]=useState(false);
  const [form,setForm]=useState(()=>configurationProp?protocolFromConfiguration(study,configurationProp):protocolFromStudy(study));
  const [configuration,setConfiguration]=useState(configurationProp||null);
  const [configurationHistory,setConfigurationHistory]=useState([]);
  const [status,setStatus]=useState("");
  const [aiResult,setAiResult]=useState(null);
  const [aiStatus,setAiStatus]=useState("");
  useEffect(()=>{
    let active=true;
    // If the parent already supplied the current configuration, skip the extra API call
    const configPromise=configurationProp
      ?Promise.resolve(configurationProp)
      :studyApi.currentConfiguration(study.id).catch(()=>null);
    Promise.all([
      configPromise,
      studyApi.configurationHistory(study.id).catch(()=>[])
    ]).then(([current,history])=>{
      if(!active)return;
      setConfiguration(current);
      setConfigurationHistory(history||[]);
      if(!editing&&current)setForm(protocolFromConfiguration(study,current));
    });
    return ()=>{active=false;};
  },[study.id]);
  const protocol=configuration?protocolFromConfiguration(study,configuration):protocolFromStudy(study);
  const versions=datasets.flatMap((dataset)=>dataset.versions.map((version)=>({...version,dataset_name:dataset.name}))).sort((a,b)=>new Date(a.created_at)-new Date(b.created_at));
  const latest=selectedVersion||versions[versions.length-1];
  const latestDatasetName=latest?.dataset_name||datasets.find((dataset)=>dataset.id===latest?.dataset_id)?.name;
  const configured=versions.length>0;
  const hasProtocol=Boolean(study.name&&study.ml_task&&(protocol.objective||protocol.research_question||study.problem_objective));
  const hasDataset=datasets.length>0;
  const hasConfig=Boolean(latest?.configuration||configured);
  const hasFingerprint=Boolean(latest?.fingerprint);
  const hasProfile=Boolean(latest?.profile_report_id||selectedVersion?.profile_report_id);
  const hasDiagnosis=Boolean(diagnosis||latest?.diagnosis);
  const hasSemantic=Boolean(latest?.semantic_diff)||Boolean(latest?.parent_version_id===null&&latest);
  const hasContract=Boolean(diagnosisContract);
  const hasVariant=versions.some((version)=>version.generation_method&&version.generation_method!=="manual");
  const workflowStages=[
    {id:"study",label:"Study",status:stageStatus(hasProtocol,!hasProtocol),action:()=>setEditing(true),enabled:true},
    {id:"evidence",label:"Evidence",status:stageStatus(hasDataset,hasProtocol&&!hasDataset),action:onOpenEvidence,enabled:true},
    {id:"version",label:"Version",status:stageStatus(configured,hasDataset&&!configured),action:()=>latest?onOpenVersions(latest.id):onOpenVersions(),enabled:hasDataset},
    {id:"fingerprint",label:"Fingerprint",status:stageStatus(hasFingerprint,configured&&!hasFingerprint),action:()=>latest&&onOpenVersions(latest.id),enabled:configured},
    {id:"profile",label:"Profile",status:stageStatus(hasProfile,configured&&!hasProfile),action:()=>latest&&onOpenVersions(latest.id),enabled:configured},
    {id:"diagnosis",label:"Diagnose",status:stageStatus(hasDiagnosis,configured&&!hasDiagnosis),action:onOpenDiagnosis,enabled:configured},
    {id:"variants",label:"Variants",status:stageStatus(hasVariant,hasDiagnosis&&!hasVariant),action:onOpenDiagnosis,enabled:hasDiagnosis},
    {id:"evaluate",label:"Evaluate",status:"Pending",action:onOpenDiagnosis,enabled:hasVariant},
    {id:"reproduce",label:"Reproduce",status:stageStatus(Boolean(hasFingerprint&&latest?.configuration?.configuration_hash),configured&&!hasFingerprint),action:()=>latest&&onOpenVersions(latest.id),enabled:configured}
  ].filter((stage)=>stage.enabled!==false);
  const completedCount=workflowStages.filter((stage)=>stage.status==="Complete").length;
  const workflowCompletion=Math.round((completedCount/Math.max(workflowStages.length,1))*100);
  const currentStage=workflowStages.find((stage)=>stage.status==="Current"||stage.status==="Needs attention")||workflowStages.find((stage)=>stage.status!=="Complete");
  const nextStage=currentStage||workflowStages.at(-1);
  const nextAction=[nextStage?.label?`Continue: ${nextStage.label}`:"Continue workflow",nextStage?.action||onOpenVersions];
  const integrity=[
    ["Dataset hash", latest?.fingerprint?.file_hash||latest?.file_hash],
    ["Schema hash", latest?.fingerprint?.schema_hash],
    ["Configuration hash", latest?.configuration?.configuration_hash],
    ["Fingerprint generated", hasFingerprint],
    ["Diagnosis contract", hasContract],
    ["Profile report", hasProfile],
    ["Semantic diff", latest?.semantic_diff],
    ["Recreation bundle", hasFingerprint&&latest?.configuration?.configuration_hash]
  ];
  const gaps=overviewGaps({hasDataset,configured,latest,hasDiagnosis,hasSemantic,hasContract,diagnosisContract,protocol,onOpenEvidence,onOpenVersions,onOpenDiagnosis});
  const timeline=overviewTimeline(study,datasets,versions,diagnosis);
  const runAi=async(type)=>{
    const payload=type==="diagnosis"&&diagnosis?.id?{explanation_type:"diagnosis",source_entity_id:diagnosis.id}:type==="semantic"&&latest?.semantic_diff?.id?{explanation_type:"semantic_diff",source_entity_id:latest.semantic_diff.id}:{explanation_type:"study_description",source_entity_id:study.id};
    setAiStatus("Generating evidence-bound research brief...");
    setAiResult(null);
    try{setAiResult(await aiApi.explain(study.id,payload));setAiStatus("");}
    catch(err){setAiStatus(aiFallbackMessage());}
  };
  const exportDiagnosisReport=async()=>{
    if(!latest?.id)return;
    setStatus("Preparing diagnosis report...");
    try{downloadBlob(await datasetApi.diagnosisReport(latest.id),`fedrepro-diagnosis-v${latest.version_number}-report.docx`);setStatus("Diagnosis report exported.");}
    catch(err){setStatus(err.response?.data?.detail||"Diagnosis report export failed.");}
  };
  const exportContract=()=>diagnosisContract&&downloadBlob(new Blob([JSON.stringify(diagnosisContract,null,2)],{type:"application/json"}),`fedrepro-diagnosis-v${latest?.version_number||"selected"}-contract.json`);
  const exportRecreation=async()=>{
    if(!latest?.id)return;
    setStatus("Preparing recreation bundle...");
    try{const bundle=await datasetApi.recreationBundle(latest.id);downloadBlob(new Blob([JSON.stringify(bundle,null,2)],{type:"application/json"}),`fedrepro-v${latest.version_number}-recreation-bundle.json`);setStatus("Recreation bundle exported.");}
    catch(err){setStatus(err.response?.data?.detail||"Recreation bundle export failed.");}
  };
  const save=async(event)=>{
    event.preventDefault();
    setStatus("Saving study protocol...");
    try{
      const savedConfiguration=await studyApi.createConfiguration(study.id,configurationPayloadFromProtocol(form));
      const updated=await studyApi.get(study.id);
      setConfiguration(savedConfiguration);
      setConfigurationHistory(await studyApi.configurationHistory(study.id).catch(()=>configurationHistory));
      onStudyUpdate(updated);
      setEditing(false);
      setStatus(`Study protocol V${savedConfiguration.version_number} saved.`);
    }catch(err){
      setStatus(err.response?.data?.detail||"Could not update study protocol.");
    }
  };
  return <div className="stack">
    <Card className="research-identity-card">
      <div className="version-page-head">
        <div><p className="eyebrow">Research workspace</p><h1>{study.name}</h1><p className="muted">Study #{shown(study.id)} · {shown(study.ml_task)} · Protocol V{configuration?.version_number||1} · {shown(protocol.domain)}</p></div>
        <div className="summary-actions"><Button variant="secondary compact" onClick={()=>{setForm(protocol);setEditing(true);setStatus("");}}><Edit3 size={14}/>Edit Study</Button><ReportActions study={study} compact /><Button onClick={nextAction[1]}>{nextAction[0]}</Button></div>
      </div>
      <div className="overview-evidence-strip">
        <VersionState label="Target column" value={protocol.target_column||latest?.configuration?.target_column||"Not Available"} />
        <VersionState label="Primary metric" value={protocol.primary_metric||latest?.configuration?.primary_metric||"Not Available"} />
        <VersionState label="Latest version" value={latest?`V${latest.version_number}`:"Not Available"} />
        <VersionState label="Health fingerprint" value={shortHash(latest?.fingerprint)||"Not Available"} mono />
      </div>
    </Card>

    {/* ── Protocol Completeness Card (Refinement #1) ── */}
    <Card className="protocol-completeness-card">
        <div className="completeness-header">
          <div>
            <p className="eyebrow">Workflow readiness</p>
            <h2>{completedCount} of {workflowStages.length} evidence stages complete</h2>
          </div>
          <span className={`completeness-badge ${workflowCompletion===100?"complete":workflowCompletion>=60?"partial":"low"}`}>
            {workflowCompletion}%
          </span>
        </div>
        <div className="completeness-bar-track" role="progressbar" aria-valuenow={workflowCompletion} aria-valuemin={0} aria-valuemax={100}>
          <div
            className={`completeness-bar-fill ${workflowCompletion===100?"complete":workflowCompletion>=60?"partial":"low"}`}
            style={{width:`${workflowCompletion}%`}}
          />
        </div>
        <div className="workflow-stage-summary">
          {workflowStages.map((stage)=><button key={stage.id} className={`workflow-pill ${stage.status.toLowerCase().replace(/\s+/g,"-")}`} onClick={stage.action} disabled={!stage.action}>
            <span>{stage.label}</span><Badge tone={workflowTone(stage.status)}>{stage.status}</Badge>
          </button>)}
        </div>
        <div className="context-list compact">
          <div className="context-row"><strong>Current stage</strong><span>{currentStage?.label||"Complete"}</span></div>
          <div className="context-row"><strong>Next action</strong><span>{nextAction[0]}</span></div>
          <div className="context-row"><strong>Protocol field score</strong><span>{configuration?.completeness_score??"Not Available"}%</span></div>
        </div>
        {configuration?.missing_fields&&configuration.missing_fields.length>0&&(
          <div className="completeness-missing">
            <p className="eyebrow">Protocol fields still missing</p>
            <div className="completeness-chips">
              {configuration.missing_fields.map((field)=>(
                <span key={field} className="completeness-chip missing">{field.replace(/_/g," ")}</span>
              ))}
            </div>
          </div>
        )}
        {false&&configuration?.missing_fields&&configuration.missing_fields.length===0&&(
          <p className="completeness-all-ok">✓ All 10 protocol fields are documented</p>
        )}
        <div className="completeness-meta">
          {configuration?.change_reason&&<span className="muted">Last protocol change: {configuration.change_reason}</span>}
          {latest&&<span className="muted">Active evidence: {latestDatasetName||"Dataset"} V{latest.version_number}</span>}
        </div>
      </Card>

    <Card className="overview-protocol-card">
      <div className="row">
        <div><p className="eyebrow">Research objective card</p><h2>Protocol intent</h2></div>
        <Button variant="secondary compact" onClick={()=>{setForm(protocol);setEditing(!editing);setStatus("");}}><Edit3 size={14} />{editing?"Close edit":"Edit"}</Button>
      </div>
      {editing?<StudyProtocolEditForm form={form} setForm={setForm} status={status} onCancel={()=>setEditing(false)} onSave={save} />:<div className="overview-context-grid">
        <ProtocolItem icon={GitBranch} label="Research Objective" value={study.problem_objective||protocol.objective} />
        <ProtocolItem icon={Target} label="Research Question" value={protocol.research_question} />
        <ProtocolItem icon={ShieldCheck} label="Hypothesis" value={protocol.hypothesis} />
        <ProtocolItem icon={ScanSearch} label="Data Quality Focus" value={protocol.focus_issue} />
        <ProtocolItem icon={ClipboardCheck} label="Intended Research Use" value={protocol.intended_use_case} />
        <ProtocolItem icon={FileStack} label="Protocol Version" value={`${configuration?.version_number||1} current; ${configurationHistory.length||1} total`} />
      </div>}
    </Card>

    <Card>
      <p className="eyebrow">Workflow progress</p><h2>Research pipeline</h2>
      <div className="workflow-rail">{workflowStages.map((stage)=><button key={stage.id} className={`workflow-stage ${stage.status==="Complete"?"complete":stage.status==="Current"?"review":"pending"}`} disabled={!stage.action} onClick={stage.action}><span>{stage.label}</span><Badge tone={workflowTone(stage.status)}>{stage.status}</Badge></button>)}</div>
    </Card>
    {false&&<>

    <div className="overview-layout">
      <Card className="overview-protocol-card">
        <p className="eyebrow">Research readiness</p><h2>{completedCount} of {workflowStages.length} stages complete</h2>
        <div className="readiness-list">{workflowStages.map((stage)=><div key={stage.id} className={stage.status==="Completed"?"complete":stage.status==="Needs Review"?"review":""}><CheckCircle2 size={15}/><span>{stage.label}</span><Badge tone={stage.status==="Completed"?"low":stage.status==="Needs Review"?"medium":"default"}>{stage.status}</Badge></div>)}</div>
      </Card>
      <Card>
        <p className="eyebrow">Current evidence snapshot</p><h2>Persisted evidence</h2>
        <div className="context-list">
          <div className="context-row"><strong>Dataset count</strong><span>{datasets.length}</span></div>
          <div className="context-row"><strong>Version count</strong><span>{versions.length}</span></div>
          <div className="context-row"><strong>Latest version</strong><span>{latest?`V${latest.version_number}`:"Not Available"}</span></div>
          <div className="context-row"><strong>Latest rows</strong><span>{latest?.row_count??"Not Available"}</span></div>
          <div className="context-row"><strong>Latest columns</strong><span>{latest?.column_count??"Not Available"}</span></div>
          <div className="context-row"><strong>Profile report</strong><span>{hasProfile?"Available":"Not Available"}</span></div>
          <div className="context-row"><strong>Diagnosis</strong><span>{hasDiagnosis?"Available":"Not Available"}</span></div>
          <div className="context-row"><strong>Semantic diff</strong><span>{hasSemantic?"Available":"Not Available"}</span></div>
          <div className="context-row"><strong>Fingerprint</strong><span>{hasFingerprint?"Available":"Not Available"}</span></div>
          <div className="context-row"><strong>Recreation bundle</strong><span>{hasFingerprint?"Available":"Not Available"}</span></div>
        </div>
      </Card>
    </div>

    <Card>
      <p className="eyebrow">Evidence integrity</p><h2>Research evidence checks</h2>
      <div className="integrity-grid">{integrity.map(([label,value])=><div key={label}><strong>{label}</strong>{typeof value==="boolean"?<Badge tone={value?"low":"medium"}>{value?"Verified":"Missing"}</Badge>:value?<HashChip value={value}/>:<Badge tone="medium">Missing</Badge>}</div>)}</div>
    </Card>

    <Card>
      <p className="eyebrow">Latest dataset evidence</p><h2>{latest?`${shown(latestDatasetName)} · V${latest.version_number}`:"No version available"}</h2>
      {!latest?<Empty>No immutable dataset version has been configured yet.</Empty>:<><div className="latest-evidence-grid">
        {[
          ["Version",`V${latest.version_number}`],["Dataset",latestDatasetName],["Rows",latest.row_count],["Columns",latest.column_count],["Created",formatDate(latest.created_at)],["Parent",latest.parent_version_id?`V${latest.parent_version_id}`:"Baseline"],["Fingerprint",shortHash(latest.fingerprint)],["Configuration",shortHash(latest.configuration?.configuration_hash)],["MLRS",diagnosis?.mlrs_score],["LRS",diagnosis?.lrs_score],["SCM",latest.semantic_diff?.scm_score],["DSI",latest.semantic_diff?.dsi_score]
        ].map(([label,value])=><div key={label}><strong>{label}</strong><span className={String(label).includes("Fingerprint")||String(label).includes("Configuration")?"mono":""}>{value??"Not Available"}</span></div>)}
      </div><div className="action-stack horizontal"><Button variant="secondary" onClick={()=>onOpenVersions(latest.id)}><Eye size={15}/>Open Version</Button><Button variant="secondary" disabled={!hasDiagnosis} onClick={onOpenDiagnosis}><ShieldCheck size={15}/>Open Diagnosis</Button><Button variant="secondary" onClick={()=>runAi("semantic")}><Sparkles size={15}/>Generate AI Insight</Button><ReportActions study={study} compact /></div></>}
    </Card>

    <Card>
      <p className="eyebrow">Evidence gaps</p><h2>Missing research evidence</h2>
      {!gaps.length?<Notice>Current evidence is sufficient for the completed pipeline stages.</Notice>:<div className="gap-list">{gaps.map((gap)=><article key={gap.title}><h3>{gap.title}</h3><p>{gap.why}</p><div className="context-list compact"><div className="context-row"><strong>Impact</strong><span>{gap.impact}</span></div></div><Button variant="secondary compact" onClick={gap.action}>{gap.recommendation}</Button></article>)}</div>}
    </Card>

    <div className="grid grid-2">
      <Card>
        <p className="eyebrow">Research dependency graph</p><h2>Downstream readiness</h2>
        <div className="dependency-chain">{[
          ["Diagnosis",hasDiagnosis],["Variant Planning",hasContract],["Experiments",false],["Impact Analysis",false],["Research Findings",false]
        ].map(([label,ready],index)=><div key={label} className={ready?"ready":"blocked"}><span>{label}</span><Badge tone={ready?"low":"medium"}>{ready?"Ready":"Blocked"}</Badge>{index<4&&<em>↓</em>}</div>)}</div>
      </Card>
      <Card>
        <p className="eyebrow">Research readiness preview</p><h2>Diagnosis to experiment signal</h2>
        {!diagnosis?<Empty>Diagnosis evidence is not available yet.</Empty>:<div className="context-list">
          <div className="context-row"><strong>ML readiness</strong><span>{diagnosisContract?.readiness?.status||"Not Available"}</span></div>
          <div className="context-row"><strong>Leakage risk</strong><span>{diagnosis.findings?.some((item)=>item.code==="TARGET_LEAKAGE")?"Detected":"Not Available"}</span></div>
          <div className="context-row"><strong>Risk families</strong><span>{diagnosisContract?.risk_families?.map((item)=>item.family).join(", ")||"Not Available"}</span></div>
          <div className="context-row"><strong>Intervention count</strong><span>{diagnosisContract?.intervention_options?.length??"Not Available"}</span></div>
          <div className="context-row"><strong>Pending decisions</strong><span>{diagnosisContract?.human_decisions?.length??"Not Available"}</span></div>
          <div className="context-row"><strong>Experiment warnings</strong><span>{diagnosisContract?.experiment_handoff?.cautions?.length??"Not Available"}</span></div>
        </div>}
      </Card>
    </div>

    <Card>
      <p className="eyebrow">Research timeline</p><h2>Evidence events</h2>
      {!timeline.length?<Empty>No timestamped evidence events are available.</Empty>:<div className="research-timeline">{timeline.map((item)=><div key={`${item.label}-${item.date}`}><strong>{item.label}</strong><span>{formatDate(item.date)}</span></div>)}</div>}
    </Card>

    <Card>
      <p className="eyebrow">Research evidence vault</p><h2>Export center</h2>
      {status&&<Notice error={status.includes("failed")}>{status}</Notice>}
      <div className="vault-grid">
        <Button variant="secondary" onClick={()=>studyApi.executiveReport(study.id,false).then((blob)=>downloadBlob(blob,`fedrepro-study-${study.id}-executive-report.docx`))}>Executive Report</Button>
        <Button variant="secondary" disabled={!hasDiagnosis||!latest} onClick={exportDiagnosisReport}>Diagnosis Report</Button>
        <Button variant="secondary" disabled={!hasContract} onClick={exportContract}>Diagnosis Contract JSON</Button>
        <Button variant="secondary" disabled={!latest||!hasFingerprint} onClick={exportRecreation}>Recreation Bundle</Button>
        <Button variant="secondary" disabled>Version Certificate</Button>
        <Button variant="secondary" disabled>Fingerprint Certificate</Button>
      </div>
    </Card>

    <Card className="ai-panel">
      <p className="eyebrow">AI research copilot</p><h2>Evidence-bound support</h2>
      <div className="action-stack horizontal">
        <Button variant="secondary" onClick={()=>runAi("study")}>Summarize Current Evidence</Button>
        <Button variant="secondary" disabled={!diagnosis} onClick={()=>runAi("diagnosis")}>Explain Diagnosis</Button>
        <Button variant="secondary" onClick={()=>runAi("study")}>Review Methodology</Button>
        <Button variant="secondary" onClick={()=>runAi("study")}>Suggest Next Step</Button>
        <Button variant="secondary" onClick={()=>runAi("study")}>Generate Research Abstract</Button>
        <Button variant="secondary" onClick={()=>runAi("study")}>Draft Executive Summary</Button>
      </div>
      {aiStatus&&<Notice error={!aiStatus.startsWith("Generating")}>{aiStatus}</Notice>}
      {aiResult&&<div className="pre">{aiResult.content}</div>}
    </Card>

    <Card>
      <p className="eyebrow">Research claims tracker</p><h2>Currently supported claims</h2>
      <div className="claims-grid">{overviewClaims({hasDataset,configured,hasDiagnosis,hasFingerprint,hasContract}).map((claim)=><article key={claim.title} className={claim.supported?"supported":"unsupported"}><div className="row"><strong>{claim.title}</strong><Badge tone={claim.supported?"low":"medium"}>{claim.supported?"Supported":"Unsupported"}</Badge></div><p>{claim.reason}</p></article>)}</div>
    </Card>
    </>}
  </div>;
}

function ProtocolItem({ icon: Icon, label, value }) {
  return <div className="protocol-item"><Icon size={15}/><span><strong>{label}</strong>{shown(value)}</span></div>;
}

function StudyProtocolEditForm({ form, setForm, status, onCancel, onSave }) {
  const update=(patch)=>setForm({...form,...patch});
  return <form className="protocol-form overview-edit-form" onSubmit={onSave}>
    <div className="protocol-section">
      <div className="protocol-section-title"><span>1</span><div><h3>Study identity</h3><p>Edit the protocol fields that guide later evidence and LLM context.</p></div></div>
      <div className="protocol-field-grid">
        <Field label="Study name" full><input value={form.name} onChange={(e)=>update({name:e.target.value})} required /></Field>
        <Field label="Dataset domain"><input value={form.domain} onChange={(e)=>update({domain:e.target.value})} /></Field>
        <Field label="ML task"><select value={form.ml_task} onChange={(e)=>update({ml_task:e.target.value})} required><option value="">Select task</option><option value="classification">Classification</option><option value="regression">Regression</option><option value="clustering">Clustering</option></select></Field>
      </div>
    </div>
    <div className="protocol-section">
      <div className="protocol-section-title"><span>2</span><div><h3>Research intent</h3><p>Keep these statements explicit because downstream explanations use them as context.</p></div></div>
      <div className="protocol-field-grid">
        <Field label="Data quality focus"><input value={form.focus_issue} onChange={(e)=>update({focus_issue:e.target.value})} /></Field>
        <Field label="Primary metric"><input value={form.primary_metric} onChange={(e)=>update({primary_metric:e.target.value})} /></Field>
        {form.ml_task!=="clustering"&&<Field label="Target column"><input value={form.target_column} onChange={(e)=>update({target_column:e.target.value})} /></Field>}
        <Field label={form.ml_task==="clustering"?"Grouping goal":"Feature scope"}><input value={form.feature_scope} onChange={(e)=>update({feature_scope:e.target.value})} /></Field>
        <Field label="Research objective" full><textarea value={form.objective} onChange={(e)=>update({objective:e.target.value})} /></Field>
        <Field label="Research question" full><textarea value={form.research_question} onChange={(e)=>update({research_question:e.target.value})} /></Field>
        <Field label="Hypothesis" full><textarea value={form.hypothesis} onChange={(e)=>update({hypothesis:e.target.value})} /></Field>
      </div>
    </div>
    <div className="protocol-section">
      <div className="protocol-section-title"><span>3</span><div><h3>Reproducibility controls</h3><p>Document the settings intended to remain fixed across variants.</p></div></div>
      <div className="protocol-field-grid">
        <Field label="Controlled baseline model"><input value={form.baseline_model} onChange={(e)=>update({baseline_model:e.target.value})} /></Field>
        <Field label="Validation plan"><input value={form.validation_strategy} onChange={(e)=>update({validation_strategy:e.target.value})} /></Field>
        <Field label="Random seed"><input value={form.random_seed} onChange={(e)=>update({random_seed:e.target.value})} inputMode="numeric" /></Field>
        <Field label="Intended research use"><textarea value={form.intended_use_case} onChange={(e)=>update({intended_use_case:e.target.value})} /></Field>
      </div>
    </div>
    {status&&<Notice error={status.includes("Could not")}>{status}</Notice>}
    <div className="overview-edit-actions"><Button>Save protocol</Button><Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button></div>
  </form>;
}

export function EvidencePanel({ study, datasets, refresh, onVersion }) {
  const [file,setFile]=useState(null); const [name,setName]=useState(""); const [notes,setNotes]=useState(""); const [status,setStatus]=useState(""); const [progress,setProgress]=useState(0);
  const submit=async(e)=>{e.preventDefault();setStatus("Validating and registering CSV evidence…");const data=new FormData();data.append("file",file);if(name)data.append("dataset_name",name);if(notes)data.append("version_notes",notes);try{await datasetApi.register(study.id,data,(event)=>setProgress(Math.round(event.loaded*100/(event.total||1))));setFile(null);setName("");setNotes("");setStatus("Dataset registered. Select its target and evaluation settings below.");await refresh();}catch(err){setStatus(err.response?.data?.detail||"Registration failed");}};
  return <div className="stack"><div className="grid grid-2"><Card><h2>Register dataset evidence</h2><form className="form-grid" onSubmit={submit}><Field label="CSV file" full><input type="file" accept=".csv" onChange={(e)=>setFile(e.target.files?.[0]||null)} required /></Field><Field label="Dataset name" full><input value={name} onChange={(e)=>setName(e.target.value)} placeholder="Defaults to filename" /></Field><Field label="Version notes" full><textarea value={notes} onChange={(e)=>setNotes(e.target.value)} placeholder="Document collection or preparation changes" /></Field>{progress>0&&progress<100&&<div className="field full"><progress value={progress} max="100" /></div>}{status&&<div className="field full"><Notice error={status.includes("failed")}>{status}</Notice></div>}<div className="field full"><Button disabled={!file}>Register evidence</Button></div></form></Card><Card><h2>Registered evidence</h2>{!datasets.length?<Empty>No dataset evidence registered.</Empty>:<DataTable rows={datasets} columns={[{key:"name",label:"Dataset"},{key:"registrations",label:"Registrations",render:(r)=>r.registrations.length},{key:"versions",label:"Versions",render:(r)=>r.versions.length},{key:"created_at",label:"Created",render:(r)=>new Date(r.created_at).toLocaleDateString()}]} />}</Card></div><ConfigurationPanel study={study} datasets={datasets} refresh={refresh} onVersion={onVersion} /></div>;
}

function ConfigurationPanel({ study, datasets, refresh, onVersion }) {
  const registrations=datasets.flatMap((dataset)=>dataset.registrations.filter((item)=>item.status==="registered").map((item)=>({...item,dataset_name:dataset.name})));
  const [registrationId,setRegistrationId]=useState(""); const selected=registrations.find((item)=>String(item.id)===String(registrationId)); const columns=selected?.metadata?.column_names||[];
  const [form,setForm]=useState({target_column:"",primary_metric:study.ml_task==="regression"?"rmse":"f1_weighted",validation_strategy:"holdout",feature_selection_mode:"all_numeric",selected_features:[],scaling_strategy:"standard"}); const [status,setStatus]=useState("");
  const submit=async(e)=>{e.preventDefault();setStatus("Creating immutable version and deterministic reports…");try{const result=await datasetApi.configure(registrationId,form);setStatus("Configuration complete. Version, fingerprint, profile, and diagnosis created.");await refresh();onVersion(result);}catch(err){setStatus(err.response?.data?.detail||"Configuration failed");}};
  return <Card><h2>Target and evaluation settings</h2><p className="muted">Choose these settings here after upload, once the dataset columns are known.</p>{!registrations.length?<Empty>Upload new dataset evidence above to select its target column, primary metric, and validation strategy.</Empty>:<form className="form-grid" onSubmit={submit}><Field label="Pending registration" full><select value={registrationId} onChange={(e)=>setRegistrationId(e.target.value)} required><option value="">Select registration</option>{registrations.map((r)=><option key={r.id} value={r.id}>{r.dataset_name} · {r.original_filename}</option>)}</select></Field>{study.ml_task!=="clustering"?<><Field label="Target column"><select value={form.target_column} onChange={(e)=>setForm({...form,target_column:e.target.value})} required><option value="">Select target</option>{columns.map((c)=><option key={c}>{c}</option>)}</select></Field><Field label="Primary metric"><select value={form.primary_metric} onChange={(e)=>setForm({...form,primary_metric:e.target.value})}>{(study.ml_task==="classification"?["f1_weighted","f1_macro","accuracy","precision","recall","roc_auc"]:["rmse","mae","r2","mape"]).map((x)=><option key={x}>{x}</option>)}</select></Field><Field label="Validation strategy"><select value={form.validation_strategy} onChange={(e)=>setForm({...form,validation_strategy:e.target.value})}>{["holdout","stratified_holdout","k_fold","stratified_k_fold"].map((x)=><option key={x}>{x}</option>)}</select></Field></>:<><Field label="Feature selection mode"><select value={form.feature_selection_mode} onChange={(e)=>setForm({...form,feature_selection_mode:e.target.value})}><option value="all_numeric">All numeric features</option><option value="selected">Selected features</option></select></Field><Field label="Scaling strategy"><select value={form.scaling_strategy} onChange={(e)=>setForm({...form,scaling_strategy:e.target.value})}>{["standard","robust","minmax","none"].map((x)=><option key={x}>{x}</option>)}</select></Field></>}{selected&&<div className="field full"><Notice>{selected.metadata.row_count} rows · {selected.metadata.column_count} columns · {selected.metadata.missing_total} missing cells</Notice></div>}{status&&<div className="field full"><Notice error={status.includes("failed")}>{status}</Notice></div>}<div className="field full"><Button disabled={!registrationId}>Save settings and analyze</Button></div></form>}</Card>;
}

export function EnhancedEvidencePanel({ study, datasets, refresh, onVersion }) {
  const registrations=datasets.flatMap((dataset)=>dataset.registrations.map((registration)=>({...registration,dataset_name:dataset.name,dataset_versions:dataset.versions})));
  const latestVersion=datasets.flatMap((dataset)=>dataset.versions.map((version)=>({...version,dataset_name:dataset.name}))).sort((a,b)=>new Date(a.created_at)-new Date(b.created_at)).at(-1);
  const configurableRegistrations=registrations.filter((registration)=>!registration.dataset_versions?.some((version)=>version.registration_id===registration.id));
  const [selectedId,setSelectedId]=useState(configurableRegistrations[0]?.id ? String(configurableRegistrations[0].id) : registrations[0]?.id ? String(registrations[0].id) : "");
  const selected=registrations.find((item)=>String(item.id)===String(selectedId))||registrations[0];
  const [file,setFile]=useState(null);
  const [name,setName]=useState("");
  const [role,setRole]=useState("");
  const [source,setSource]=useState("");
  const [collection,setCollection]=useState("");
  const [limitations,setLimitations]=useState("");
  const [notes,setNotes]=useState("");
  const [status,setStatus]=useState("");
  const [progress,setProgress]=useState(0);
  const [report,setReport]=useState(null);
  const [reportStatus,setReportStatus]=useState("");
  const configureRegistration=(row)=>{
    setSelectedId(String(row.id));
    window.setTimeout(()=>document.getElementById("dataset-evidence-configuration")?.scrollIntoView({behavior:"smooth",block:"start"}),0);
  };
  const loadRegistrationReport=async(row)=>{
    setSelectedId(String(row.id));
    setReportStatus("Loading saved dataset explanation report...");
    setReport(null);
    try{
      setReport(await datasetApi.registrationReport(row.id));
      setReportStatus("");
      window.setTimeout(()=>document.getElementById("dataset-explanation-report")?.scrollIntoView({behavior:"smooth",block:"start"}),0);
    }catch(err){
      setReportStatus(err.response?.data?.detail||"Could not load dataset explanation report.");
    }
  };
  const submit=async(event)=>{
    event.preventDefault();
    setStatus("Registering dataset evidence...");
    const data=new FormData();
    data.append("file",file);
    if(name)data.append("dataset_name",name);
    const evidenceNotes=[
      role&&`Evidence role: ${role}`,
      source&&`Source description: ${source}`,
      collection&&`Collection period: ${collection}`,
      limitations&&`Known limitations: ${limitations}`,
      notes&&`Version notes: ${notes}`
    ].filter(Boolean).join("\n");
    if(evidenceNotes)data.append("version_notes",evidenceNotes);
    try{
      await datasetApi.register(study.id,data,(event)=>setProgress(Math.round(event.loaded*100/(event.total||1))));
      setFile(null);setName("");setRole("");setSource("");setCollection("");setLimitations("");setNotes("");setStatus("Dataset evidence registered.");
      await refresh();
    }catch(err){
      setStatus(err.response?.data?.detail||"Registration failed");
    }
  };
  return <div className="stack">
    <details className="collapsible-card" open>
      <summary><div><p className="eyebrow">Dataset evidence</p><h2>Register evidence artifact</h2></div><span className="metric-icon"><UploadCloud size={17}/></span></summary>
      <div className="collapsible-body">
    <div className="evidence-hero-grid">
      <Card className="evidence-upload-card">
        <form className="form-grid" onSubmit={submit}>
          <Field label="CSV file" full><input type="file" accept=".csv" onChange={(event)=>setFile(event.target.files?.[0]||null)} required /></Field>
          <Field label="Dataset name"><input value={name} onChange={(event)=>setName(event.target.value)} placeholder="Defaults to filename" /></Field>
          <Field label="Evidence role"><input value={role} onChange={(event)=>setRole(event.target.value)} placeholder="Describe this dataset role" /></Field>
          <Field label="Source description" full><textarea value={source} onChange={(event)=>setSource(event.target.value)} placeholder="Document where this evidence came from" /></Field>
          <Field label="Collection period"><input value={collection} onChange={(event)=>setCollection(event.target.value)} placeholder="Document the source period if known" /></Field>
          <Field label="Known limitations"><input value={limitations} onChange={(event)=>setLimitations(event.target.value)} placeholder="Document known caveats" /></Field>
          <Field label="Version notes" full><textarea value={notes} onChange={(event)=>setNotes(event.target.value)} placeholder="Document collection, preparation, or upload context" /></Field>
          {progress>0&&progress<100&&<div className="field full"><progress value={progress} max="100" /></div>}
          {status&&<div className="field full"><Notice error={status.includes("failed")}>{status}</Notice></div>}
          <div className="field full"><Button disabled={!file}><UploadCloud size={15}/>Register evidence</Button></div>
        </form>
      </Card>
      <Card className="evidence-status-card">
        <p className="eyebrow">Evidence state</p><h2>Current registry</h2>
        <div className="evidence-stat-list">
          <EvidenceStat icon={Database} label="Datasets" value={datasets.length} />
          <EvidenceStat icon={FileStack} label="Registrations" value={registrations.length} />
          <EvidenceStat icon={FileCheck2} label="Versions" value={datasets.reduce((total,dataset)=>total+dataset.versions.length,0)} />
          <EvidenceStat icon={TableProperties} label="Latest shape" value={latestVersion?`${latestVersion.row_count} rows, ${latestVersion.column_count} columns`:"Not available"} />
        </div>
      </Card>
    </div>
      </div>
    </details>

    <details className="collapsible-card" open>
      <summary><div><p className="eyebrow">Evidence registry</p><h2>Registered dataset evidence</h2></div>{registrations.length>0&&<Badge tone="low">{registrations.length} registration{registrations.length===1?"":"s"}</Badge>}</summary>
      <div className="collapsible-body">
      {!registrations.length?<Empty>No dataset evidence registered.</Empty>:<div className="evidence-registry-table"><DataTable rows={registrations} columns={[
        {key:"dataset_name",label:"Dataset"},
        {key:"original_filename",label:"File"},
        {key:"status",label:"Status",render:(row)=><Badge tone="low">{row.status}</Badge>},
        {key:"shape",label:"Shape",render:(row)=>`${row.metadata?.row_count??"?"} x ${row.metadata?.column_count??"?"}`},
        {key:"missing",label:"Missing",render:(row)=>row.metadata?.missing_total??"Not available"},
        {key:"created_at",label:"Registered",render:(row)=>new Date(row.created_at).toLocaleDateString()},
        {key:"actions",label:"Actions",render:(row)=>{
          const alreadyConfigured=row.dataset_versions?.some((version)=>version.registration_id===row.id);
          return <div className="evidence-row-actions">
            <Button variant="secondary compact" disabled={alreadyConfigured} onClick={()=>configureRegistration(row)}>{alreadyConfigured?<><CheckCircle2 size={13}/>Configured</>:<><ClipboardCheck size={13}/>Configure</>}</Button>
            <Button variant="secondary compact" onClick={()=>loadRegistrationReport(row)}><Eye size={13}/>View report</Button>
          </div>;
        }}
      ]} /></div>}
      </div>
    </details>

    <details className="collapsible-card" open>
      <summary><div><p className="eyebrow">Selected registration</p><h2>Evidence certificate</h2></div>{selected&&<Badge>{selected.dataset_name}</Badge>}</summary>
      <div className="collapsible-body">
        <div className="evidence-detail-grid">
          <RegistrationDetail selected={selected} study={study} />
          <EvidenceChecklist selected={selected} />
        </div>
        {selected&&<EvidenceQualitySummary selected={selected} />}
        {selected&&<SchemaEvidenceTable selected={selected} configuredVersion={selected.dataset_versions?.find((version)=>version.registration_id===selected.id)} />}
        {reportStatus&&<Notice error={reportStatus.includes("Could not")}>{reportStatus}</Notice>}
        {report&&<EvidenceExplanationReport report={report} />}
      </div>
    </details>

    {!!configurableRegistrations.length&&<EnhancedConfigurationPanel study={study} registrations={configurableRegistrations} selected={configurableRegistrations.find((item)=>String(item.id)===String(selectedId))||configurableRegistrations[0]} selectedId={configurableRegistrations.some((item)=>String(item.id)===String(selectedId))?selectedId:String(configurableRegistrations[0].id)} setSelectedId={setSelectedId} refresh={refresh} onVersion={onVersion} />}
  </div>;
}

function EvidenceStat({ icon: Icon, label, value }) {
  return <div className="evidence-stat"><Icon size={15}/><span><strong>{label}</strong>{value}</span></div>;
}

function RegistrationDetail({ selected, study }) {
  if(!selected)return <Card><Empty>Select a registered dataset to inspect metadata and schema.</Empty></Card>;
  const metadata=selected.metadata||{};
  const validation=selected.validation||{};
  const configuredVersion=selected.dataset_versions?.find((version)=>version.registration_id===selected.id);
  return <Card className="registration-detail-card">
    <p className="eyebrow">Selected registration</p><h2>{selected.dataset_name}</h2>
    <div className="context-list">
      <div className="context-row"><strong>Registration ID</strong><span>{selected.id}</span></div>
      <div className="context-row"><strong>Version association</strong><span>{configuredVersion?`V${configuredVersion.version_number}`:"Not configured"}</span></div>
      <div className="context-row"><strong>ML task</strong><span>{study?.ml_task||"Not available"}</span></div>
      <div className="context-row"><strong>Target column</strong><span>{configuredVersion?.configuration?.target_column||"Not configured"}</span></div>
      <div className="context-row"><strong>Original file</strong><span>{selected.original_filename}</span></div>
      <div className="context-row"><strong>File type</strong><span>CSV</span></div>
      <div className="context-row"><strong>File size</strong><span>{formatBytes(selected.file_size)}</span></div>
      <div className="context-row"><strong>Rows</strong><span>{metadata.row_count??"Not available"}</span></div>
      <div className="context-row"><strong>Columns</strong><span>{metadata.column_count??"Not available"}</span></div>
      <div className="context-row"><strong>Missing cells</strong><span>{metadata.missing_total??"Not available"}</span></div>
      <div className="context-row"><strong>Duplicate rows</strong><span>{metadata.duplicate_count??"Not available"}</span></div>
      <div className="context-row"><strong>Registered</strong><span>{formatDate(selected.created_at)||"Not available"}</span></div>
      <div className="context-row"><strong>Validation</strong><span>{validation.valid_csv&&validation.schema_valid?"valid":selected.status}</span></div>
    </div>
  </Card>;
}

function EvidenceChecklist({ selected }) {
  const selectedVersions=selected?.dataset_versions?.filter((version)=>version.registration_id===selected.id)||[];
  const hasVersion=Boolean(selectedVersions.length);
  const items=[
    ["File uploaded", Boolean(selected)],
    ["Metadata extracted", Boolean(selected?.metadata)],
    ["Validation recorded", Boolean(selected?.validation)],
    ["Immutable version created", hasVersion],
    ["Fingerprint available", Boolean(selectedVersions.some((version)=>version.fingerprint))]
  ];
  return <Card className="evidence-checklist-card">
    <p className="eyebrow">Evidence completeness</p><h2>Artifact status</h2>
    <div className="readiness-list">{items.map(([label,done])=><div key={label} className={done?"complete":""}><CheckCircle2 size={15}/><span>{label}</span></div>)}</div>
    {selected?.version_notes&&<div className="evidence-notes"><strong>Research notes</strong><pre className="pre">{selected.version_notes}</pre></div>}
  </Card>;
}

function EvidenceQualitySummary({ selected }) {
  const quality=evidenceQuality(selected.metadata||{});
  return <Card className="evidence-quality-card">
    <p className="eyebrow">Evidence quality summary</p><h2>Computed from registration metadata</h2>
    <div className="grid grid-4">
      <MetricCard label="Missing cells" value={quality.missingCells} icon={Gauge} />
      <MetricCard label="Duplicate rows" value={quality.duplicateRows} icon={Copy} />
      <MetricCard label="Numeric columns" value={quality.numericCount} icon={TableProperties} />
      <MetricCard label="Categorical columns" value={quality.categoricalCount} icon={Database} />
    </div>
    <div className="context-list compact">
      <div className="context-row"><strong>Suspicious identifiers</strong><span>{quality.suspiciousIdentifierColumns.join(", ")||"None detected"}</span></div>
      <div className="context-row"><strong>Columns needing inspection</strong><span>{quality.issueColumns.length}</span></div>
    </div>
  </Card>;
}

function SchemaEvidenceTable({ selected, configuredVersion }) {
  const metadata=selected.metadata||{};
  const columns=metadata.column_names||[];
  const dataTypes=metadata.data_types||{};
  const missingValues=metadata.missing_values||{};
  const target=configuredVersion?.configuration?.target_column;
  const [search,setSearch]=useState("");
  const [typeFilter,setTypeFilter]=useState("all");
  const [issueOnly,setIssueOnly]=useState(false);
  const [page,setPage]=useState(0);
  const pageSize=12;
  const rows=columns.map((name,index)=>{
    const dtype=dataTypes[name]||"Not available";
    const missing=missingValues[name]||0;
    const missingRatio=metadata.row_count?missing/metadata.row_count:0;
    const numeric=/int|float|double|decimal|number/i.test(String(dtype));
    const suspicious=/(^id$|_id$|uuid|identifier|email|phone)/i.test(name);
    return {position:index+1,name,data_type:dtype,kind:numeric?"numeric":"categorical",role:name===target?"target":"feature",missing_count:missing,missing_ratio:missingRatio,unique_count:metadata.unique_values?.[name],issue:missing>0||suspicious};
  });
  const filtered=rows.filter((row)=>{
    const matchesSearch=!search||row.name.toLowerCase().includes(search.toLowerCase());
    const matchesType=typeFilter==="all"||row.kind===typeFilter;
    const matchesIssue=!issueOnly||row.issue;
    return matchesSearch&&matchesType&&matchesIssue;
  });
  const maxPage=Math.max(0,Math.ceil(filtered.length/pageSize)-1);
  const safePage=Math.min(page,maxPage);
  const visible=filtered.slice(safePage*pageSize,safePage*pageSize+pageSize);
  return <Card className="schema-evidence-card">
    <div className="row">
      <div><p className="eyebrow">Schema intelligence</p><h2>{columns.length} captured columns</h2></div>
      <Badge tone="low">{filtered.length} shown</Badge>
    </div>
    <div className="filter-row">
      <Field label="Search"><input value={search} onChange={(event)=>{setSearch(event.target.value);setPage(0);}} placeholder="Column name" /></Field>
      <Field label="Datatype"><select value={typeFilter} onChange={(event)=>{setTypeFilter(event.target.value);setPage(0);}}><option value="all">All</option><option value="numeric">Numeric</option><option value="categorical">Categorical</option></select></Field>
      <label className="checkbox-field"><input type="checkbox" checked={issueOnly} onChange={(event)=>{setIssueOnly(event.target.checked);setPage(0);}} /> Issue-only</label>
    </div>
    {!visible.length?<Empty>No columns match the current filters.</Empty>:<DataTable rows={visible} columns={[
      {key:"position",label:"#"},
      {key:"name",label:"Column"},
      {key:"data_type",label:"Datatype"},
      {key:"role",label:"Role",render:(row)=><Badge tone={row.role==="target"?"medium":"default"}>{row.role}</Badge>},
      {key:"missing_count",label:"Missing"},
      {key:"missing_ratio",label:"Missing %",render:(row)=>pct(row.missing_ratio)},
      {key:"unique_count",label:"Unique",render:(row)=>row.unique_count??"Not captured"},
      {key:"issue",label:"State",render:(row)=><Badge tone={row.issue?"medium":"low"}>{row.issue?"Inspect":"Clear"}</Badge>},
    ]} />}
    <div className="pagination-row">
      <Button variant="secondary compact" disabled={safePage===0} onClick={()=>setPage(safePage-1)}>Previous</Button>
      <span>Page {safePage+1} of {maxPage+1}</span>
      <Button variant="secondary compact" disabled={safePage>=maxPage} onClick={()=>setPage(safePage+1)}>Next</Button>
    </div>
  </Card>;
}

function EvidenceExplanationReport({ report }) {
  const reportColumns=Array.isArray(report.columns)?report.columns:[];
  return <Card id="dataset-explanation-report" className="evidence-report-card">
    <div className="row">
      <div><p className="eyebrow">Saved explanation report</p><h2>{report.title||"Dataset explanation report"}</h2></div>
      <Badge>{report.report_version||"Report"}</Badge>
    </div>
    {report.summary&&<LLMFormattedContent content={report.summary} />}
    {report.metrics&&<div className="version-summary-grid evidence-report-metrics">
      {Object.entries(report.metrics).filter(([,value])=>value!==null&&value!==undefined&&value!=="").map(([key,value])=><CertificateSummaryCard key={key} label={key.replaceAll("_"," ")} value={value} detail="Persisted evidence" />)}
    </div>}
    {!!reportColumns.length&&<div className="evidence-report-column-table">
      <div className="row">
        <div><p className="eyebrow">Column inventory</p><h3>Observed columns from registration metadata</h3></div>
        <Badge tone="low">{reportColumns.length} captured</Badge>
      </div>
      <DataTable rows={reportColumns} columns={[
        {key:"position",label:"#"},
        {key:"name",label:"Column"},
        {key:"data_type",label:"Data type",render:(row)=>row.data_type||"Not Available"},
        {key:"missing_count",label:"Missing cells",render:(row)=>row.missing_count??"Not Available"},
        {key:"missing_ratio",label:"Missing %",render:(row)=>row.missing_ratio==null?"Not Available":pct(row.missing_ratio)},
        {key:"evidence_source",label:"Evidence source",render:(row)=>(row.evidence_source||"Persisted metadata").replaceAll("_"," ")}
      ]} />
    </div>}
    <div className="evidence-report-sections">
      {(report.sections||[]).map((section)=><article key={section.title} className="mini-evidence-list">
        <h3>{section.title}</h3>
        {(section.items||[]).map((item)=><div key={`${section.title}-${item.label}`}><strong>{item.label}</strong><span>{item.value??"Not Available"}</span></div>)}
      </article>)}
    </div>
  </Card>;
}

function LLMFormattedContent({ content, compact = false }) {
  const text=String(content||"").trim();
  if(!text)return null;
  const sections=[];
  let current={title:"Summary",body:[]};
  text.split(/\r?\n/).forEach((line)=>{
    const clean=line.trim();
    if(!clean)return;
    if(isLlmBoilerplate(clean))return;
    if(/^={3,}$/.test(clean)||/^-{3,}$/.test(clean))return;
    const normalized=clean.replace(/^#{1,4}\s*/,"").replace(/\*\*/g,"").trim();
    const heading=normalized.match(/^([A-Za-z][A-Za-z\s/&-]{2,48}):?$/);
    if(heading&&normalized.length<56){
      if(current.body.length)sections.push(current);
      current={title:heading[1].trim(),body:[]};
    }else{
      current.body.push(clean.replace(/\*\*/g,""));
    }
  });
  if(current.body.length)sections.push(current);
  const rendered=sections.length?sections:[{title:"Summary",body:[text]}];
  return <div className={compact?"llm-formatted compact":"llm-formatted"}>
    {rendered.map((section,index)=><section key={`${section.title}-${index}`}><h3>{section.title}</h3><LLMSectionBody lines={section.body} /></section>)}
  </div>;
}

function LLMSectionBody({ lines }) {
  const blocks=[];
  for(let index=0;index<lines.length;){
    const line=lines[index];
    if(isMarkdownTableStart(lines,index)){
      const table=[];
      table.push(splitMarkdownTable(lines[index]));
      index+=2;
      while(index<lines.length&&isMarkdownTableRow(lines[index])){
        table.push(splitMarkdownTable(lines[index]));
        index+=1;
      }
      blocks.push({type:"table",rows:table});
      continue;
    }
    if(/^[+-]\s+/.test(line)||/^[-*]\s+/.test(line)){
      const items=[];
      while(index<lines.length&&(/^[+-]\s+/.test(lines[index])||/^[-*]\s+/.test(lines[index]))){
        items.push(cleanInline(lines[index].replace(/^[+\-*]\s+/,"")));
        index+=1;
      }
      blocks.push({type:"list",items});
      continue;
    }
    const keyValue=line.match(/^([^:]{2,48}):\s*(.+)$/);
    if(keyValue){
      blocks.push({type:"kv",label:cleanInline(keyValue[1]),value:cleanInline(keyValue[2])});
    }else{
      blocks.push({type:"p",text:cleanInline(line)});
    }
    index+=1;
  }
  return <>{blocks.map((block,index)=>{
    if(block.type==="table")return <div className="llm-table-wrap" key={index}><table className="llm-table"><thead><tr>{block.rows[0].map((cell)=><th key={cell}>{cleanInline(cell)}</th>)}</tr></thead><tbody>{block.rows.slice(1).map((row,rowIndex)=><tr key={rowIndex}>{row.map((cell,cellIndex)=><td key={`${rowIndex}-${cellIndex}`}>{cleanInline(cell)}</td>)}</tr>)}</tbody></table></div>;
    if(block.type==="list")return <ul className="llm-list" key={index}>{block.items.map((item,itemIndex)=><li key={itemIndex}>{item}</li>)}</ul>;
    if(block.type==="kv")return <div className="llm-key-value" key={index}><strong>{block.label}</strong><span>{block.value}</span></div>;
    return <p key={index}>{block.text}</p>;
  })}</>;
}

function isMarkdownTableRow(line) {
  return /^\|.*\|$/.test(String(line||"").trim());
}

function isMarkdownTableStart(lines,index) {
  return isMarkdownTableRow(lines[index])&&isMarkdownTableRow(lines[index+1])&&/^\|\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$/.test(lines[index+1].trim());
}

function splitMarkdownTable(line) {
  return line.trim().replace(/^\|/,"").replace(/\|$/,"").split("|").map((cell)=>cell.trim());
}

function cleanInline(value) {
  return String(value||"").replace(/`([^`]+)`/g,"$1").trim();
}

function isLlmBoilerplate(line) {
  const normalized=line.replace(/\*\*/g,"").replace(/^[-*]\s+/,"").trim().toLowerCase();
  return [
    "here is the interpretation of the dataset-version transition:",
    "here are the interpretations of scm and dsi for a research user:",
    "here is the interpretation:",
    "here is a concise interpretation:",
    "summary",
  ].includes(normalized);
}

function formatExplanationReportDownload(report, study, version, datasetName) {
  const lines=[
    `# ${report.title||`Dataset Explanation Report - V${version.version_number}`}`,
    "",
    `Generated: ${formatDate(report.generated_at)||new Date().toLocaleString()}`,
    `Study: ${study.name}`,
    `Dataset: ${datasetName||report.version?.dataset_name||"Not Available"}`,
    `Version: V${version.version_number}`,
    `ML task: ${study.ml_task||"Not Available"}`,
    "",
    "## Study Context",
    study.problem_objective||"Not Available",
    "",
    "## Version Evidence",
    `Rows: ${version.row_count}`,
    `Columns: ${version.column_count}`,
    `Target column: ${version.configuration?.target_column||"Not Available"}`,
    `Primary metric: ${version.configuration?.primary_metric||"Not Available"}`,
    `Validation strategy: ${version.configuration?.validation_strategy||"Not Available"}`,
    `Version notes: ${version.version_notes||"Not Available"}`,
    "",
    "## Detailed Explanation",
    report.summary||"Not Available",
  ];
  if(report.ai){
    lines.push("", "## AI Evidence Binding", `Model: ${report.ai.model||"Not Available"}`, `Prompt version: ${report.ai.prompt_version||"Not Available"}`, `Source evidence hash: ${report.ai.source_evidence_hash||"Not Available"}`);
  }
  return lines.join("\n");
}

function EnhancedConfigurationPanel({ study, registrations, selected, selectedId, setSelectedId, refresh, onVersion }) {
  const columns=selected?.metadata?.column_names||[];
  const activeRegistrationId=selectedId||String(selected?.id||"");
  const [form,setForm]=useState({target_column:"",primary_metric:"",validation_strategy:"",feature_selection_mode:"",selected_features:[],scaling_strategy:""});
  const [status,setStatus]=useState("");
  const submit=async(event)=>{
    event.preventDefault();
    setStatus("Creating immutable version and deterministic reports...");
    try{
      const result=await datasetApi.configure(activeRegistrationId,form);
      setStatus("Configuration complete. Version, fingerprint, profile, and diagnosis created.");
      await refresh();
      onVersion(result);
    }catch(err){
      setStatus(err.response?.data?.detail||"Configuration failed");
    }
  };
  return <details id="dataset-evidence-configuration" className="collapsible-card" open>
    <summary><div><p className="eyebrow">Target and evaluation</p><h2>{selected?`Configure ${selected.dataset_name}`:"Configure evidence"}</h2></div>{selected&&<Badge>{selected.original_filename}</Badge>}</summary>
    <div className="collapsible-body">
    {!registrations.length?<Empty>Register dataset evidence before configuring target and evaluation settings.</Empty>:<form className="form-grid" onSubmit={submit}>
      {!selected&&<Field label="Registration" full><select value={selectedId} onChange={(event)=>setSelectedId(event.target.value)} required><option value="">Select registration</option>{registrations.map((registration)=><option key={registration.id} value={registration.id}>{registration.dataset_name} - {registration.original_filename}</option>)}</select></Field>}
      {study.ml_task!=="clustering"?<>
        <Field label="Target column"><select value={form.target_column} onChange={(event)=>setForm({...form,target_column:event.target.value})} required><option value="">Select target</option>{columns.map((column)=><option key={column}>{column}</option>)}</select></Field>
        <Field label="Primary metric"><select value={form.primary_metric} onChange={(event)=>setForm({...form,primary_metric:event.target.value})} required><option value="">Select metric</option>{(study.ml_task==="classification"?["f1_weighted","f1_macro","accuracy","precision","recall","roc_auc"]:["rmse","mae","r2","mape"]).map((metric)=><option key={metric}>{metric}</option>)}</select></Field>
        <Field label="Validation strategy"><select value={form.validation_strategy} onChange={(event)=>setForm({...form,validation_strategy:event.target.value})} required><option value="">Select validation strategy</option>{["holdout","stratified_holdout","k_fold","stratified_k_fold"].map((strategy)=><option key={strategy}>{strategy}</option>)}</select></Field>
      </>:<>
        <Field label="Feature selection mode"><select value={form.feature_selection_mode} onChange={(event)=>setForm({...form,feature_selection_mode:event.target.value})}><option value="">Select feature mode</option><option value="all_numeric">All numeric features</option><option value="selected">Selected features</option></select></Field>
        <Field label="Scaling strategy"><select value={form.scaling_strategy} onChange={(event)=>setForm({...form,scaling_strategy:event.target.value})} required><option value="">Select scaling strategy</option>{["standard","robust","minmax","none"].map((strategy)=><option key={strategy}>{strategy}</option>)}</select></Field>
      </>}
      {selected&&<div className="field full"><Notice>{selected.metadata?.row_count??"Unknown"} rows, {selected.metadata?.column_count??"unknown"} columns, {selected.metadata?.missing_total??"unknown"} missing cells</Notice></div>}
      {status&&<div className="field full"><Notice error={status.includes("failed")}>{status}</Notice></div>}
      <div className="configuration-summary field full">
        <strong>Configuration summary</strong>
        <span>Target: {form.target_column||"Not selected"} | Metric: {form.primary_metric||"Not selected"} | Validation: {form.validation_strategy||"Not selected"}</span>
      </div>
      <div className="field full"><Button disabled={!activeRegistrationId}>Save settings and analyze</Button></div>
    </form>}
    </div>
  </details>;
}

function formatBytes(bytes) {
  if(bytes==null)return "Not available";
  if(bytes<1024)return `${bytes} B`;
  if(bytes<1024*1024)return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/(1024*1024)).toFixed(1)} MB`;
}

export function VersionPanel({ study, datasets, selectedVersion, profile, semanticHistory, onVersion, onDelete, onOpenDiagnosis, status }) {
  const [detailTab,setDetailTab]=useState("fingerprint");
  const [compareId,setCompareId]=useState("");
  const [metricAiResult,setMetricAiResult]=useState(null);
  const [metricAiStatus,setMetricAiStatus]=useState("");
  const [executiveResult,setExecutiveResult]=useState(null);
  const [executiveStatus,setExecutiveStatus]=useState("");
  const [evidenceReport,setEvidenceReport]=useState(null);
  const [reportStatus,setReportStatus]=useState("");
  const semanticByVersionId=new Map((semanticHistory||[]).map((item)=>[item.id,item.semantic_diff]));
  const versions=datasets.flatMap((dataset)=>dataset.versions.map((version)=>({
    ...version,
    dataset_name:dataset.name,
    semantic_diff:version.semantic_diff||semanticByVersionId.get(version.id)
  }))).sort((a,b)=>a.version_number-b.version_number);
  const versionNumberById=new Map(versions.map((version)=>[version.id,version.version_number]));
  const parentVersionLabel=(row)=>row?.parent_version_id?`V${versionNumberById.get(row.parent_version_id)||row.parent_version_id}`:"Baseline";
  const selectedRow=selectedVersion?versions.find((version)=>version.id===selectedVersion.id):null;
  const selectedWithEvidence=selectedVersion&&selectedRow?{...selectedVersion,semantic_diff:selectedVersion.semantic_diff||selectedRow.semantic_diff,dataset_name:selectedRow.dataset_name}:selectedVersion;
  const selectedDatasetName=selectedRow?.dataset_name||datasets.find((dataset)=>dataset.id===selectedVersion?.dataset_id)?.name||study.name;
  const latest=versions.at(-1);
  const semantic=selectedWithEvidence?.semantic_diff;
  const compareOptions=selectedWithEvidence?versions.filter((version)=>version.id!==selectedWithEvidence.id&&version.version_number<selectedWithEvidence.version_number&&(!selectedWithEvidence.dataset_id||!version.dataset_id||version.dataset_id===selectedWithEvidence.dataset_id)):[];
  const compareBase=compareOptions.find((version)=>String(version.id)===String(compareId))||versions.find((version)=>version.id===selectedWithEvidence?.parent_version_id)||compareOptions.at(-1);
  const warnings=integrityWarnings(selectedWithEvidence, profile);
  const executiveStreaming=executiveStatus.startsWith("Streaming");
  useEffect(()=>{
    setMetricAiResult(null);
    setMetricAiStatus("");
    setExecutiveResult(null);
    setExecutiveStatus("");
    setEvidenceReport(null);
    setReportStatus("");
    setCompareId("");
  },[selectedWithEvidence?.id]);
  const remove=(row)=>{if(window.confirm(`Delete ${row.dataset_name} V${row.version_number}? This permanently removes its file, profile, diagnosis, and dependent semantic comparisons.`))onDelete(row.id);};
  const scrollToEvidenceSection=(nextTab="fingerprint")=>{
    const targets={fingerprint:"version-fingerprint-section",lineage:"version-lineage-section",semantic:"version-comparison-section"};
    setDetailTab(nextTab);
    window.setTimeout(()=>document.getElementById(targets[nextTab])?.scrollIntoView({behavior:"smooth",block:"start"}),80);
  };
  const loadVersion=async(row,nextTab="fingerprint")=>{
    setDetailTab(nextTab);
    await onVersion(row.id);
    scrollToEvidenceSection(nextTab);
  };
  const exportBundle=async()=>{
    if(!selectedWithEvidence)return;
    setReportStatus("Preparing recreation bundle...");
    try{
      const bundle=await datasetApi.recreationBundle(selectedWithEvidence.id);
      downloadBlob(new Blob([JSON.stringify(bundle,null,2)],{type:"application/json"}),`fedrepro-v${selectedWithEvidence.version_number}-recreation-bundle.json`);
      setReportStatus("Recreation bundle exported.");
    }catch(err){
      setReportStatus(err.response?.data?.detail||"Could not export recreation bundle.");
    }
  };
  const generateMetricAi=async()=>{
    if(!semantic?.id||executiveStreaming)return;
    setMetricAiStatus("Generating SCM and DSI interpretation...");
    setMetricAiResult(null);
    try{
      setMetricAiResult(await aiApi.semanticMetrics(study.id,semantic.id));
      setMetricAiStatus("");
    }catch(err){
      setMetricAiStatus(aiFallbackMessage());
    }
  };
  const generateExecutiveSummary=async()=>{
    if(!selectedWithEvidence)return;
    const versionId=selectedWithEvidence.id;
    setExecutiveStatus("Streaming dataset executive summary...");
    setExecutiveResult({version_id:versionId,content:""});
    try{
      const content=await aiApi.versionExecutiveSummaryStream(study.id,versionId,(chunk)=>{
        setExecutiveResult((current)=>({
          ...(current||{}),
          version_id:versionId,
          content:`${current?.content||""}${chunk}`
        }));
      });
      setExecutiveResult((current)=>({...current,version_id:versionId,content}));
      setExecutiveStatus("Executive summary generated.");
    }catch(err){
      setExecutiveStatus(aiFallbackMessage());
    }
  };
  const loadEvidenceReport=async()=>{
    if(!selectedWithEvidence)return;
    setReportStatus("Generating, saving, and downloading detailed explanation report...");
    setEvidenceReport(null);
    try{
      const report=await datasetApi.generateVersionEvidenceReport(selectedWithEvidence.id);
      const text=formatExplanationReportDownload(report,study,selectedWithEvidence,selectedDatasetName);
      downloadBlob(new Blob([text],{type:"text/markdown;charset=utf-8"}),`fedrepro-v${selectedWithEvidence.version_number}-dataset-explanation-report.md`);
      setReportStatus("Detailed explanation report downloaded.");
    }catch(err){
      setReportStatus(aiFallbackMessage());
    }
  };
  return <div className="stack">
    <Card className="version-dashboard-header">
      <div className="version-page-head">
        <div><p className="eyebrow">Versions & Fingerprints</p><h1>Dataset Evidence Certificate Dashboard</h1>{selectedWithEvidence&&<p className="version-story-line">V{selectedWithEvidence.version_number} - {selectedDatasetName} | {selectedWithEvidence.parent_version_id?`Revision of ${parentVersionLabel(selectedWithEvidence)}`:"Baseline version"} | {formatDate(selectedWithEvidence.created_at)||"Not Available"} | {selectedWithEvidence.row_count} rows | {selectedWithEvidence.column_count} columns</p>}</div>
        <div className="summary-actions">
          <Button variant="secondary compact" disabled={!selectedWithEvidence} onClick={exportBundle}><FileCheck2 size={14}/>Export Recreation Bundle</Button>
          <Button variant="secondary compact" disabled={!selectedWithEvidence} onClick={()=>document.getElementById("version-reproducibility-section")?.scrollIntoView({behavior:"smooth",block:"start"})}><ShieldCheck size={14}/>Verify Candidate Dataset</Button>
          <Button variant="secondary compact" disabled={!selectedWithEvidence?.parent_version_id} onClick={()=>document.getElementById("version-comparison-section")?.scrollIntoView({behavior:"smooth",block:"start"})}><GitCompare size={14}/>Compare Versions</Button>
          <Button variant="secondary compact" disabled={!selectedWithEvidence} onClick={loadEvidenceReport}><Eye size={14}/>Download Explanation Report</Button>
        </div>
      </div>
      {status&&<Notice error={status.includes("Could not")}>{status}</Notice>}
      {reportStatus&&<Notice error={reportStatus.includes("Could not")}>{reportStatus}</Notice>}
    </Card>

    <Card className="version-ledger-panel">
        <div className="version-page-head">
          <div><p className="eyebrow">Version ledger</p><h2>{study.name}</h2></div>
          <div className="summary-actions"><Badge>{versions.length} version{versions.length===1?"":"s"}</Badge><ReportActions study={study} compact /></div>
        </div>
        {!versions.length?<Empty>No configured versions.</Empty>:<DataTable rows={versions} columns={[
          {key:"version_number",label:"Version",render:(row)=><button className={selectedVersion?.id===row.id?"ledger-link active":"ledger-link"} onClick={()=>loadVersion(row)}>{`V${row.version_number}`}</button>},
          {key:"dataset_name",label:"Dataset"},
          {key:"parent_version_id",label:"Parent",render:(row)=>row.parent_version_id?parentVersionLabel(row):<Badge>Baseline</Badge>},
          {key:"shape",label:"Shape",render:(row)=>`${row.row_count} x ${row.column_count}`},
          {key:"fingerprint",label:"Fingerprint",render:(row)=><HashChip value={fingerprintValue(row.fingerprint)} />},
          {key:"status",label:"Evidence",render:(row)=><EvidenceStatus row={row} />},
          {key:"action",label:"Actions",render:(row)=><div className="ledger-icon-actions">
            <Button variant="secondary compact" title="Inspect fingerprint" aria-label={`Inspect V${row.version_number} fingerprint`} onClick={()=>loadVersion(row,"fingerprint")}><Copy size={13}/></Button>
            <Button variant="secondary compact" title="View lineage" aria-label={`View V${row.version_number} lineage`} onClick={()=>loadVersion(row,"lineage")}><Network size={13}/></Button>
            <Button variant="secondary compact" title="Compare semantic change" aria-label={`Compare V${row.version_number}`} onClick={()=>loadVersion(row,"semantic")} disabled={!row.parent_version_id}><GitCompare size={13}/></Button>
            <Button variant="danger compact" title="Delete version" aria-label={`Delete ${row.dataset_name} version ${row.version_number}`} onClick={()=>remove(row)}><Trash2 size={14}/></Button>
          </div>}
        ]} />}
    </Card>

    {evidenceReport&&<EvidenceExplanationReport report={evidenceReport} />}

    {!selectedWithEvidence?<Empty>No version selected.</Empty>:<>
      <VersionIdentityCard version={selectedWithEvidence} datasetName={selectedDatasetName} warnings={warnings} parentLabel={parentVersionLabel(selectedWithEvidence)} />
      <VersionResearchContext version={selectedWithEvidence} />
      <div id="version-comparison-section" className="version-tab-grid"><SemanticChangeSummary semantic={semantic} selectedVersion={selectedWithEvidence} parentLabel={parentVersionLabel(selectedWithEvidence)} /><SemanticInsightCard semantic={semantic} selectedVersion={selectedWithEvidence} aiResult={metricAiResult} aiStatus={metricAiStatus} onGenerateAi={generateMetricAi} disabled={executiveStreaming} /></div>
      <ExecutiveSummaryPanel version={selectedWithEvidence} onGenerate={generateExecutiveSummary} status={executiveStatus} result={executiveResult} />
      <ReproducibilitySnapshot version={selectedWithEvidence} parentLabel={parentVersionLabel(selectedWithEvidence)} />
      <FingerprintBreakdown version={selectedWithEvidence} focus={detailTab==="fingerprint"} />
      <LineageTimeline versions={versions} selectedVersion={selectedWithEvidence} parentLabel={parentVersionLabel} onSelect={(row)=>loadVersion(row,"lineage")} />
      <ComparisonSelector study={study} selectedVersion={selectedWithEvidence} versions={versions} compareBase={compareBase} compareId={compareId} setCompareId={setCompareId} options={compareOptions} semantic={semantic} pauseAi={executiveStreaming} />
      <VersionExportActions study={study} version={selectedWithEvidence} semantic={semantic} onExportBundle={exportBundle} onLoadReport={loadEvidenceReport} onExecutiveSummary={generateExecutiveSummary} reportStatus={reportStatus||executiveStatus} />
      {detailTab==="analysis"&&profile&&<VersionAnalysis key={selectedWithEvidence.id} study={study} version={selectedWithEvidence} profile={profile} timeline={semanticHistory} />}
    </>}
  </div>;
}

function CertificateSummaryCard({ label, value, detail, mono = false }) {
  return <Card className="certificate-summary-card">
    <p className="eyebrow">{label}</p>
    <strong className={mono?"mono":""}>{value||"Not Available"}</strong>
    <span>{detail||"Not Available"}</span>
  </Card>;
}

function fingerprintValue(value) {
  if(!value)return "";
  return typeof value==="string"?value:value.combined_fingerprint;
}

function shortHash(value) {
  const text=fingerprintValue(value)||value;
  return text ? `${String(text).slice(0,16)}...` : "";
}

function metricValue(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : value;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "";
}

function HashChip({ value }) {
  const text=fingerprintValue(value)||value;
  if(!text)return <Badge tone="medium">Pending</Badge>;
  return <button className="hash-chip copyable" onClick={()=>copyText(text)} title={text}>{shortHash(text)}</button>;
}

function copyText(value) {
  if(value&&navigator.clipboard)navigator.clipboard.writeText(String(value));
}

function HashDisclosure({ label, value, meaning }) {
  if(!value)return null;
  return <details className="hash-disclosure">
    <summary><span>{label}</span><span className="hash-summary-actions"><Badge tone="low">Verified</Badge><HashChip value={value}/></span></summary>
    <div>{meaning&&<p>{meaning}</p>}<code>{value}</code><Button type="button" variant="secondary compact" onClick={()=>copyText(value)}><Copy size={13}/>Copy</Button></div>
  </details>;
}

function VersionState({ label, value, mono = false }) {
  if(!value)return null;
  return <div className="version-state"><span>{label}</span><strong className={mono?"mono":""}>{value}</strong></div>;
}

function EvidenceStatus({ row }) {
  return <div className="evidence-status-chips">
    <Badge tone={row.fingerprint?"low":"medium"}>{row.fingerprint?"Fingerprint":"Fingerprint pending"}</Badge>
    {row.parent_version_id?<Badge>Revision</Badge>:<Badge>Baseline</Badge>}
  </div>;
}

function VersionIdentityCard({ version, datasetName, warnings = [], parentLabel = "Baseline" }) {
  const shortNote=versionContextItems(version).find((item)=>item.label==="Version notes"&&item.value.length<=80)?.value;
  return <Card className="evidence-certificate compact-certificate">
    <details>
      <summary>
        <div><p className="eyebrow">Version Identity</p><h2>V{version.version_number} - {datasetName}</h2><span>{version.parent_version_id?`Revision of ${parentLabel}`:"Baseline version"} | {version.row_count} rows | {version.column_count} columns</span></div>
        <Badge tone={warnings.length?"medium":"low"}>{warnings.length?"Needs Review":"Verified"}</Badge>
      </summary>
      <div className="context-list">
        <div className="context-row"><strong>Version</strong><span>V{version.version_number}</span></div>
        <div className="context-row"><strong>Parent Version</strong><span>{version.parent_version_id?parentLabel:<Badge>Baseline</Badge>}</span></div>
        <div className="context-row"><strong>Created</strong><span>{formatDate(version.created_at)||"Not Available"}</span></div>
        <div className="context-row"><strong>Rows</strong><span>{version.row_count}</span></div>
        <div className="context-row"><strong>Columns</strong><span>{version.column_count}</span></div>
        <div className="context-row"><strong>Fingerprint</strong><span>{version.fingerprint?"Verified":"Not Available"}</span></div>
        {shortNote&&<div className="context-row"><strong>Version note</strong><span>{shortNote}</span></div>}
      </div>
      <div className="certificate-status">{warnings.length?warnings.map((warning)=><Badge key={warning} tone="medium">{warning}</Badge>):<Badge tone="low">Evidence complete</Badge>}</div>
    </details>
  </Card>;
}

function VersionResearchContext({ version }) {
  const items=versionContextItems(version);
  if(!items.length)return null;
  const longCount=items.filter((item)=>item.value.length>80).length;
  return <Card className="version-research-context">
    <details>
      <summary>
        <div><p className="eyebrow">Research Context</p><h2>Study-specific version notes</h2><span>{longCount?`${longCount} long field${longCount===1?"":"s"} moved out of the header`:"Context fields recorded for this version"}</span></div>
        <Badge>{items.length} field{items.length===1?"":"s"}</Badge>
      </summary>
      <div className="research-context-list">
        {items.map((item)=><article key={item.label} className={item.value.length>80?"long":""}>
          <strong>{item.label}</strong>
          <p>{item.value}</p>
        </article>)}
      </div>
    </details>
  </Card>;
}

function versionContextItems(version) {
  const text=String(version?.version_notes||"").trim();
  if(!text)return [];
  const labelMap={
    "evidence role":"Evidence role",
    "source description":"Source description",
    "collection period":"Collection period",
    "known limitations":"Known limitations",
    "version notes":"Version notes"
  };
  const items=[];
  let current=null;
  text.split(/\r?\n/).forEach((line)=>{
    const clean=line.trim();
    if(!clean)return;
    const match=clean.match(/^([^:]{2,60}):\s*(.*)$/);
    if(match){
      const key=match[1].trim().toLowerCase();
      current={label:labelMap[key]||match[1].trim(),value:match[2].trim()};
      items.push(current);
    }else if(current){
      current.value=[current.value,clean].filter(Boolean).join(" ");
    }else{
      current={label:"Version notes",value:clean};
      items.push(current);
    }
  });
  return items.filter((item)=>item.value);
}

function FingerprintBreakdown({ version, focus }) {
  const meanings={
    "File hash":"Proves the exact uploaded file bytes used for this version.",
    "Schema hash":"Proves the column structure and inferred types used for this version.",
    "Metadata hash":"Proves the registration metadata captured during upload.",
    "Combined fingerprint":"Final identity key assembled from file, schema, metadata, and configuration evidence."
  };
  return <Card id="version-fingerprint-section" className={focus?"fingerprint-card focus-ring":"fingerprint-card"}>
    <details>
      <summary><div><p className="eyebrow">Fingerprint Certificate</p><h2>Hash evidence</h2><span>{version.fingerprint?"All available hash components are ready for audit.":"Fingerprint evidence is not available."}</span></div><Badge tone={version.fingerprint?"low":"medium"}>{version.fingerprint?"Verified":"Missing"}</Badge></summary>
      <div className="hash-stack">
        <HashDisclosure label="File hash" value={version.fingerprint?.file_hash||version.file_hash} meaning={meanings["File hash"]} />
        <HashDisclosure label="Schema hash" value={version.fingerprint?.schema_hash} meaning={meanings["Schema hash"]} />
        <HashDisclosure label="Metadata hash" value={version.fingerprint?.metadata_hash} meaning={meanings["Metadata hash"]} />
        <HashDisclosure label="Combined fingerprint" value={version.fingerprint?.combined_fingerprint} meaning={meanings["Combined fingerprint"]} />
      </div>
      {version.fingerprint?.algorithm_version&&<div className="context-row"><strong>Fingerprint ruleset</strong><span>{version.fingerprint.algorithm_version}</span></div>}
    </details>
  </Card>;
}

function ReproducibilitySnapshot({ version, parentLabel = "Baseline" }) {
  const config=version.configuration||{};
  const [bundleText,setBundleText]=useState("");
  const [candidateFile,setCandidateFile]=useState(null);
  const [verifyResult,setVerifyResult]=useState(null);
  const [verifyStatus,setVerifyStatus]=useState("");
  const exportBundle=async()=>{
    setVerifyStatus("Preparing recreation bundle...");
    try{
      const bundle=await datasetApi.recreationBundle(version.id);
      const text=JSON.stringify(bundle,null,2);
      setBundleText(text);
      downloadBlob(new Blob([text],{type:"application/json"}),`fedrepro-v${version.version_number}-recreation-bundle.json`);
      setVerifyStatus("Recreation bundle exported.");
    }catch(err){
      setVerifyStatus(err.response?.data?.detail||"Could not export recreation bundle.");
    }
  };
  const verify=async(event)=>{
    event.preventDefault();
    if(!candidateFile||!bundleText)return;
    setVerifyStatus("Verifying candidate CSV...");
    setVerifyResult(null);
    const data=new FormData();
    data.append("file",candidateFile);
    data.append("bundle_json",bundleText);
    try{
      const result=await datasetApi.verifyRecreation(data);
      setVerifyResult(result);
      setVerifyStatus(result.matched?"Candidate matches recreation bundle.":"Candidate does not match recreation bundle.");
    }catch(err){
      setVerifyStatus(err.response?.data?.detail||"Recreation verification failed.");
    }
  };
  const saveCandidate=()=>{
    if(candidateFile)downloadBlob(candidateFile,`recreated-v${version.version_number}-${candidateFile.name}`);
  };
  return <Card className="repro-snapshot" id="version-reproducibility-section">
    <p className="eyebrow">Reproducibility Panel</p><h2>Recreate V{version.version_number}</h2>
    <form className="recreate-tool" onSubmit={verify}>
      <div className="recreate-tool-head"><h3>Recreate tool</h3><Button type="button" variant="secondary compact" onClick={exportBundle}>Export bundle</Button></div>
      <Field label="Recreation bundle" full><textarea value={bundleText} onChange={(event)=>setBundleText(event.target.value)} placeholder="Paste or export a recreation bundle JSON" /></Field>
      <Field label="Candidate CSV" full><input type="file" accept=".csv" onChange={(event)=>setCandidateFile(event.target.files?.[0]||null)} /></Field>
      <div className="recreate-actions"><Button disabled={!candidateFile||!bundleText}>Verify candidate</Button>{verifyResult?.matched&&<Button type="button" variant="secondary" onClick={saveCandidate}>Save recreated CSV</Button>}</div>
      {verifyStatus&&<Notice error={verifyStatus.includes("failed")||verifyStatus.includes("does not match")}>{verifyStatus}</Notice>}
      {verifyResult&&<RecreationResult result={verifyResult} />}
    </form>
  </Card>;
}

function RecreationResult({ result }) {
  const metrics=result.metrics||{};
  const checks=result.checks||[];
  const passed=metrics.passed_checks??checks.filter((item)=>item.matched&&item.expected).length;
  const total=metrics.total_checks??checks.filter((item)=>item.expected).length;
  const similarity=result.similarity_rate??(total?Math.round((passed/total)*100):0);
  return <div className={result.matched?"recreation-result match":"recreation-result mismatch"}>
    <div className="row"><h3>{result.matched?"Recreated version verified":"Recreated version differs"}</h3><Badge tone={result.matched?"low":"medium"}>{similarity}% similarity</Badge></div>
    <div className="recreation-metrics">
      <VersionState label="Checks passed" value={`${passed}/${total}`} />
      <VersionState label="Shape match" value={metrics.shape_match?"Matched":"Different"} />
      <VersionState label="Row delta" value={signed(metrics.row_delta||0)} />
      <VersionState label="Column delta" value={signed(metrics.column_delta||0)} />
    </div>
    <div className="grid grid-2">
      <div className="context-list compact">
        <div className="context-row"><strong>Candidate</strong><span>{result.candidate.filename}</span></div>
        <div className="context-row"><strong>Shape</strong><span>{result.candidate.rows} rows / {result.candidate.columns} columns</span></div>
        {result.bundle?.expected_shape&&<div className="context-row"><strong>Expected shape</strong><span>{result.bundle.expected_shape.rows} rows / {result.bundle.expected_shape.columns} columns</span></div>}
      </div>
      <div className="checklist-compact">{checks.map((check)=><div key={check.name} className={check.matched?"complete":""}><CheckCircle2 size={14}/><span>{check.name.replaceAll("_"," ")}</span><Badge tone={check.matched?"low":"medium"}>{check.matched?"Matched":"Mismatch"}</Badge></div>)}</div>
    </div>
  </div>;
}

function LineageTimeline({ versions, selectedVersion, focus, onSelect, parentLabel = (version)=>version?.parent_version_id?`V${version.parent_version_id}`:"Baseline" }) {
  const [mode,setMode]=useState("lineage");
  const byId=new Map(versions.map((version)=>[version.id,version]));
  const childrenByParent=versions.reduce((acc,version)=>{
    const key=version.parent_version_id||"root";
    acc[key]=[...(acc[key]||[]),version];
    return acc;
  },{});
  const roots=(childrenByParent.root||versions.filter((version)=>!version.parent_version_id)).sort((a,b)=>a.version_number-b.version_number);
  const selectedParent=selectedVersion?.parent_version_id?byId.get(selectedVersion.parent_version_id):null;
  const selectedDiff=selectedVersion?.semantic_diff;
  const renderNode=(version,depth=0)=>{
    const diff=version.semantic_diff;
    const report=diff?.report||{};
    const transition=transitionLabel(version, report);
    const significant=Number(diff?.scm_score||0)>=30||Number(diff?.dsi_score||0)>=30;
    const children=childrenByParent[version.id]||[];
    const nodeKind=lineageNodeKind(version);
    const risk=lineageRisk(version);
    const transformations=recordedTransformations(version, report);
    return <div key={version.id} className="lineage-branch evolution-branch" style={{"--depth":depth}}>
      {version.parent_version_id&&<div className={`evolution-edge ${significant?"significant":""}`}>
        <span className="edge-arrow">-></span>
        <span>SCM {metricValue(diff?.scm_score)}</span>
        <span>DSI {metricValue(diff?.dsi_score)}</span>
        {significant&&<Badge tone="medium">Significant</Badge>}
        {transformations.slice(0,2).map((item)=><Badge key={`${version.id}-${item}`}>{item}</Badge>)}
      </div>}
      <button className={`lineage-graph-node evolution-node mode-${mode} ${version.id===selectedVersion?.id?"active":""} ${significant?"significant":""} ${nodeKind}`} onClick={()=>onSelect(version)} title={`V${version.version_number}, parent ${parentLabel(version)}, fingerprint ${version.fingerprint?"verified":"not available"}`}>
        <span className="evolution-node-head">
          <span className="lineage-node-title">V{version.version_number}</span>
          <span className="lineage-badges">
            <Badge tone={nodeKind==="variant"?"info":!version.parent_version_id?"low":"default"}>{lineageNodeBadge(version)}</Badge>
            {version.fingerprint&&<Badge tone="low">Fingerprint</Badge>}
          </span>
        </span>
        <span className="evolution-node-body">
          <strong>{transition}</strong>
          <small>{version.row_count} x {version.column_count} | {formatDate(version.created_at)||"Not Available"}</small>
        </span>
        <span className="evolution-node-metrics">
          <span><em>MLRS</em>{displayMetric(risk.mlrs)}</span>
          <span><em>LRS</em>{displayMetric(risk.lrs)}</span>
          <span><em>Method</em>{formatGenerationMethod(version.generation_method)}</span>
          <span><em>Hash</em>{shortHash(version.fingerprint)||"Not Available"}</span>
        </span>
      </button>
      {!!children.length&&<div className="lineage-children evolution-children">{children.sort((a,b)=>a.version_number-b.version_number).map((child)=>renderNode(child,depth+1))}</div>}
    </div>;
  };
  return <Card id="version-lineage-section" className={focus?"lineage-card focus-ring":"lineage-card"}>
    <div className="evolution-map-head">
      <div><p className="eyebrow">Dataset Evolution Map</p><h2>Provenance, semantic change, and risk trail</h2><span>Parent-child lineage with persisted fingerprints, SCM/DSI evidence, and recorded generation methods.</span></div>
      <div className="evolution-mode-tabs" role="tablist" aria-label="Dataset evolution map mode">
        {["lineage","impact","evidence"].map((item)=><button key={item} className={mode===item?"active":""} onClick={()=>setMode(item)} type="button">{item}</button>)}
      </div>
    </div>
    {!versions.length?<Empty>No versions are available for lineage.</Empty>:<div className={`lineage-graph evolution-map mode-${mode}`} role="tree">
      {roots.map((version)=>renderNode(version,0))}
    </div>}
    {selectedVersion&&<div className="lineage-detail-panel evolution-detail-panel">
      <div className="row"><div><p className="eyebrow">Selected-version comparison</p><h3>{selectedParent?`V${selectedParent.version_number} -> V${selectedVersion.version_number}`:`Baseline -> V${selectedVersion.version_number}`}</h3></div><Button variant="secondary compact" disabled={!selectedVersion.parent_version_id} onClick={()=>onSelect(selectedVersion)}>Open selected version</Button></div>
      <EvolutionStory selectedVersion={selectedVersion} parent={selectedParent} diff={selectedDiff} />
      <EvolutionComparison parent={selectedParent} selected={selectedVersion} diff={selectedDiff} />
      <EvolutionEvidenceDetails selected={selectedVersion} parent={selectedParent} diff={selectedDiff} parentLabel={parentLabel(selectedVersion)} />
    </div>
    }
  </Card>;
}

function lineageNodeKind(version) {
  if(!version.parent_version_id)return "baseline";
  return version.generation_method&&version.generation_method!=="manual"?"variant":"revision";
}

function lineageNodeBadge(version) {
  const kind=lineageNodeKind(version);
  if(kind==="baseline")return "Baseline";
  if(kind==="variant")return "Variant";
  return "Revision";
}

function formatGenerationMethod(method) {
  return method ? String(method).replaceAll("_"," ") : "manual";
}

function displayMetric(value, fallback = "Not Available") {
  return value==null?fallback:metricValue(value);
}

function lineageRisk(version) {
  return {
    mlrs: version.mlrs_score??version.diagnosis?.mlrs_score??version.diagnosis_report?.mlrs_score,
    lrs: version.lrs_score??version.diagnosis?.lrs_score??version.diagnosis_report?.lrs_score,
  };
}

function selectedMissingValue(version) {
  return version?.missing_cells??version?.profile?.summary?.missing_cells??version?.profile_report?.summary?.missing_cells;
}

function selectedDuplicateValue(version) {
  return version?.duplicate_rows??version?.profile?.summary?.duplicate_rows??version?.profile_report?.summary?.duplicate_rows;
}

function recordedTransformations(version, report = {}) {
  const labels=[];
  const method=String(version.generation_method||"").toLowerCase();
  const notes=String(version.version_notes||"").toLowerCase();
  const text=`${method} ${notes}`;
  if(method&&method!=="manual")labels.push(formatGenerationMethod(method));
  if(/duplicate/.test(text)||report.duplicate_rows?.delta<0)labels.push("Duplicate Removal");
  if(/missing|imput/.test(text)||Object.keys(report.missingness_changes_by_column||{}).length)labels.push("Missing Value Handling");
  if(/feature|select|reduction|drop/.test(text)||report.columns_removed?.length)labels.push("Feature Reduction");
  if(report.columns_added?.length)labels.push("Feature Addition");
  return [...new Set(labels)];
}

function EvolutionStory({ selectedVersion, parent, diff }) {
  const transforms=recordedTransformations(selectedVersion, diff?.report||{});
  const start=parent?`V${parent.version_number}`:"Baseline";
  const steps=[start,...transforms,`V${selectedVersion.version_number}`];
  return <div className="evolution-story" aria-label="Visual change story">
    {steps.map((step,index)=><span key={`${step}-${index}`} className={index===0||index===steps.length-1?"endpoint":""}>{step}</span>)}
  </div>;
}

function EvolutionComparison({ parent, selected, diff }) {
  const parentRisk=parent?lineageRisk(parent):{};
  const selectedRisk=lineageRisk(selected);
  const report=diff?.report||{};
  const rows=[
    evolutionComparisonRow("Rows", parent?.row_count, selected.row_count, "lower-neutral"),
    evolutionComparisonRow("Columns/features", parent?.column_count, selected.column_count, "lower-neutral"),
    evolutionComparisonRow("Missing values", selectedMissingValue(parent), selectedMissingValue(selected), "lower-better", report.missing_ratio_change),
    evolutionComparisonRow("Duplicates", selectedDuplicateValue(parent), selectedDuplicateValue(selected), "lower-better", report.duplicate_rows?.delta),
    evolutionComparisonRow("MLRS", parentRisk.mlrs, selectedRisk.mlrs, "lower-better"),
    evolutionComparisonRow("LRS", parentRisk.lrs, selectedRisk.lrs, "lower-better"),
    evolutionComparisonRow("SCM", null, diff?.scm_score, "lower-better"),
    evolutionComparisonRow("DSI", null, diff?.dsi_score, "lower-better"),
  ];
  return <div className="evolution-comparison-grid">
    {rows.map((row)=><article key={row.label} className={`evolution-change ${row.tone}`}>
      <strong>{row.label}</strong>
      <span>{row.before} -> {row.after}</span>
      <em>{row.delta}</em>
      <Badge tone={row.badgeTone}>{row.meaning}</Badge>
    </article>)}
  </div>;
}

function evolutionComparisonRow(label, beforeValue, afterValue, mode, explicitDelta = null) {
  const before=beforeValue==null?"Not Available":metricValue(beforeValue);
  const after=afterValue==null?"Not Available":metricValue(afterValue);
  const numericBefore=Number(beforeValue);
  const numericAfter=Number(afterValue);
  const numericDelta=explicitDelta!=null?Number(explicitDelta):(Number.isFinite(numericBefore)&&Number.isFinite(numericAfter)?numericAfter-numericBefore:null);
  const direction=numericDelta==null||!Number.isFinite(numericDelta)?"flat":numericDelta>0?"up":numericDelta<0?"down":"flat";
  const riskier=mode==="lower-better"&&direction==="up";
  const improved=mode==="lower-better"&&direction==="down";
  const meaning=improved?"Improved":riskier?"Increased risk":direction==="flat"?"Stable":"Changed";
  return {
    label,
    before,
    after,
    delta:numericDelta==null||!Number.isFinite(numericDelta)?"Delta unavailable":`${numericDelta>0?"+":""}${metricValue(numericDelta)}`,
    tone:improved?"improved":riskier?"riskier":"neutral",
    badgeTone:improved?"low":riskier?"medium":"default",
    meaning,
  };
}

function EvolutionEvidenceDetails({ selected, parent, diff, parentLabel }) {
  return <div className="evolution-evidence-grid">
    <VersionState label="Parent version" value={parent?`V${parent.version_number}`:parentLabel||"Baseline"} />
    <VersionState label="Combined fingerprint" value={shortHash(selected.fingerprint)||"Not Available"} mono />
    <VersionState label="Fingerprint verification" value={selected.fingerprint?"Verified":"Not Available"} />
    <VersionState label="Generation method" value={formatGenerationMethod(selected.generation_method)} />
    <VersionState label="Profile availability" value={selected.profile_report_id||selected.profile?"Available":"Not Available"} />
    <VersionState label="Diagnosis availability" value={selected.diagnosis||selected.diagnosis_report_id||lineageRisk(selected).mlrs!=null?"Available":"Not Available"} />
    <VersionState label="SCM" value={displayMetric(diff?.scm_score)} />
    <VersionState label="DSI" value={displayMetric(diff?.dsi_score)} />
    <VersionState label="Created" value={formatDate(selected.created_at)||"Not Available"} />
  </div>;
}

function transitionLabel(version, report = {}) {
  if(!version?.parent_version_id)return "Initial registration";
  const added=report.columns_added?.length||0;
  const removed=report.columns_removed?.length||0;
  const typeChanges=Object.keys(report.data_type_changes||{}).length;
  const rowDelta=Math.abs(report.row_count_change||0);
  const missingDelta=Math.abs(report.missing_ratio_change||0);
  if(added&&!removed&&!typeChanges)return "Schema expansion";
  if(removed&&!added)return "Schema reduction";
  if(added||removed||typeChanges)return "Mixed structural update";
  if(rowDelta>0)return "Row update";
  if(missingDelta>0)return "Metadata-quality update";
  return "Minimal measurable change";
}

function lineageStory(report) {
  if(!report||!Object.keys(report).length)return "Revision created; semantic details are not available yet.";
  const changes=[];
  if(report.row_count_change)changes.push(`${signed(report.row_count_change)} net rows`);
  if(report.columns_added?.length)changes.push(`${report.columns_added.length} columns added`);
  if(report.columns_removed?.length)changes.push(`${report.columns_removed.length} columns removed`);
  if(Object.keys(report.missingness_changes_by_column||{}).length)changes.push(`${Object.keys(report.missingness_changes_by_column||{}).length} missingness changes`);
  if(Object.keys(report.numeric_distribution_changes||{}).length)changes.push(`${Object.keys(report.numeric_distribution_changes||{}).length} numeric shifts`);
  return changes.length?changes.join(", "):"Revision has no material semantic changes reported.";
}

function lineageCompactStory(version, report) {
  const context=versionContextItems(version);
  const shortNote=context.find((item)=>item.label==="Version notes"&&item.value.length<=100)?.value;
  if(shortNote)return shortNote;
  const anyLongContext=context.some((item)=>item.value.length>100);
  const semanticStory=lineageStory(report);
  if(semanticStory&&semanticStory !== "Revision created; semantic details are not available yet.")return semanticStory;
  return anyLongContext?"Research context recorded; open the version to review details.":semanticStory;
}

function lineageImplication({ schemaChange, missingChanges, numericChanges, categoricalChanges, semantic }) {
  if(!semantic)return "Semantic comparison will describe the impact once available.";
  if(schemaChange)return "Schema changed, so feature compatibility and experiment comparability need review.";
  if(numericChanges||categoricalChanges)return "Distribution changed, so downstream metrics and findings may shift.";
  if(missingChanges)return "Missingness changed, so preprocessing and diagnosis should be reviewed.";
  return "No major semantic movement reported; this version appears comparable with its parent.";
}

function SemanticChangeSummary({ semantic, selectedVersion, parentLabel = "Baseline" }) {
  if(!semantic)return <Card className="semantic-summary-card"><p className="eyebrow">Semantic change intelligence</p><h2>{selectedVersion.parent_version_id?"Will be generated at next step":"Baseline version"}</h2><div className="context-list"><div className="context-row"><strong>Status</strong><span>{selectedVersion.parent_version_id?<Badge tone="medium">Pending</Badge>:<Badge>Baseline</Badge>}</span></div>{selectedVersion.parent_version_id&&<div className="context-row"><strong>Parent</strong><span>{parentLabel}</span></div>}<div className="context-row"><strong>SCM and DSI</strong><span>{selectedVersion.parent_version_id?"Will be generated when semantic comparison evidence is loaded.":"Not required for the first baseline version."}</span></div></div></Card>;
  const report=semantic.report||{};
  const rowContent=report.row_content_change;
  const missingChanges=Object.keys(report.missingness_changes_by_column||{}).length;
  const numericChanges=Object.keys(report.numeric_distribution_changes||{}).length;
  const categoricalChanges=Object.keys(report.categorical_distribution_changes||{}).length;
  const targetChange=report.target_distribution_change;
  const missingRows=Object.entries(report.missingness_changes_by_column||{}).map(([column,value])=>({column,...value})).sort((a,b)=>Math.abs(b.ratio_delta||0)-Math.abs(a.ratio_delta||0)).slice(0,4);
  const numericRows=Object.entries(report.numeric_distribution_changes||{}).map(([column,value])=>({column,...value})).sort((a,b)=>Number(b.normalized_shift_score||0)-Number(a.normalized_shift_score||0)).slice(0,4);
  const categoricalRows=Object.entries(report.categorical_distribution_changes||{}).flatMap(([column,rows])=>(rows||[]).slice(0,2).map((row)=>({column,...row}))).slice(0,4);
  return <Card className="semantic-summary-card">
    <p className="eyebrow">Semantic change intelligence</p><h2>What changed in V{selectedVersion.version_number}</h2>
    <div className="grid grid-2">
      <MetricCard label="SCM score" value={metricValue(semantic.scm_score)} icon={GitBranch} />
      <MetricCard label="DSI score" value={metricValue(semantic.dsi_score)} icon={ScanSearch} />
    </div>
    <div className="context-list">
      {rowContent&&<div className="context-row"><strong>Rows Added</strong><span>{rowContent.row_instances_added??"Not Available"}</span></div>}
      {rowContent&&<div className="context-row"><strong>Rows Removed</strong><span>{rowContent.row_instances_removed??"Not Available"}</span></div>}
      {report.row_count_change!=null&&!rowContent&&<div className="context-row"><strong>Rows changed</strong><span>{report.row_count_change}</span></div>}
      {!!report.columns_added?.length&&<div className="context-row"><strong>Columns added</strong><span>{report.columns_added.join(", ")}</span></div>}
      {!!report.columns_removed?.length&&<div className="context-row"><strong>Columns removed</strong><span>{report.columns_removed.join(", ")}</span></div>}
      <div className="context-row"><strong>Schema Changed</strong><span>{report.columns_added?.length||report.columns_removed?.length||Object.keys(report.data_type_changes||{}).length?"Yes":"No"}</span></div>
      {report.missing_ratio_change!=null&&<div className="context-row"><strong>Missingness changes</strong><span>{missingChanges} column{missingChanges===1?"":"s"} | {signedPct(report.missing_ratio_change)}</span></div>}
      <div className="context-row"><strong>Distribution Shift</strong><span>{numericChanges} numeric, {categoricalChanges} categorical</span></div>
      {report.duplicate_rows&&<div className="context-row"><strong>Duplicate change</strong><span>{signed(report.duplicate_rows.delta)}</span></div>}
      {targetChange&&Object.keys(targetChange).length>0&&<div className="context-row"><strong>Target distribution</strong><span>{Object.keys(targetChange).length} target value change{Object.keys(targetChange).length===1?"":"s"}</span></div>}
    </div>
    <div className="semantic-insight-grid">
      {!!missingRows.length&&<MiniEvidenceList title="Missingness" rows={missingRows.map((row)=>[row.column, `${signed(row.count_delta)} cells | ${signedPct(row.ratio_delta)}`])} />}
      {!!numericRows.length&&<MiniEvidenceList title="Numeric shifts" rows={numericRows.map((row)=>[row.column, `${row.change_level} | ${row.normalized_shift_score}`])} />}
      {!!categoricalRows.length&&<MiniEvidenceList title="Categorical shifts" rows={categoricalRows.map((row)=>[`${row.column}: ${row.value}`, `${signed(row.count_delta)} rows | ${signedPct(row.ratio_delta)}`])} />}
    </div>
  </Card>;
}

function SemanticInsightCard({ semantic, selectedVersion, aiResult, aiStatus, onGenerateAi, disabled = false }) {
  const hasScores=semantic&&semantic.scm_score!=null&&semantic.dsi_score!=null;
  return <Card className="ai-evidence-card semantic-ai-card">
    <p className="eyebrow">Evidence-bound AI insight</p><h2>SCM and DSI interpretation</h2>
    {!hasScores?<Notice>{selectedVersion.parent_version_id?"SCM and DSI will be generated at the semantic comparison step.":"This is the baseline version, so semantic comparison metrics are not needed yet."}</Notice>:<div className="context-list">
      <div className="context-row"><strong>SCM</strong><span>{metricValue(semantic.scm_score)}</span></div>
      <div className="context-row"><strong>DSI</strong><span>{metricValue(semantic.dsi_score)}</span></div>
    </div>}
    <Button variant="secondary" disabled={!semantic?.id||disabled} onClick={onGenerateAi}><Sparkles size={15}/>Generate AI interpretation</Button>
    {aiStatus&&<Notice error={aiStatus.includes("failed")||aiStatus.includes("Could not")}>{aiStatus}</Notice>}
    {aiResult&&<LLMFormattedContent content={aiResult.content} compact />}
  </Card>;
}

function ExecutiveSummaryPanel({ version, onGenerate, status, result }) {
  const visibleResult=result&&(!result.version_id||result.version_id===version?.id)?result:null;
  return <Card className="ai-evidence-card executive-summary-card">
    <div className="row">
      <div><p className="eyebrow">Executive summary generation</p><h2>Dataset research summary</h2></div>
      <Button variant="secondary" onClick={onGenerate}><Sparkles size={15}/>Generate executive summary</Button>
    </div>
    {status&&<Notice error={status.includes("failed")||status.includes("Could not")}>{status}</Notice>}
    {visibleResult&&<LLMFormattedContent content={visibleResult.content} />}
  </Card>;
}

function MiniEvidenceList({ title, rows }) {
  return <div className="mini-evidence-list"><h3>{title}</h3>{rows.map(([label,value])=><div key={`${title}-${label}`}><strong>{label}</strong><span>{value}</span></div>)}</div>;
}

const RISK_FAMILY_DEFINITIONS=[
  {key:"missingness",label:"Missingness",aliases:["missing","null","nan"]},
  {key:"duplicates",label:"Duplicates",aliases:["duplicate"]},
  {key:"outliers",label:"Outliers",aliases:["outlier"]},
  {key:"correlation",label:"Correlation",aliases:["corr","collinear"]},
  {key:"leakage",label:"Leakage",aliases:["leak","target_proxy"]},
  {key:"imbalance",label:"Imbalance",aliases:["class_imbalance","minority"]},
  {key:"scaling",label:"Scaling",aliases:["scale","standardization"]},
  {key:"drift",label:"Drift",aliases:["shift","distribution"]}
];

function normalizeRiskFamily(value) {
  const text=String(value||"").toLowerCase().replaceAll("-","_").replaceAll(" ","_");
  return RISK_FAMILY_DEFINITIONS.find((family)=>family.key===text||family.aliases.some((alias)=>text.includes(alias)))?.key||text;
}

function riskFamilyLabel(key) {
  const definition=RISK_FAMILY_DEFINITIONS.find((family)=>family.key===key);
  return definition?.label||String(key||"Risk").replaceAll("_"," ");
}

function isKnownRiskFamily(key) {
  return RISK_FAMILY_DEFINITIONS.some((family)=>family.key===key);
}

function riskFamiliesForFinding(finding) {
  const evidenceFamilies=Object.keys(finding?.evidence||{});
  return [...new Set([finding?.code, finding?.issue, finding?.risk, ...evidenceFamilies].map(normalizeRiskFamily).filter(isKnownRiskFamily))];
}

function RiskMapDetail({ row, families, findings = [], version }) {
  const activeFamilies=families.filter((family)=>row.familyKeys?.includes(family.key));
  const related=findings.filter((finding)=>DiagnosisFindingColumns(finding).includes(row.column));
  const source=row.raw?"Diagnosis contract column impact":"Diagnosis findings fallback";
  return <div className="risk-map-detail">
    <div className="risk-map-detail-grid">
      <article>
        <span>Feature</span>
        <strong>{row.column}</strong>
        <small>{row.role||"feature"} / {row.dataType||"type unavailable"}</small>
      </article>
      <article>
        <span>Risk families</span>
        <strong>{activeFamilies.length}</strong>
        <small>{activeFamilies.map((family)=>family.label).join(", ")||"No active family evidence"}</small>
      </article>
      <article>
        <span>Evidence source</span>
        <strong>{source}</strong>
        <small>{methodLabel(version)}</small>
      </article>
    </div>
    <div className="risk-family-chip-grid">
      {families.map((family)=><span key={family.key} className={row.familyKeys?.includes(family.key)?"active":""}>{family.label}</span>)}
    </div>
    <MiniEvidenceList title="Column evidence" rows={[
      ["Role",row.role||"feature"],
      ["Data type",row.dataType||"N/A"],
      ["Risks",activeFamilies.map((family)=>family.label).join(", ")||"None"],
      ["Recommended operations",row.recommendedOperationCount??"N/A"]
    ]} />
    <MiniEvidenceList title="Related findings" rows={related.length?related.map((finding)=>[finding.code,`${finding.severity} - ${finding.issue}`]):[["Status","No diagnosis finding names this feature directly"]]} />
  </div>;
}

function findingsForRiskMapRow(row, findings = []) {
  return findings.filter((finding)=>{
    const columns=DiagnosisFindingColumns(finding);
    return row.column==="Dataset-level" ? !columns.length : columns.includes(row.column);
  });
}

function highestSeverity(findings = []) {
  const order={critical:4,high:3,medium:2,low:1};
  return findings.reduce((best,item)=>((order[item.severity]||0)>(order[best]||0)?item.severity:best),"");
}

function ComparisonSelector({ study, selectedVersion, versions = [], compareBase, compareId, setCompareId, options, semantic, focus, pauseAi = false }) {
  const [comparison,setComparison]=useState(null);
  const [status,setStatus]=useState("");
  const [aiInterpretations,setAiInterpretations]=useState({});
  const [aiPathStatus,setAiPathStatus]=useState("");
  const selectedAgainstId=compareId||compareBase?.id||"";
  const selectedAgainst=options.find((version)=>String(version.id)===String(selectedAgainstId))||compareBase;
  const pathVersions=selectedAgainst?versions.filter((version)=>version.version_number>selectedAgainst.version_number&&version.version_number<=selectedVersion.version_number&&(!selectedVersion.dataset_id||!version.dataset_id||version.dataset_id===selectedVersion.dataset_id)).sort((a,b)=>a.version_number-b.version_number):[];
  const pathComparisons=pathVersions.map((version)=>({version,semantic:version.semantic_diff||(version.id===selectedVersion.id?semantic:null)})).filter((item)=>item.semantic);
  const defaultPreviousId=selectedVersion?.parent_version_id;
  const activeSemantic=comparison||(String(selectedAgainstId)===String(defaultPreviousId)?semantic:null);
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!selectedVersion||!selectedAgainstId){setComparison(null);setStatus("");return;}
      setStatus("Loading comparison...");
      try{
        const result=await datasetApi.compare(selectedVersion.id,selectedAgainstId);
        if(active){setComparison(result);setStatus("");}
      }catch(err){
        if(active){setComparison(null);setStatus(err.response?.data?.detail||"Comparison could not be loaded.");}
      }
    };
    load();
    return ()=>{active=false;};
  },[selectedVersion?.id,selectedAgainstId]);
  useEffect(()=>{
    setAiPathStatus("");
  },[study?.id,activeSemantic?.id,pathComparisons.map(({semantic})=>semantic?.id).filter(Boolean).join(","),pauseAi]);
  const interpretation=activeSemantic?comparisonInterpretation(activeSemantic):null;
  const exact=activeSemantic?comparisonExactChanges(activeSemantic):null;
  const pathLabel=selectedAgainst?`V${selectedAgainst.version_number} -> ${pathVersions.map((version)=>`V${version.version_number}`).join(" -> ")}`:"";
  const canCompare=Boolean(selectedVersion&&options.length);
  return <Card className={focus?"comparison-card focus-ring":"comparison-card"}>
    <p className="eyebrow">Version comparison selector</p><h2>Configure comparison</h2>
    <div className="form-grid">
      <Field label="Compare version"><input value={`V${selectedVersion.version_number}`} readOnly /></Field>
      <Field label="Against"><select value={selectedAgainstId} onChange={(event)=>setCompareId(event.target.value)} disabled={!canCompare}><option value="">{canCompare?"Select baseline version":"No previous versions"}</option>{options.map((version)=><option key={version.id} value={version.id}>V{version.version_number} - {version.dataset_name}</option>)}</select></Field>
    </div>
    {status&&<Notice error={!status.startsWith("Loading")}>{status}</Notice>}
    <div className="context-list">
      {activeSemantic&&<div className="context-row"><strong>Loaded comparison</strong><span>V{activeSemantic.previous_version_number||selectedAgainst?.version_number||activeSemantic.previous_version_id} to V{activeSemantic.current_version_number||selectedVersion.version_number}</span></div>}
      {selectedAgainst&&<div className="context-row"><strong>Selected baseline</strong><span>V{selectedAgainst.version_number}</span></div>}
      {selectedAgainst&&<div className="context-row"><strong>Intermediate path</strong><span>{pathLabel}</span></div>}
      {activeSemantic&&<div className="context-row"><strong>Ruleset</strong><span>{activeSemantic.ruleset_version||"Not Available"}</span></div>}
      {!activeSemantic&&<div className="context-row"><strong>Status</strong><span>{selectedVersion.parent_version_id?"Select a baseline version to load semantic comparison.":"Baseline has no previous version."}</span></div>}
    </div>
    {interpretation&&<ComparisonOverview semantic={activeSemantic} interpretation={interpretation} exact={exact} selectedAgainst={selectedAgainst} selectedVersion={selectedVersion} aiInterpretation={activeSemantic?.id?aiInterpretations[activeSemantic.id]:null} />}
    {selectedAgainst&&<div className="comparison-path-stack">
      <h3>Version-by-version semantic story</h3>
      {aiPathStatus&&<Notice>{aiPathStatus}</Notice>}
      {!pathComparisons.length?<Notice>Intermediate semantic diff evidence is not loaded for this path yet.</Notice>:pathComparisons.map(({version,semantic:stepSemantic})=><SemanticPathStep key={`${version.id}-${stepSemantic.id||version.version_number}`} version={version} semantic={stepSemantic} aiInterpretation={aiInterpretations[stepSemantic.id]} />)}
    </div>}
  </Card>;
}

function ComparisonOverview({ semantic, interpretation, exact, selectedAgainst, selectedVersion, aiInterpretation }) {
  const isStored=Boolean(semantic?.id);
  return <div className="comparison-overview">
    <div className="comparison-callout">
      <div><p className="eyebrow">Overall comparison</p><h3>{selectedAgainst?`V${selectedAgainst.version_number} to V${selectedVersion.version_number}`:"Selected comparison"}</h3></div>
      <div className="lineage-badges"><Badge>SCM {metricValue(semantic.scm_score)}</Badge><Badge>DSI {metricValue(semantic.dsi_score)}</Badge></div>
      {aiInterpretation?.content?<div className="semantic-ai-narrative"><LLMFormattedContent content={aiInterpretation.content} compact /></div>:aiInterpretation?.error?<Notice>{aiInterpretation.error}</Notice>:<Notice>Measured comparison evidence is shown below.</Notice>}
    </div>
    <details className="comparison-raw-details">
      <summary>Show measured aggregate evidence</summary>
      <div className="comparison-exact-grid">
        <MiniEvidenceList title="Main measured changes" rows={interpretation.mainChanges.slice(0,4)} />
        <MiniEvidenceList title="Schema" rows={exact.schema} />
        <MiniEvidenceList title="Rows and quality" rows={exact.quality} />
        <MiniEvidenceList title="Distribution" rows={exact.distribution} />
        <MiniEvidenceList title="Target" rows={exact.target} />
      </div>
    </details>
  </div>;
}

function SemanticPathStep({ version, semantic, aiInterpretation }) {
  const exact=comparisonExactChanges(semantic);
  const interpretation=comparisonInterpretation(semantic);
  const previous=version.version_number-1;
  const current=version.version_number;
  return <article className="semantic-path-step">
    <div className="row">
      <div><h3>V{previous} to V{current}</h3><p>{version.version_notes||lineageStory(semantic.report||{})}</p></div>
      <div className="lineage-badges"><Badge>SCM {metricValue(semantic.scm_score)}</Badge><Badge>DSI {metricValue(semantic.dsi_score)}</Badge></div>
    </div>
    {aiInterpretation?.content?<div className="semantic-ai-narrative"><LLMFormattedContent content={aiInterpretation.content} compact /></div>:aiInterpretation?.error?<Notice>{aiInterpretation.error}</Notice>:<Notice>Measured transition evidence is shown below.</Notice>}
    <details className="comparison-raw-details">
      <summary>Show measured changes for this transition</summary>
      <div className="comparison-exact-grid">
        <MiniEvidenceList title="Main measured changes" rows={interpretation.mainChanges} />
        <MiniEvidenceList title="Exact quality changes" rows={exact.quality} />
        <MiniEvidenceList title="Distribution and target" rows={[...exact.distribution.slice(0,3),...exact.target.slice(0,2)]} />
      </div>
    </details>
  </article>;
}

function comparisonInterpretation(semantic) {
  const report=semantic.report||{};
  const missingCount=Object.keys(report.missingness_changes_by_column||{}).length;
  const numericCount=Object.keys(report.numeric_distribution_changes||{}).length;
  const categoricalCount=Object.keys(report.categorical_distribution_changes||{}).length;
  const schemaChanged=Boolean(report.columns_added?.length||report.columns_removed?.length||Object.keys(report.data_type_changes||{}).length);
  const rowDelta=report.row_count_change??(report.row_content_change ? (report.row_content_change.row_instances_added||0)-(report.row_content_change.row_instances_removed||0) : null);
  const scm=Number(semantic.scm_score);
  const dsi=Number(semantic.dsi_score);
  const stable=Number.isFinite(scm)&&Number.isFinite(dsi)&&scm<20&&dsi<20&&!schemaChanged;
  const goodForMl=stable&&missingCount<3;
  return {
    mainChanges:[
      ["Rows", rowDelta==null?"No row count delta reported":`${signed(rowDelta)} net rows`],
      ["Schema", schemaChanged?`${report.columns_added?.length||0} added, ${report.columns_removed?.length||0} removed`:"No schema change reported"],
      ["Missingness", `${missingCount} column${missingCount===1?"":"s"} changed`],
      ["Distribution", `${numericCount} numeric and ${categoricalCount} categorical changes`],
    ],
    stability:[
      ["Assessment", stable?"More stable or comparable to previous version":"Needs review before treating as equivalent"],
      ["SCM", metricValue(semantic.scm_score)],
      ["DSI", metricValue(semantic.dsi_score)],
    ],
    mlSuitability:[
      ["Decision", goodForMl?"Suitable for ML continuation with evidence":"Review diagnosis and drift before downstream experiments"],
      ["Reason", goodForMl?"Low change signals and limited missingness movement.":"Semantic or distribution movement may affect model behavior."],
    ],
    whyItMatters:[
      ["Model metrics", numericCount||categoricalCount?"Distribution changes can alter validation behavior and feature importance.":"No material distribution movement was reported."],
      ["Findings", schemaChanged?"Schema changes may change reproducibility and experiment comparability.":"Schema appears comparable for version-to-version analysis."],
    ],
  };
}

function comparisonExactChanges(semantic) {
  const report=semantic.report||{};
  const missingRows=Object.entries(report.missingness_changes_by_column||{})
    .map(([column,value])=>[column, `${signed(value.count_delta||0)} missing cells, ${signedPct(value.ratio_delta||0)}`])
    .slice(0,5);
  const numericRows=Object.entries(report.numeric_distribution_changes||{})
    .map(([column,value])=>[column, `${value.change_level||adaptiveLevel(value.normalized_shift_score)} shift, score ${value.normalized_shift_score??"Not Available"}`])
    .slice(0,5);
  const categoricalRows=Object.entries(report.categorical_distribution_changes||{})
    .flatMap(([column,rows])=>(rows||[]).slice(0,2).map((row)=>[`${column}: ${row.value}`, `${signed(row.count_delta||0)} rows, ${signedPct(row.ratio_delta||0)}`]))
    .slice(0,5);
  const targetRows=Object.entries(report.target_distribution_change||{})
    .map(([label,value])=>[label, `${signed(value.count_delta||0)} rows, ${signedPct(value.ratio_delta||0)}`])
    .slice(0,5);
  return {
    schema:[
      ["Columns added", report.columns_added?.join(", ")||"None reported"],
      ["Columns removed", report.columns_removed?.join(", ")||"None reported"],
      ["Type changes", Object.keys(report.data_type_changes||{}).join(", ")||"None reported"],
    ],
    quality:[
      ["Row count", report.row_count_change==null?"Not Available":`${signed(report.row_count_change)} rows`],
      ["Duplicate rows", report.duplicate_rows?.delta==null?"Not Available":`${signed(report.duplicate_rows.delta)} duplicates`],
      ["Missingness", missingRows.length?`${missingRows.length} changed columns shown below`:"No changed missingness reported"],
      ...missingRows,
    ],
    distribution:[
      ...(numericRows.length?numericRows:[["Numeric columns","No material numeric shift reported"]]),
      ...(categoricalRows.length?categoricalRows:[["Categorical columns","No material categorical shift reported"]]),
    ].slice(0,6),
    target:targetRows.length?targetRows:[["Target distribution","No target movement reported"]],
  };
}

function VersionExportActions({ study, version, semantic, onExportBundle, onLoadReport, onExecutiveSummary, reportStatus }) {
  const exportSemantic=()=>semantic&&downloadBlob(new Blob([JSON.stringify(semantic,null,2)],{type:"application/json"}),`fedrepro-v${version.version_number}-semantic-comparison.json`);
  return <Card className="version-action-card">
    <p className="eyebrow">Export actions</p><h2>Evidence outputs</h2>
    <div className="action-stack horizontal">
      <Button variant="secondary" onClick={onExportBundle}><FileCheck2 size={15}/>Recreation bundle JSON</Button>
      <Button variant="secondary" onClick={onLoadReport}><Eye size={15}/>Saved explanation report</Button>
      <Button variant="secondary" disabled={!semantic} onClick={exportSemantic}><GitCompare size={15}/>Semantic comparison JSON</Button>
      <Button variant="secondary" onClick={onExecutiveSummary}><Sparkles size={15}/>Executive summary</Button>
      <ReportActions study={study} compact />
      <Button variant="secondary" disabled>Version certificate DOCX</Button>
      <Button variant="secondary" disabled>Fingerprint certificate JSON</Button>
    </div>
    {reportStatus&&<Notice error={reportStatus.includes("Could not")}>{reportStatus}</Notice>}
  </Card>;
}

function integrityWarnings(version, profile) {
  if(!version)return [];
  return [
    !version.fingerprint&&"Missing fingerprint",
    !profile&&"Missing profile report",
    !version.semantic_diff&&"Version has no semantic diff because it is baseline",
    version&&!profile&&"Registration completed but no analysis loaded"
  ].filter(Boolean);
}

function IntegrityWarnings({ warnings }) {
  if(!warnings.length)return null;
  return <div className="integrity-warnings">{warnings.map((warning)=><Notice key={warning}><AlertTriangle size={14}/>{warning}</Notice>)}</div>;
}

function LegacyVersionPanel({ study, datasets, selectedVersion, profile, semanticHistory, onVersion, onDelete, status }) {
  const versions=datasets.flatMap((dataset)=>dataset.versions.map((version)=>({...version,dataset_name:dataset.name})));
  const remove=(row)=>{if(window.confirm(`Delete ${row.dataset_name} V${row.version_number}? This permanently removes its file, profile, diagnosis, and dependent semantic comparisons.`))onDelete(row.id);};
  return <div className="stack"><Card><h2>Versioning and fingerprints</h2><p className="muted">View a saved analysis or permanently remove a version and its generated evidence.</p>{status&&<Notice error={status.includes("Could not")}>{status}</Notice>}{!versions.length?<Empty>Versions appear after a registration is configured.</Empty>:<DataTable rows={versions} columns={[{key:"dataset_name",label:"Dataset"},{key:"version_number",label:"Version",render:(r)=>`V${r.version_number}`},{key:"row_count",label:"Rows"},{key:"column_count",label:"Columns"},{key:"file_hash",label:"File hash",render:(r)=><span className="mono">{r.file_hash.slice(0,16)}…</span>},{key:"fingerprint",label:"Fingerprint",render:(r)=><span className="mono">{r.fingerprint?.slice(0,16)}…</span>},{key:"action",label:"Actions",render:(r)=><div className="row" style={{justifyContent:"flex-start"}}><Button variant="secondary compact" onClick={()=>onVersion(r.id)}>View analysis</Button><Button variant="danger compact" aria-label={`Delete ${r.dataset_name} version ${r.version_number}`} onClick={()=>remove(r)}><Trash2 size={14} />Delete</Button></div>}]} />}</Card>{selectedVersion&&profile&&<VersionAnalysis key={selectedVersion.id} study={study} version={selectedVersion} profile={profile} timeline={semanticHistory} />}</div>;
}

function VersionAnalysis({ study, version, profile, timeline }) {
  const report=profile.report;
  const [aiResult,setAiResult]=useState(null);
  const [aiStatus,setAiStatus]=useState("");
  const generateInsights=async()=>{
    setAiStatus("Generating evidence-bound insights with Ollama…");
    setAiResult(null);
    try{
      setAiResult(await aiApi.explain(study.id,{explanation_type:"version_analysis",source_entity_id:version.id}));
      setAiStatus("");
    }catch(err){
      setAiStatus(aiFallbackMessage());
    }
  };
  const aiLoading=aiStatus.startsWith("Generating");
  return <div className="stack">
    <Card>
      <p className="eyebrow">Selected version analysis</p>
      <h2>Dataset V{version.version_number}</h2>
      <p className="muted">Profile for the selected version and semantic evolution from the baseline through V{version.version_number}.</p>
      <div className="context-list">
        <div className="context-row"><strong>Target</strong><span>{version.configuration.target_column||"Unsupervised"}</span></div>
        <div className="context-row"><strong>Primary metric</strong><span>{version.configuration.primary_metric||"Not applicable"}</span></div>
        <div className="context-row"><strong>Validation</strong><span>{version.configuration.validation_strategy||"Not applicable"}</span></div>
        <div className="context-row"><strong>Fingerprint</strong><span className="mono">{version.fingerprint.combined_fingerprint}</span></div>
      </div>
    </Card>
    <div className="grid grid-4">
      {[["Rows",report.summary.row_count,Database],["Columns",report.summary.column_count,FileStack],["Missing",`${(report.summary.missing_ratio*100).toFixed(1)}%`,Gauge],["Duplicates",report.summary.duplicate_rows,ScanSearch]].map(([label,value,Icon])=><MetricCard key={label} label={label} value={value} icon={Icon} />)}
    </div>
    <Card>
      <p className="eyebrow">Dataset profile</p>
      <h2>Column statistics for V{version.version_number}</h2>
      <DataTable rows={report.columns} columns={[{key:"name",label:"Column"},{key:"role",label:"Role"},{key:"data_type",label:"Type"},{key:"missing_ratio",label:"Missing",render:(row)=>`${(row.missing_ratio*100).toFixed(1)}%`},{key:"unique_count",label:"Unique"},{key:"outlier_count",label:"Outliers"}]} />
    </Card>
    <Card>
      <p className="eyebrow">Task evidence</p>
      <h2>Task-aware profile</h2>
      <pre className="pre">{JSON.stringify(report.task_profile,null,2)}</pre>
    </Card>
    <Card>
      <p className="eyebrow">Version history</p>
      <h2>Semantic evolution through V{version.version_number}</h2>
      <div className="stack">
        {timeline.map((item)=><SemanticVersionChange key={item.id} item={item} />)}
      </div>
    </Card>
    <Card className="ai-panel">
      <p className="eyebrow">Optional LLM interpretation</p>
      <h2>Human-understandable insights</h2>
      <p className="muted">Ollama receives the ML study, selected profile, version history, and semantic diffs. It explains persisted evidence only and cannot alter calculated results.</p>
      <Button onClick={generateInsights} disabled={aiLoading}>{aiLoading?"Generating insights…":"Generate AI insights"}</Button>
      {aiStatus&&<Notice error={!aiLoading}>{aiStatus}</Notice>}
      {aiResult&&<AIInsightReport result={aiResult} />}
    </Card>
  </div>;
}

function SemanticVersionChange({ item }) {
  const diff=item.semantic_diff;
  if(!diff)return <div className="context-row" style={{alignItems:"flex-start"}}><strong>V{item.version_number}</strong><div><p>{item.row_count} rows · {item.column_count} columns</p><p className="muted">Reproducible baseline—no previous version to compare.</p></div></div>;
  const report=diff.report;
  const missingRows=Object.entries(report.missingness_changes_by_column||{}).map(([column,change])=>({id:column,column,...change}));
  const allNumericRows=Object.entries(report.numeric_distribution_changes||{}).map(([column,change])=>({id:column,column,...change}));
  const numericRows=allNumericRows.filter((row)=>(row.change_level||adaptiveLevel(row.normalized_shift_score))!=="negligible");
  const omittedNumericCount=allNumericRows.length-numericRows.length;
  const categorical=Object.entries(report.categorical_distribution_changes||{});
  const types=Object.entries(report.data_type_changes||{});
  const addedDetails=report.columns_added_details||{};
  const removedDetails=report.columns_removed_details||{};
  const rowContent=report.row_content_change;
  const duplicates=report.duplicate_rows;
  return <div className="semantic-version">
    <div className="row">
      <div><p className="eyebrow">Transition into V{item.version_number}</p><h3>{item.row_count} rows · {item.column_count} columns</h3></div>
      <div className="row"><Badge>SCM {diff.scm_score}</Badge><Badge>DSI {diff.dsi_score}</Badge></div>
    </div>
    <div className="grid grid-2">
      <div className="change-cluster">
        <p className="metric-label">Schema changes</p>
        <p><strong>Added:</strong> {report.columns_added?.join(", ")||"None"}</p>
        {Object.entries(addedDetails).map(([column,value])=><p className="muted" key={`added-${column}`}>{column}: {value.data_type}, {pct(value.missing_ratio)} missing, {value.unique_count} unique</p>)}
        <p><strong>Removed:</strong> {report.columns_removed?.join(", ")||"None"}</p>
        {Object.entries(removedDetails).map(([column,value])=><p className="muted" key={`removed-${column}`}>{column}: {value.data_type}, {pct(value.missing_ratio)} missing, {value.unique_count} unique</p>)}
        {!types.length?<p className="muted">No data-type changes.</p>:types.map(([column,value])=><p key={column}><strong>{column}:</strong> {value.previous} → {value.current}</p>)}
      </div>
      <div className="change-cluster">
        <p className="metric-label">Rows and duplicates</p>
        <p><strong>Net row change:</strong> {signed(report.row_count_change)}</p>
        {rowContent&&<><p><strong>Row signatures:</strong> {rowContent.unchanged_row_instances} unchanged, {rowContent.row_instances_added} added or modified, {rowContent.row_instances_removed} removed or modified</p><p className="muted">{pct(rowContent.turnover_ratio)} row-signature turnover; edits are counted as one removed and one added signature.</p></>}
        {duplicates&&<p><strong>Duplicate rows:</strong> {duplicates.previous} → {duplicates.current} ({signed(duplicates.delta)})</p>}
      </div>
    </div>
    <div className="change-cluster">
      <p className="metric-label">Missingness changes by column</p>
      {!missingRows.length?<p className="muted">No column-level missingness changes.</p>:<DataTable rows={missingRows} columns={[{key:"column",label:"Column"},{key:"counts",label:"Missing cells",render:(row)=>`${row.previous_count} → ${row.current_count} (${signed(row.count_delta)})`},{key:"ratios",label:"Missing ratio",render:(row)=>`${pct(row.previous_ratio)} → ${pct(row.current_ratio)} (${signedPct(row.ratio_delta)})`}]} />}
    </div>
    <div className="change-cluster">
      <p className="metric-label">Numeric distribution changes</p>
      {!numericRows.length?<p className="muted">No numeric shift crossed the adaptive reporting threshold.</p>:<DataTable rows={numericRows} columns={[{key:"column",label:"Column"},{key:"mean",label:"Mean",render:(row)=>`${number(row.previous.mean)} → ${number(row.current.mean)} (${signedNumber(row.delta.mean)})`},{key:"median",label:"Median",render:(row)=>`${number(row.previous.median)} → ${number(row.current.median)} (${signedNumber(row.delta.median)})`},{key:"range",label:"Range",render:(row)=>`${number(row.previous.min)}–${number(row.previous.max)} → ${number(row.current.min)}–${number(row.current.max)}`},{key:"shift",label:"Shift",render:(row)=><><Badge tone={levelTone(row.change_level||adaptiveLevel(row.normalized_shift_score))}>{row.change_level||adaptiveLevel(row.normalized_shift_score)}</Badge> {row.normalized_shift_score}</>}]} />}
      {omittedNumericCount>0&&<p className="muted" style={{marginTop:8}}>{omittedNumericCount} unchanged or negligible numeric column{omittedNumericCount===1?" was":"s were"} omitted.</p>}
    </div>
    <div className="change-cluster">
      <p className="metric-label">Categorical and target distribution changes</p>
      {!categorical.length?<p className="muted">No material categorical distribution changes.</p>:categorical.map(([column,rows])=><div key={column} style={{marginTop:12}}><h3>{column}</h3><DataTable rows={rows.map((row)=>({...row,id:`${column}-${row.value}`}))} columns={[{key:"value",label:"Value"},{key:"count",label:"Count",render:(row)=>`${row.previous_count} → ${row.current_count} (${signed(row.count_delta)})`},{key:"share",label:"Share",render:(row)=>`${pct(row.previous_ratio)} → ${pct(row.current_ratio)} (${signedPct(row.ratio_delta)})`}]} /></div>)}
    </div>
    <p className="muted">Deterministic semantic ruleset {diff.ruleset_version}.</p>
  </div>;
}

function AIInsightReport({ result }) {
  const insight=result.structured_content;
  return <div className="ai-insight-report">
    <div className="ai-insight-meta">
      <Badge>{result.model}</Badge>
      <span>Prompt {result.prompt_version}</span>
      <span>Evidence {result.source_evidence_hash.slice(0,12)}</span>
    </div>
    {!insight?<div className="ai-insight-section"><h3>Generated interpretation</h3><div className="ai-insight-text">{result.content}</div></div>:<>
      {insight.generation_note&&<div className={`ai-generation-note ${insight.generation_note.startsWith("Ollama could not")?"fallback":""}`}>{insight.generation_note}</div>}
      <section className="ai-insight-section executive">
        <p className="eyebrow">Executive summary</p>
        <p>{insight.executive_summary}</p>
      </section>
      <section className="ai-insight-section">
        <h3>Selected version profile</h3>
        <ul>{(insight.selected_version_profile||[]).map((item,index)=><li key={index}>{item}</li>)}</ul>
      </section>
      <section className="ai-insight-section">
        <h3>Version evolution</h3>
        <div className="stack">{(insight.version_evolution||[]).map((item,index)=><article className="ai-evolution-item" key={`${item.transition}-${index}`}><h4>{item.transition}</h4><ul>{(item.changes||[]).map((change,changeIndex)=><li key={changeIndex}>{change}</li>)}</ul><p><strong>Interpretation:</strong> {item.interpretation}</p></article>)}</div>
      </section>
      <section className="ai-insight-section caution">
        <h3>Research cautions</h3>
        <ul>{(insight.research_cautions||[]).map((item,index)=><li key={index}>{item}</li>)}</ul>
      </section>
      {!!(insight.reproducibility_recipe||[]).length&&<section className="ai-insight-section">
        <h3>Reproducibility recipe</h3>
        <ul>{insight.reproducibility_recipe.map((item,index)=><li key={index}>{item}</li>)}</ul>
      </section>}
      {!!(insight.potential_effects||[]).length&&<section className="ai-insight-section">
        <h3>Potential effects</h3>
        <ul>{insight.potential_effects.map((item,index)=><li key={index}>{item}</li>)}</ul>
      </section>}
      {!!(insight.recommended_next_checks||[]).length&&<section className="ai-insight-section">
        <h3>Recommended next checks</h3>
        <ul>{insight.recommended_next_checks.map((item,index)=><li key={index}>{item}</li>)}</ul>
      </section>}
      <section className="ai-insight-section conclusion">
        <h3>Conclusion</h3>
        <p>{insight.conclusion}</p>
      </section>
    </>}
  </div>;
}

const number=(value)=>value==null?"—":Number(value).toFixed(3);
const signedNumber=(value)=>value==null?"—":`${value>0?"+":""}${Number(value).toFixed(3)}`;
const signed=(value)=>`${Number(value)>0?"+":""}${Number(value)}`;
const pct=(value)=>`${(Number(value||0)*100).toFixed(2)}%`;
const signedPct=(value)=>`${Number(value)>0?"+":""}${(Number(value||0)*100).toFixed(2)} pp`;
const adaptiveLevel=(score)=>Number(score)<.1?"negligible":Number(score)<1?"minor":Number(score)<5?"moderate":"major";
const levelTone=(level)=>level==="major"?"high":level==="moderate"?"medium":"low";

function DiagnosisVersionSelector({ datasets = [], version, onVersion, status, setStatus, transientStatus = null }) {
  const datasetsWithVersions=datasets.filter((dataset)=>dataset.versions?.length);
  const [selectedDatasetId,setSelectedDatasetId]=useState(version?.dataset_id?String(version.dataset_id):String(datasetsWithVersions[0]?.id||""));
  useEffect(()=>{
    if(version?.dataset_id)setSelectedDatasetId(String(version.dataset_id));
    else if(!selectedDatasetId&&datasetsWithVersions[0])setSelectedDatasetId(String(datasetsWithVersions[0].id));
  },[version?.dataset_id,datasetsWithVersions.length]);
  const selectedDataset=datasetsWithVersions.find((dataset)=>String(dataset.id)===String(selectedDatasetId));
  const versionOptions=(selectedDataset?.versions||[]).slice().sort((a,b)=>a.version_number-b.version_number);
  const selectedVersionId=version&&String(version.dataset_id)===String(selectedDatasetId)?String(version.id):"";
  const chooseVersion=async(event)=>{
    const id=event.target.value;
    if(!id)return;
    setStatus("Loading selected diagnosis version...");
    try{
      await onVersion(id);
      setStatus("");
    }catch(err){
      setStatus(err.response?.data?.detail||"Could not load selected version.");
    }
  };
  return <Card className="diagnosis-selector-card">
    <div className="version-page-head">
      <div><p className="eyebrow">Diagnosis target</p><h2>Select dataset and version</h2></div>
      {version&&<Badge>V{version.version_number}</Badge>}
    </div>
    {!datasetsWithVersions.length?<Empty>No configured dataset versions are available for diagnosis.</Empty>:<div className="form-grid">
      <Field label="Dataset"><select value={selectedDatasetId} onChange={(event)=>setSelectedDatasetId(event.target.value)}>{datasetsWithVersions.map((dataset)=><option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></Field>
      <Field label="Version"><select value={selectedVersionId} onChange={chooseVersion}><option value="">Select version</option>{versionOptions.map((item)=><option key={item.id} value={item.id}>V{item.version_number} - {item.row_count} rows, {item.column_count} columns</option>)}</select></Field>
    </div>}
    {!!versionOptions.length&&<div className="diagnosis-version-status-list">
      {versionOptions.map((item)=><button type="button" key={item.id} className={version?.id===item.id?"active":""} onClick={()=>onVersion(item.id)}>
        {(()=>{
          const shownStatus = version?.id===item.id && transientStatus ? transientStatus : item.diagnosis_status || "Not Diagnosed";
          return <>
        <strong>V{item.version_number}</strong>
        <span>{formatGenerationMethod(item.generation_method)}</span>
        <Badge tone={shownStatus==="Diagnosed"?"success":shownStatus==="Recompute Available"||shownStatus==="Running"?"warning":shownStatus==="Failed"?"critical":"neutral"}>{shownStatus}</Badge>
        <em>MLRS {displayMetric(item.diagnosis?.mlrs_score, "N/A")} - LRS {displayMetric(item.diagnosis?.lrs_score, "N/A")}</em>
          </>;
        })()}
      </button>)}
    </div>}
    {status&&<Notice error={status.includes("Could not")}>{status}</Notice>}
  </Card>;
}

function DiagnosisEvidenceSummary({ version, profile, diagnosis, contract }) {
  const summary=profile?.report?.summary||{};
  const task=profile?.report?.task_profile||{};
  const semantic=version?.semantic_diff;
  const scoreBreakdown=diagnosis?.score_breakdown||diagnosis?.diagnosis?.score_breakdown||{};
  const mlrsComponents=scoreBreakdown.mlrs_components||diagnosis?.mlrs_components||{};
  const lrsComponents=scoreBreakdown.lrs_components||diagnosis?.lrs_components||{};
  const generatorHints=scoreBreakdown.variant_generator_hints||[];
  const leakageFindings=(diagnosis?.findings||[]).filter((item)=>item.code==="TARGET_LEAKAGE");
  const severityCounts=(diagnosis?.findings||[]).reduce((acc,item)=>({...acc,[item.severity]:(acc[item.severity]||0)+1}),{});
  const decisionRows=[
    ["Readiness", contract?.readiness?.status],
    ["MLRS", metricValue(diagnosis?.mlrs_score)],
    ["LRS", metricValue(diagnosis?.lrs_score)],
    ["Findings", diagnosis?.findings?.length],
    ["Interventions", contract?.readiness?.intervention_count],
    ["Required decisions", contract?.readiness?.required_decision_count],
  ];
  const leakageRows=[
    ["Leakage findings", leakageFindings.length],
    ["Affected columns", [...new Set(leakageFindings.flatMap((finding)=>DiagnosisFindingColumns(finding)))].join(", ")||"Not Available"],
    ["LRS", metricValue(diagnosis?.lrs_score)],
    ["Evidence status", leakageFindings.length?"Finding present":"No persisted leakage finding"],
  ];
  const stabilityRows=[
    ["SCM", semantic?metricValue(semantic.scm_score):"Not Available"],
    ["DSI", semantic?metricValue(semantic.dsi_score):"Not Available"],
    ["Schema added", semantic?.report?.columns_added?.join(", ")||"Not Available"],
    ["Schema removed", semantic?.report?.columns_removed?.join(", ")||"Not Available"],
    ["Duplicate delta", semantic?.report?.duplicate_rows?.delta??"Not Available"],
    ["Missingness delta", semantic?.report?.missing_ratio_change!=null?signedPct(semantic.report.missing_ratio_change):"Not Available"],
  ];
  const qualityRows=[
    ["Rows", summary.row_count??version?.row_count],
    ["Columns", summary.column_count??version?.column_count],
    ["Missing cells", summary.missing_cells??"Not Available"],
    ["Missing ratio", summary.missing_ratio!=null?pct(summary.missing_ratio):"Not Available"],
    ["Duplicate rows", summary.duplicate_rows??"Not Available"],
    ["Target classes", task.class_distribution?Object.entries(task.class_distribution).map(([key,value])=>`${key}: ${value}`).join(", "):"Not Available"],
  ];
  return <div className="diagnosis-evidence-grid">
    <MiniEvidenceList title="Training readiness" rows={decisionRows} />
    <MiniEvidenceList title="Leakage review" rows={leakageRows} />
    <MiniEvidenceList title="MLRS components" rows={componentRows(mlrsComponents)} />
    <MiniEvidenceList title="LRS components" rows={componentRows(lrsComponents)} />
    <MiniEvidenceList title="Stability evidence" rows={stabilityRows} />
    <MiniEvidenceList title="Quality statistics" rows={qualityRows} />
    <MiniEvidenceList title="Severity distribution" rows={["critical","high","medium","low"].map((key)=>[key,severityCounts[key]||0])} />
    <MiniEvidenceList title="Reproducibility evidence" rows={[
      ["Fingerprint", shortHash(version?.fingerprint?.combined_fingerprint)||"Not Available"],
      ["Configuration", shortHash(version?.configuration?.configuration_hash)||"Not Available"],
      ["Target", version?.configuration?.target_column||"Not Available"],
      ["Validation", version?.configuration?.validation_strategy||"Not Available"],
    ]} />
    <MiniEvidenceList title="Variant-generator hints" rows={generatorHints.length?generatorHints.slice(0,6).map((item)=>[item.component?.replaceAll("_"," ")||item.family, `${metricValue(item.score)} | ${item.recommended_action}`]):[["Status","No score-triggered variant hint available"]]} />
  </div>;
}

function componentRows(components = {}) {
  const rows=Object.entries(components).filter(([,value])=>Number(value)>0).sort((a,b)=>Number(b[1])-Number(a[1])).map(([key,value])=>[key.replaceAll("_"," "), metricValue(value)]);
  return rows.length?rows:[["Status","No component risk raised"]];
}

function DiagnosisFindingColumns(finding) {
  const evidence=finding?.evidence||{};
  const columns=[];
  if(evidence.columns)for(const item of evidence.columns)columns.push(typeof item==="object"?item.column:String(item));
  if(evidence.target_column)columns.push(evidence.target_column);
  if(evidence.correlations)for(const item of evidence.correlations)columns.push(item.left,item.right);
  if(evidence.pairs)for(const item of evidence.pairs)columns.push(item.left,item.right);
  return [...new Set(columns.filter(Boolean))];
}

function DiagnosisLLMReport({ report, status }) {
  return <Card className="diagnosis-llm-report">
    <div className="version-page-head">
      <div><p className="eyebrow">Stored diagnosis interpretation</p><h2>LLM-generated evidence explanation</h2></div>
      {report?.prompt_version&&<Badge>{report.prompt_version}</Badge>}
    </div>
    {status&&<Notice error={status.includes("failed")||status.includes("Could not")}>{status}</Notice>}
    {!report&&!status?<Empty>Diagnosis interpretation will be generated after a version is selected.</Empty>:null}
    {report?.content&&<LLMFormattedContent content={report.content} />}
  </Card>;
}

function riskTone(score) {
  const value = Number(score);
  if (!Number.isFinite(value)) return "neutral";
  if (value >= 70) return "critical";
  if (value >= 45) return "high";
  if (value >= 20) return "medium";
  return "low";
}

function compactPct(value) {
  return value === null || value === undefined ? "N/A" : pct(value);
}

function methodLabel(version) {
  return formatGenerationMethod(version?.generation_method || "manual");
}

function DetailDrawer({ detail, onClose }) {
  if (!detail) return null;
  const hasRaw=detail.raw !== undefined;
  return <section className="diagnosis-drawer-backdrop diagnosis-detail-layer" role="region" aria-labelledby="diagnosis-detail-title">
    <article className="diagnosis-drawer diagnosis-detail-workspace">
      <div className="diagnosis-drawer-head">
        <div>
          <p className="eyebrow">{detail.eyebrow || "Evidence detail"}</p>
          <h2 id="diagnosis-detail-title">{detail.title}</h2>
          {detail.subtitle && <p className="muted">{detail.subtitle}</p>}
        </div>
        <Button variant="secondary compact" onClick={onClose}>Close</Button>
      </div>
      <nav className="diagnosis-detail-nav" aria-label="Detail sections">
        <a href="#diagnosis-detail-summary">Summary</a>
        <a href="#diagnosis-detail-evidence">Evidence</a>
        {hasRaw&&<a href="#diagnosis-detail-advanced">Advanced</a>}
      </nav>
      <div id="diagnosis-detail-summary" className="diagnosis-detail-summary">
        <strong>{detail.title}</strong>
        <span>{detail.subtitle || detail.eyebrow || "Persisted evidence detail"}</span>
      </div>
      <div id="diagnosis-detail-evidence" className="diagnosis-drawer-body">{detail.body}</div>
      {hasRaw && <details id="diagnosis-detail-advanced" className="debug-disclosure">
        <summary>Advanced evidence</summary>
        <pre className="pre">{JSON.stringify(detail.raw, null, 2)}</pre>
      </details>}
    </article>
  </section>;
}

function SmartCard({ icon: Icon, label, value, note, tone = "neutral", onClick, children }) {
  const Tag=onClick?"button":"article";
  return <Tag type={onClick?"button":undefined} className={`smart-card ${tone} ${onClick?"interactive":""}`} onClick={onClick}>
    <div className="smart-card-top">
      <span>{Icon && <Icon size={15} />}</span>
      <strong>{label}</strong>
    </div>
    <div className="smart-card-value">{value ?? "N/A"}</div>
    {note && <p>{note}</p>}
    {children}
  </Tag>;
}

function RiskGauge({ value, label, tone = "medium", onClick }) {
  const score = Number(value);
  const safe = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
  return <button type="button" className={`risk-gauge ${tone}`} onClick={onClick} style={{ "--risk-value": `${safe * 3.6}deg` }}>
    <span className="risk-gauge-ring"><strong>{Number.isFinite(score) ? score.toFixed(1) : "N/A"}</strong></span>
    <span>{label}</span>
  </button>;
}

function MiniBar({ label, value, max = 100, tone = "medium", onClick }) {
  const numeric = Number(value);
  const width = Number.isFinite(numeric) ? Math.max(0, Math.min(100, (numeric / Math.max(Number(max) || 1, 1)) * 100)) : 0;
  const Tag = onClick ? "button" : "div";
  return <Tag type={onClick ? "button" : undefined} className={`mini-bar-row ${tone}`} onClick={onClick}>
    <span>{label}</span>
    <div><i style={{ width: `${width}%` }} /></div>
    <strong>{Number.isFinite(numeric) ? metricValue(numeric) : value ?? "N/A"}</strong>
  </Tag>;
}

function ClassDistributionBars({ distribution = {}, onClick }) {
  const entries = Object.entries(distribution || {});
  const total = entries.reduce((sum, [,value])=>sum + Number(value || 0), 0);
  if (!entries.length) return <p className="muted compact-copy">No class distribution evidence.</p>;
  return <div className="class-bars">
    {entries.map(([label, value]) => <MiniBar key={label} label={label} value={Number(value)} max={total || 1} tone="low" onClick={onClick} />)}
  </div>;
}

function SeverityStrip({ findings = [], onClick }) {
  const counts = findings.reduce((acc,item)=>({...acc,[item.severity]:(acc[item.severity]||0)+1}),{});
  return <div className="severity-strip">
    {["critical","high","medium","low"].map((key)=><button type="button" key={key} className={`severity-chip ${key}`} onClick={onClick}><strong>{counts[key]||0}</strong><span>{key}</span></button>)}
  </div>;
}

function RiskHeatmap({ findings = [], contract, onInspect }) {
  const impacts = contract?.column_impact || [];
  if (impacts.length) return <div className="risk-heatmap">
    {impacts.map((row)=><button type="button" key={row.column} className="risk-heatmap-row" onClick={()=>onInspect({title: row.column, eyebrow: "Risk map", raw: row, body: <MiniEvidenceList title="Column impact" rows={[
      ["Role", row.role], ["Type", row.data_type], ["Risks", row.risk_families?.join(", ") || "None"], ["Recommended ops", row.recommended_operation_count]
    ]} />})}>
      <strong>{row.column}</strong>
      <span>{row.role}</span>
      <div>{["missingness","duplicates","outliers","correlation","leakage","imbalance"].map((risk)=><i key={risk} className={row.risk_families?.some((item)=>String(item).toLowerCase().includes(risk)) ? "active" : ""} title={risk} />)}</div>
    </button>)}
  </div>;
  const affected = [...new Set(findings.flatMap((finding)=>DiagnosisFindingColumns(finding)))];
  if (!affected.length) return <Empty>No feature-level risk map is available.</Empty>;
  return <div className="risk-heatmap">
    {affected.map((column)=><button type="button" key={column} className="risk-heatmap-row" onClick={()=>onInspect({title: column, eyebrow: "Risk map", body: <MiniEvidenceList title="Related findings" rows={findings.filter((finding)=>DiagnosisFindingColumns(finding).includes(column)).map((finding)=>[finding.code, finding.severity])} />})}>
      <strong>{column}</strong>
      <span>feature</span>
      <div>{findings.map((finding)=><i key={finding.code} className={DiagnosisFindingColumns(finding).includes(column) ? "active" : ""} title={finding.code} />)}</div>
    </button>)}
  </div>;
}

function RiskMapTable({ rows = [], onOpen }) {
  const [sortKey,setSortKey]=useState("column");
  const [sortDir,setSortDir]=useState("asc");
  if(!rows.length)return <Empty>No feature-level risk map is available.</Empty>;
  const sort=(key)=>{
    if(sortKey===key)setSortDir((dir)=>dir==="asc"?"desc":"asc");
    else{setSortKey(key);setSortDir("asc");}
  };
  const sorted=[...rows].sort((a,b)=>{
    const left=sortKey==="riskCount"?(a.risks?.length||0):(a[sortKey]||"");
    const right=sortKey==="riskCount"?(b.risks?.length||0):(b[sortKey]||"");
    const result=String(left).localeCompare(String(right),undefined,{numeric:true});
    return sortDir==="asc"?result:-result;
  });
  return <div className="table-wrap risk-map-table"><table><thead><tr>
    {[["column","Feature"],["role","Role"],["riskCount","Risk count"],["risks","Risks"]].map(([key,label])=><th key={key} onClick={()=>sort(key)}><span>{label}{sortKey===key?` ${sortDir==="asc"?"up":"down"}`:""}</span></th>)}
  </tr></thead><tbody>{sorted.map((row,index)=><tr key={`${row.column}-${index}`} tabIndex={0} onClick={()=>onOpen(row)} onKeyDown={(event)=>event.key==="Enter"&&onOpen(row)}>
    <td>{row.column}</td><td>{row.role}</td><td>{row.familyKeys?.length||row.risks?.length||0}</td><td>{(row.familyKeys||[]).map(riskFamilyLabel).join(", ")||row.risks?.join(", ")||"None"}</td>
  </tr>)}</tbody></table></div>;
}

function diagnosisVersionInfo(item, activeVersionId = null, transientStatus = null) {
  const active=String(activeVersionId||"")===String(item.id);
  const shownStatus=active&&transientStatus?transientStatus:item.diagnosis_status||"Not Diagnosed";
  return {
    shownStatus,
    tone:shownStatus==="Diagnosed"?"success":shownStatus==="Recompute Available"||shownStatus==="Running"?"warning":shownStatus==="Failed"?"critical":"neutral",
    label:`V${item.version_number} - ${formatGenerationMethod(item.generation_method)} - ${shownStatus} - MLRS ${displayMetric(item.diagnosis?.mlrs_score, "N/A")} - LRS ${displayMetric(item.diagnosis?.lrs_score, "N/A")}`
  };
}

export function DiagnosisPanel({ study, datasets = [], version, profile, diagnosis, initialContract = null, versionStatus = "", onVersion, onOpenVariants }) {
  const [contract,setContract]=useState(initialContract);
  const [status,setStatus]=useState("");
  const [diagnosisReport,setDiagnosisReport]=useState(null);
  const [diagnosisReportStatus,setDiagnosisReportStatus]=useState("");
  const [selectedOptions,setSelectedOptions]=useState([]);
  const [detail,setDetail]=useState(null);
  const [running,setRunning]=useState(false);
  const [riskFilter,setRiskFilter]=useState("all");
  const [mapMode,setMapMode]=useState("visual");
  const datasetsWithVersions=datasets.filter((dataset)=>dataset.versions?.length);
  const [selectedDatasetId,setSelectedDatasetId]=useState(version?.dataset_id?String(version.dataset_id):String(datasetsWithVersions[0]?.id||""));
  const activeDataset=datasetsWithVersions.find((dataset)=>String(dataset.id)===String(selectedDatasetId))||datasetsWithVersions[0];
  const versionOptions=(activeDataset?.versions||[]).slice().sort((a,b)=>a.version_number-b.version_number);
  const selectedVersionId=version&&String(version.dataset_id)===String(activeDataset?.id)?String(version.id):"";
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!version?.id||!diagnosis){setContract(null);return;}
      if(initialContract?.header?.version_id===version.id){setContract(initialContract);setSelectedOptions(initialContract.intervention_options.map((item)=>item.id));setStatus("");return;}
      setStatus("Loading diagnosis contract...");
      try{
        const result=await datasetApi.diagnosisContract(version.id);
        if(active){setContract(result);setSelectedOptions(result.intervention_options.map((item)=>item.id));setStatus("");}
      }catch(err){
        if(active){setContract(null);setStatus(err.response?.data?.detail||"Could not load diagnosis contract.");}
      }
    };
    load();
    return()=>{active=false;};
  },[version?.id,diagnosis?.id,initialContract?.header?.version_id]);
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!version?.id||!diagnosis?.id){setDiagnosisReport(null);setDiagnosisReportStatus("");return;}
      setDiagnosisReportStatus("Preparing stored diagnosis interpretation...");
      try{
        const result=await aiApi.diagnosisInterpretation(study.id,version.id);
        if(active){setDiagnosisReport(result);setDiagnosisReportStatus("");}
      }catch(err){
        if(active){setDiagnosisReport(null);setDiagnosisReportStatus(aiFallbackMessage());}
      }
    };
    load();
    return()=>{active=false;};
  },[study.id,version?.id,diagnosis?.id]);
  useEffect(()=>{
    if(version?.dataset_id){
      setSelectedDatasetId(String(version.dataset_id));
    }else if(!selectedDatasetId&&datasetsWithVersions[0]){
      setSelectedDatasetId(String(datasetsWithVersions[0].id));
    }
  },[version?.dataset_id,selectedDatasetId,datasetsWithVersions.length]);

  const selectorStatus=running?"Running":status.includes("failed")?"Failed":null;
  const runDiagnosis=async(recompute=false)=>{
    if(!version?.id)return;
    setRunning(true);
    setStatus(recompute?"Recomputing diagnosis...":"Running diagnosis...");
    try{
      await datasetApi.runDiagnosis(version.id,recompute);
      await onVersion(version.id);
      setStatus(recompute?"Diagnosis recomputed.":"Diagnosis complete.");
    }catch(err){
      setStatus(err.response?.data?.detail||"Diagnosis run failed.");
    }finally{
      setRunning(false);
    }
  };

  const chooseDataset=(event)=>setSelectedDatasetId(event.target.value);
  const chooseVersion=async(event)=>{
    const id=event.target.value;
    if(!id)return;
    setStatus("Loading selected diagnosis version...");
    try{
      await onVersion(id);
      setStatus("");
    }catch(err){
      setStatus(err.response?.data?.detail||"Could not load selected diagnosis version.");
    }
  };
  const versionStatusList=!!versionOptions.length&&<div className="diagnosis-version-status-list">
    {versionOptions.map((item)=>{
      const info=diagnosisVersionInfo(item, version?.id, selectorStatus);
      return <button type="button" key={item.id} className={String(version?.id||"")===String(item.id)?"active":""} onClick={()=>onVersion(item.id)}>
        <strong>V{item.version_number}</strong>
        <span>{formatGenerationMethod(item.generation_method)}</span>
        <Badge tone={info.tone}>{info.shownStatus}</Badge>
        <em>MLRS {displayMetric(item.diagnosis?.mlrs_score, "N/A")} - LRS {displayMetric(item.diagnosis?.lrs_score, "N/A")} - {item.row_count ?? "N/A"} rows</em>
      </button>;
    })}
  </div>;

  if(!version)return <div className="diagnosis-console">
    <div className="diagnosis-context-bar">
      <Field label="Dataset"><select value={activeDataset?.id||""} onChange={chooseDataset}>{datasetsWithVersions.map((dataset)=><option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></Field>
      <Field label="Version"><select value="" onChange={chooseVersion}><option value="">Select version</option>{versionOptions.map((item)=><option key={item.id} value={item.id}>{diagnosisVersionInfo(item).label}</option>)}</select></Field>
      <span className="context-kind">{versionOptions.length?`${versionOptions.length} versions`:"No versions"}</span>
      <Badge tone="neutral">Not Diagnosed</Badge>
    </div>
    {versionStatusList}
    <Empty>{datasetsWithVersions.length?"Select a dataset version to inspect diagnosis evidence.":"No dataset versions are available for diagnosis."}</Empty>
  </div>;

  const summary=profile?.report?.summary||{};
  const columns=profile?.report?.columns||[];
  const task=profile?.report?.task_profile||{};
  const highCorrelations=profile?.report?.high_correlations||[];
  const missingColumns=columns.filter((row)=>Number(row.missing_count)>0).sort((a,b)=>Number(b.missing_ratio)-Number(a.missing_ratio));
  const outlierColumns=columns.filter((row)=>Number(row.outlier_count)>0).sort((a,b)=>Number(b.outlier_ratio)-Number(a.outlier_ratio));
  const lowInfoColumns=columns.filter((row)=>Number(row.unique_count)<=1||Number(row.unique_ratio)<=0.01);
  const semantic=version.semantic_diff;
  const variantRecord=version.variant_record;
  const findings=diagnosis?.findings||[];
  const filteredFindings=riskFilter==="all"?findings:findings.filter((item)=>item.severity===riskFilter);
  const interventions=contract?.intervention_options||[];
  const selected=interventions.filter((item)=>selectedOptions.includes(item.id));
  const selectedOps=selected.flatMap((item)=>item.operations||[]);
  const scoreBreakdown=diagnosis?.score_breakdown||{};
  const mlrsComponents=scoreBreakdown.mlrs_components||diagnosis?.mlrs_components||{};
  const lrsComponents=scoreBreakdown.lrs_components||diagnosis?.lrs_components||{};
  const statusLabel=selectorStatus||version.diagnosis_status||(diagnosis?"Diagnosed":"Not Diagnosed");
  const versionKind=variantRecord?"Variant":version.parent_version_id?"Revision":"Baseline";
  const exportReport=async()=>{
    if(!diagnosis)return;
    setStatus("Preparing diagnosis report...");
    try{downloadBlob(await datasetApi.diagnosisReport(version.id),`fedrepro-diagnosis-v${version.version_number}-report.docx`);setStatus("Diagnosis report exported.");}
    catch(err){setStatus(err.response?.data?.detail||"Could not export diagnosis report.");}
  };
  const exportContract=()=>contract&&downloadBlob(new Blob([JSON.stringify({...contract,selected_option_ids:selectedOptions},null,2)],{type:"application/json"}),`fedrepro-diagnosis-v${version.version_number}-contract.json`);
  const toggleOption=(id)=>setSelectedOptions((items)=>items.includes(id)?items.filter((item)=>item!==id):[...items,id]);
  const qualityTabs=<div className="diagnosis-detail-tabs">
    <details open><summary>Overview</summary><MiniEvidenceList title="Profile overview" rows={[["Rows",summary.row_count??version.row_count],["Columns",summary.column_count??version.column_count],["Numeric features",summary.numeric_columns??"N/A"],["Categorical features",summary.categorical_columns??"N/A"],["Low-information features",lowInfoColumns.length]]} /></details>
    <details open><summary>Missingness</summary>{missingColumns.length?missingColumns.slice(0,16).map((row)=><MiniBar key={row.name} label={row.name} value={Number(row.missing_ratio)*100} max={100} />):<Notice>No missing values detected.</Notice>}</details>
    <details><summary>Duplicates</summary><MiniEvidenceList title="Duplicate evidence" rows={[["Rows",summary.duplicate_rows??"N/A"],["Ratio",compactPct(summary.duplicate_ratio)]]} /></details>
    <details><summary>Outliers</summary>{outlierColumns.length?outlierColumns.slice(0,16).map((row)=><MiniBar key={row.name} label={row.name} value={Number(row.outlier_ratio)*100} max={100} />):<Notice>No outlier evidence detected.</Notice>}</details>
    <details><summary>Correlation</summary>{highCorrelations.length?highCorrelations.slice(0,16).map((row)=><MiniBar key={`${row.left}-${row.right}`} label={`${row.left} / ${row.right}`} value={Math.abs(Number(row.correlation))*100} max={100} />):<Notice>No strong correlation pairs crossed the reporting threshold.</Notice>}</details>
    <details><summary>Distribution</summary><ClassDistributionBars distribution={task.class_distribution} /></details>
    <details><summary>Target</summary><MiniEvidenceList title="Target" rows={[["Column",task.target_column||version.configuration?.target_column||"N/A"],["Minority class",task.minority_class||"N/A"],["Imbalance ratio",task.imbalance_ratio?metricValue(task.imbalance_ratio):"N/A"]]} /></details>
  </div>;
  const relatedForFinding=(finding)=>interventions.find((item)=>item.source_findings?.includes(finding.code)||item.triggered_by?.includes(finding.code));
  const evidenceRows=(finding)=>Object.entries(finding?.evidence||{}).map(([key,value])=>[key.replaceAll("_"," "), typeof value==="object"?JSON.stringify(value).slice(0,160):String(value)]);
  const detailAreaForType=(type)=>({
    quality:"quality",
    metric:"metric",
    derivation:"derivation",
    risk:"risk",
    "risk-map":"risk-map",
    evidence:"evidence",
    intervention:"planner",
    operation:"planner",
    decision:"planner",
    decisions:"planner",
    ai:"ai",
    plan:"plan"
  })[type]||"context";
  const setPlacedDetail=(type,next)=>setDetail({...next,area:detailAreaForType(type)});
  const openDetail=(type, payload={})=>{
    const detailBody=(rows, extra=null)=><div className="stack"><MiniEvidenceList title="Evidence" rows={rows} />{extra}</div>;
    if(type==="quality"){
      const key=payload.key;
      const bodies={
        rows:detailBody([["Rows",summary.row_count??version.row_count],["Profile report",profile?.id||"N/A"],["Version",`V${version.version_number}`],["Immutable version id",version.id]]),
        columns:detailBody([["Columns",summary.column_count??version.column_count],["Numeric features",summary.numeric_columns??"N/A"],["Categorical features",summary.categorical_columns??"N/A"],["Configured target",version.configuration?.target_column||"N/A"]]),
        missing:detailBody([["Missing cells",summary.missing_cells??0],["Missing ratio",compactPct(summary.missing_ratio)],["Affected columns",missingColumns.length]],<div className="stack">{missingColumns.length?missingColumns.slice(0,16).map((row)=><MiniBar key={row.name} label={row.name} value={Number(row.missing_ratio)*100} max={100} tone="medium" />):<Notice>No missing-value columns in persisted profile evidence.</Notice>}</div>),
        missingRatio:detailBody([["Missing ratio",compactPct(summary.missing_ratio)],["Missing cells",summary.missing_cells??0],["Profiler",profile?.profiler_version||"N/A"]],<MiniBar label="missing ratio" value={Number(summary.missing_ratio||0)*100} max={100} tone={summary.missing_ratio>.05?"medium":"low"} />),
        duplicates:detailBody([["Duplicate rows",summary.duplicate_rows??0],["Duplicate ratio",compactPct(summary.duplicate_ratio)],["Rows",summary.row_count??version.row_count]],<MiniBar label="duplicate ratio" value={Number(summary.duplicate_ratio||0)*100} max={100} tone={summary.duplicate_ratio>.01?"medium":"low"} />),
        numeric:detailBody([["Numeric features",summary.numeric_columns??"N/A"],["Total columns",summary.column_count??version.column_count],["Outlier columns",outlierColumns.length]]),
        categorical:detailBody([["Categorical features",summary.categorical_columns??"N/A"],["Total columns",summary.column_count??version.column_count],["Target",task.target_column||version.configuration?.target_column||"N/A"]]),
        outliers:detailBody([["Affected columns",outlierColumns.length],["Top column",outlierColumns[0]?.name||"N/A"]],<div className="stack">{outlierColumns.length?outlierColumns.slice(0,16).map((row)=><MiniBar key={row.name} label={row.name} value={Number(row.outlier_ratio)*100} max={100} tone="medium" />):<Notice>No outlier evidence detected by the persisted profile.</Notice>}</div>),
        correlation:detailBody([["High-correlation pairs",highCorrelations.length],["Top pair",highCorrelations[0]?`${highCorrelations[0].left} / ${highCorrelations[0].right}`:"N/A"]],<div className="stack">{highCorrelations.length?highCorrelations.slice(0,16).map((row)=><MiniBar key={`${row.left}-${row.right}`} label={`${row.left} / ${row.right}`} value={Math.abs(Number(row.correlation))*100} max={100} tone="medium" />):<Notice>No strong correlation evidence crossed the reporting threshold.</Notice>}</div>),
        lowInfo:detailBody([["Low-information features",lowInfoColumns.length],["Examples",lowInfoColumns.slice(0,5).map((row)=>row.name).join(", ")||"N/A"]],<MiniEvidenceList title="Features" rows={lowInfoColumns.length?lowInfoColumns.map((row)=>[row.name, `${row.unique_count} unique, ${compactPct(row.unique_ratio)}`]):[["Status","No constant or low-information feature evidence available"]]} />),
        target:detailBody([["Target",task.target_column||version.configuration?.target_column||"N/A"],["Minority class",task.minority_class||"N/A"],["Imbalance ratio",task.imbalance_ratio?metricValue(task.imbalance_ratio):"N/A"]],<ClassDistributionBars distribution={task.class_distribution} />),
        all:qualityTabs
      };
      setPlacedDetail(type,{eyebrow:"Dataset Quality",title:payload.title||"Quality evidence",subtitle:"Persisted profile evidence for this immutable version.",body:bodies[key]||qualityTabs,raw:profile?.report});
      return;
    }
    if(type==="metric"){
      const metric=payload.metric;
      const definitions={
        MLRS:["Machine learning readiness risk score","Lower is better",displayMetric(diagnosis?.mlrs_score,"N/A"),mlrsComponents,scoreBreakdown],
        LRS:["Leakage risk score","Lower is better",displayMetric(diagnosis?.lrs_score,"N/A"),lrsComponents,scoreBreakdown?.leakage_evidence||lrsComponents],
        SCM:["Semantic comparability metric","Higher means larger semantic change",semantic?displayMetric(semantic.scm_score):"N/A",{},semantic],
        DSI:["Dataset shift indicator","Higher means greater distribution shift",semantic?displayMetric(semantic.dsi_score):"N/A",{},semantic],
        VRS:["Variant readiness score","Higher is better",variantRecord?.vrs_score!=null?displayMetric(variantRecord.vrs_score):"N/A",{},variantRecord]
      };
      const [definition,direction,value,components,raw]=definitions[metric]||[];
      const componentEntries=Object.entries(components||{});
      setPlacedDetail(type,{eyebrow:"Diagnosis Metrics",title:metric,subtitle:definition,body:<div className="stack"><MiniEvidenceList title="Metric interpretation" rows={[["Current value",value],["Direction",direction],["Status",payload.state||"Available"],["Ruleset",diagnosis?.ruleset_version||semantic?.ruleset_version||"N/A"],["Version",`V${version.version_number}`],["Parent",version.parent_version_id?`V${version.parent_version_id}`:"Baseline / not applicable"]]} />{componentEntries.length?<div className="stack">{componentEntries.map(([key,value])=><MiniBar key={key} label={key.replaceAll("_"," ")} value={value} max={metric==="LRS"?35:25} tone={riskTone(value)} />)}</div>:<Notice>No component breakdown is stored for this metric.</Notice>}<MiniEvidenceList title="Related findings" rows={findings.filter((finding)=>metric==="LRS"?String(finding.code).includes("LEAK"):true).slice(0,6).map((finding)=>[finding.code,finding.issue])} /></div>,raw});
      return;
    }
    if(type==="risk"||type==="derivation"){
      const finding=payload.finding;
      const related=payload.related||relatedForFinding(finding);
      const cols=DiagnosisFindingColumns(finding);
      setPlacedDetail(type,{eyebrow:type==="derivation"?"Evidence -> Risk -> Action":finding.code,title:finding.issue,subtitle:finding.risk,body:<div className="stack"><MiniEvidenceList title="Finding" rows={[["Severity",finding.severity],["Affected columns",cols.join(", ")||"Dataset-level"],["Recommendation",finding.recommendation],["Related metric",String(finding.code).includes("LEAK")?"LRS":"MLRS"],["Related intervention",related?.title||"N/A"]]} />{!!evidenceRows(finding).length&&<MiniEvidenceList title="Threshold evidence" rows={evidenceRows(finding)} />}</div>,raw:{finding,related}});
      return;
    }
    if(type==="risk-map"){
      const row=payload.row;
      setPlacedDetail(type,{eyebrow:"Feature x Risk Map",title:row.column,subtitle:"Feature-level risk family evidence derived from persisted diagnosis content.",body:<RiskMapDetail row={row} families={visibleRiskFamilies} findings={findings} version={version} />,raw:row.raw||row});
      return;
    }
    if(type==="intervention"){
      const option=payload.option;
      setPlacedDetail(type,{eyebrow:"Intervention Planner",title:option.title,subtitle:option.objective,body:<div className="stack"><MiniEvidenceList title="Intervention" rows={[["Status",option.status],["Severity",option.severity],["Triggered by",option.triggered_by?.join(", ")||option.source_findings?.join(", ")||"N/A"],["Affected columns",option.affected_columns?.join(", ")||"Dataset-level"],["Expected changes",option.expected_changes?.join("; ")||"N/A"],["Risks introduced",option.risks_introduced?.join("; ")||"N/A"]]} /><MiniEvidenceList title="Ordered operations" rows={(option.operations||[]).map((op,index)=>[`${index+1}. ${op.operation?.replaceAll("_"," ")}`,op.purpose||op.columns?.join(", ")||"Operation"])} /><MetricImpactPreview impact={option.metric_impact} /></div>,raw:option});
      return;
    }
    if(type==="operation"){
      const {option,op,index}=payload;
      setPlacedDetail(type,{eyebrow:"Intervention Operation",title:op.operation?.replaceAll("_"," ")||`Operation ${index+1}`,subtitle:option.title,body:detailBody([["Step",index+1],["Purpose",op.purpose||"N/A"],["Columns",op.columns?.join(", ")||option.affected_columns?.join(", ")||"Dataset-level"],["Intervention",option.title],["Triggered by",option.triggered_by?.join(", ")||option.source_findings?.join(", ")||"N/A"]]),raw:{option,operation:op}});
      return;
    }
    if(type==="decision"){
      const decision=payload.decision;
      setPlacedDetail(type,{eyebrow:"Human Decision",title:decision.question,subtitle:decision.recommended_default,body:<div className="stack"><MiniEvidenceList title="Decision evidence" rows={[["Finding",decision.finding_code],["Scope",decision.affected_columns?.join(", ")||"Dataset-level"],["Accepting",decision.consequence_accept],["Rejecting",decision.consequence_reject]]} /><div className="row"><Button variant="secondary compact">Accept</Button><Button variant="ghost compact">Reject</Button></div></div>,raw:decision});
      return;
    }
    if(type==="decisions"){
      const decisions=contract?.human_decisions||[];
      setPlacedDetail(type,{eyebrow:"Human Decisions",title:`Human decisions required: ${decisions.length}`,subtitle:"Review choices before generating variants.",body:decisions.length?<div className="decision-drawer-list">{decisions.map((decision,index)=><button type="button" key={`${decision.finding_code}-${index}`} onClick={()=>openDetail("decision",{decision})}><strong>{decision.question}</strong><span>{decision.recommended_default}</span><small>{decision.affected_columns?.join(", ")||"Dataset-level"}</small></button>)}</div>:<Notice>No human approvals are required by the current plan.</Notice>,raw:decisions});
      return;
    }
    if(type==="plan"){
      const rows={
        selected:[["Selected options",selected.length],["Options",selected.map((item)=>item.title).join(", ")||"None"]],
        operations:[["Total operations",selectedOps.length],["Operations",selectedOps.map((op)=>op.operation?.replaceAll("_"," ")).join(", ")||"None"]],
        columns:[["Affected columns",[...new Set(selectedOps.flatMap((item)=>item.columns||[]))].join(", ")||"Dataset-level"],["Selected interventions",selected.length]],
        baseline:[["Baseline version",`V${version.version_number}`],["Generation method",methodLabel(version)],["Parent",version.parent_version_id?`V${version.parent_version_id}`:"Baseline"]],
        metrics:[["Recommended metrics",contract?.experiment_handoff?.recommended_metrics?.join(", ")||"Primary metric"],["Primary metric",version.configuration?.primary_metric||"N/A"]],
        constraints:[["Human decisions remaining",contract?.human_decisions?.length||0],["Required baseline",contract?.experiment_handoff?.required_baseline||`V${version.version_number}`]]
      };
      setPlacedDetail(type,{eyebrow:"Variant Plan",title:payload.title||"Plan detail",subtitle:"Generator-ready selections derived from persisted intervention evidence.",body:detailBody(rows[payload.key]||rows.selected),raw:{contract,selectedOptions,selected}});
      return;
    }
    if(type==="evidence"){
      const bodies={
        inspector:<EvidenceInspector version={version} profile={profile} diagnosis={diagnosis} semantic={semantic} variantRecord={variantRecord} contract={contract} />,
        fingerprint:detailBody([["File hash",shortHash(version.fingerprint?.file_hash)||"N/A"],["Schema hash",shortHash(version.fingerprint?.schema_hash)||"N/A"],["Metadata hash",shortHash(version.fingerprint?.metadata_hash)||"N/A"],["Combined",shortHash(version.fingerprint?.combined_fingerprint)||"N/A"],["Algorithm",version.fingerprint?.algorithm_version||"N/A"]]),
        lineage:detailBody([["Parent",version.parent_version_id?`V${version.parent_version_id}`:"Baseline"],["Current",`V${version.version_number}`],["Generation method",methodLabel(version)],["Notes",version.version_notes||"N/A"]]),
        stability:detailBody([["SCM",semantic?displayMetric(semantic.scm_score):"N/A"],["DSI",semantic?displayMetric(semantic.dsi_score):"N/A"],["Schema added",semantic?.report?.columns_added?.join(", ")||"N/A"],["Schema removed",semantic?.report?.columns_removed?.join(", ")||"N/A"],["Missingness delta",semantic?.report?.missing_ratio_change!=null?signedPct(semantic.report.missing_ratio_change):"N/A"],["Duplicate delta",semantic?.report?.duplicate_rows?.delta??"N/A"]]),
        reproducibility:detailBody([["Fingerprint",shortHash(version.fingerprint?.combined_fingerprint)||"N/A"],["Configuration hash",shortHash(version.configuration?.configuration_hash)||"N/A"],["Profile report",profile?.id||version.profile_report_id||"N/A"],["Diagnosis report",diagnosis?.id||"N/A"],["Ruleset",diagnosis?.ruleset_version||"N/A"],["Profiler",profile?.profiler_version||"N/A"],["Generation method",methodLabel(version)]]),
        contract:<DiagnosisEvidenceSummary version={version} profile={profile} diagnosis={diagnosis} contract={contract} />
      };
      setPlacedDetail(type,{eyebrow:"Evidence Inspector",title:payload.title||"Reproducible evidence",subtitle:"Stored deterministic evidence for audit and replay.",body:bodies[payload.key]||bodies.inspector,raw:{version,profile,diagnosis,semantic,variantRecord,contract}});
      return;
    }
    if(type==="ai"){
      setPlacedDetail(type,{eyebrow:"AI Explanation",title:"Persisted evidence explanation",subtitle:diagnosisReportStatus||(!diagnosis?"Run diagnosis before AI explanation.":!diagnosisReport?"No stored AI interpretation exists for this version.":"Generated from stored deterministic evidence."),body:<DiagnosisLLMReport report={diagnosisReport} status={diagnosisReportStatus||(!diagnosis?"Run diagnosis first before an evidence explanation can be generated.":!diagnosisReport?"No stored AI interpretation exists for this version.":"")} />,raw:diagnosisReport});
    }
  };
  const riskRowMap=new Map();
  (contract?.column_impact||[]).forEach((row)=>{
    const column=row.column||"Dataset-level";
    riskRowMap.set(column,{
      column,
      role:row.role||"feature",
      dataType:row.data_type,
      risks:row.risk_families||[],
      familyKeys:[...new Set((row.risk_families||[]).map(normalizeRiskFamily).filter(Boolean))],
      recommendedOperationCount:row.recommended_operation_count,
      raw:row
    });
  });
  findings.forEach((finding)=>{
    const findingFamilies=riskFamiliesForFinding(finding);
    const columnsForFinding=DiagnosisFindingColumns(finding);
    (columnsForFinding.length?columnsForFinding:["Dataset-level"]).forEach((column)=>{
      const existing=riskRowMap.get(column)||{column,role:column==="Dataset-level"?"dataset":"feature",risks:[],familyKeys:[],raw:null};
      riskRowMap.set(column,{
        ...existing,
        risks:[...new Set([...(existing.risks||[]), finding.code, ...findingFamilies])],
        familyKeys:[...new Set([...(existing.familyKeys||[]), ...findingFamilies])]
      });
    });
  });
  const heatRows=[...riskRowMap.values()].sort((a,b)=>(b.familyKeys?.length||0)-(a.familyKeys?.length||0)||String(a.column).localeCompare(String(b.column)));
  const activeRiskKeys=[...new Set(heatRows.flatMap((row)=>row.familyKeys||[]))];
  const visibleRiskFamilies=(activeRiskKeys.length?activeRiskKeys:RISK_FAMILY_DEFINITIONS.slice(0,6).map((family)=>family.key)).map((key)=>({key,label:riskFamilyLabel(key)}));
  const renderDetail=(area)=><DetailDrawer detail={detail?.area===area?detail:null} onClose={()=>setDetail(null)} />;

  return <div className="diagnosis-console">
    <div className="diagnosis-context-bar">
      <Field label="Dataset"><select value={activeDataset?.id||""} onChange={chooseDataset}>{datasetsWithVersions.map((dataset)=><option key={dataset.id} value={dataset.id}>{dataset.name}</option>)}</select></Field>
      <Field label="Version"><select value={selectedVersionId} onChange={chooseVersion}><option value="">Select version</option>{versionOptions.map((item)=><option key={item.id} value={item.id}>{diagnosisVersionInfo(item, version.id, selectorStatus).label}</option>)}</select></Field>
      <span className="context-kind">{versionKind}</span>
      <span className="context-kind">{version.configuration?.target_column||"No target"}</span>
      <Badge tone={statusLabel==="Diagnosed"?"success":statusLabel==="Recompute Available"||statusLabel==="Running"?"warning":statusLabel==="Failed"?"critical":"neutral"}>{statusLabel}</Badge>
      <span className="context-kind">{diagnosis?.ruleset_version||"No ruleset"}</span>
      <span className="context-kind">{methodLabel(version)}</span>
      {!diagnosis?<Button loading={running} onClick={()=>runDiagnosis(false)}><ShieldCheck size={14}/>Run Diagnosis</Button>:<Button variant="secondary" loading={running} onClick={()=>runDiagnosis(true)}><ShieldCheck size={14}/>Recompute</Button>}
      <Button variant="secondary" disabled={!diagnosis} onClick={exportReport}><FileCheck2 size={14}/>Export</Button>
      <Button variant="secondary" onClick={()=>openDetail("evidence",{key:"inspector",title:"Evidence Inspector"})}><Eye size={14}/>Evidence Details</Button>
    </div>
    {versionStatusList}
    {(status||versionStatus)&&<Notice error={(status||versionStatus).includes("Could not")||(status||versionStatus).includes("failed")}>{status||versionStatus}</Notice>}

    {!diagnosis?<Card className="diagnosis-empty-run"><div><p className="eyebrow">Not Diagnosed</p><h2>Persisted diagnosis evidence is missing for V{version.version_number}</h2><p className="muted">Run diagnosis to persist profile, diagnosis, score-breakdown, and non-baseline semantic evidence for this immutable version.</p></div></Card>:<>
      <section className="console-section quality-console">
        <div className="console-section-head"><div><p className="eyebrow">Data Quality Overview</p><h2>Compact profiling evidence</h2></div><Button variant="secondary compact" onClick={()=>openDetail("quality",{key:"all",title:"Quality Details"})}>View Quality Details</Button></div>
        <div className="quality-figure-grid">
          <SmartCard icon={TableProperties} label="Rows" value={summary.row_count??version.row_count} note="immutable version" onClick={()=>openDetail("quality",{key:"rows",title:"Row profile"})} />
          <SmartCard icon={TableProperties} label="Columns" value={summary.column_count??version.column_count} note={`${summary.numeric_columns??"N/A"} num / ${summary.categorical_columns??"N/A"} cat`} onClick={()=>openDetail("quality",{key:"columns",title:"Column profile"})} />
          <SmartCard icon={AlertTriangle} label="Missing Cells" value={summary.missing_cells??0} note={compactPct(summary.missing_ratio)} tone={summary.missing_ratio>.05?"medium":"low"} onClick={()=>openDetail("quality",{key:"missing",title:"Missingness evidence"})}><MiniBar label="cells" value={Number(summary.missing_ratio||0)*100} max={100} /></SmartCard>
          <SmartCard icon={AlertTriangle} label="Missing Ratio" value={compactPct(summary.missing_ratio)} note={`${missingColumns.length} columns affected`} tone={summary.missing_ratio>.05?"medium":"low"} onClick={()=>openDetail("quality",{key:"missingRatio",title:"Missing ratio"})}><MiniBar label="ratio" value={Number(summary.missing_ratio||0)*100} max={100} /></SmartCard>
          <SmartCard icon={Copy} label="Duplicates" value={summary.duplicate_rows??0} note={compactPct(summary.duplicate_ratio)} tone={summary.duplicate_ratio>.01?"medium":"low"} onClick={()=>openDetail("quality",{key:"duplicates",title:"Duplicate evidence"})}><MiniBar label="ratio" value={Number(summary.duplicate_ratio||0)*100} max={100} /></SmartCard>
          <SmartCard icon={Gauge} label="Numeric" value={summary.numeric_columns??"N/A"} note="numeric features" onClick={()=>openDetail("quality",{key:"numeric",title:"Numeric feature evidence"})} />
          <SmartCard icon={Database} label="Categorical" value={summary.categorical_columns??"N/A"} note="categorical features" onClick={()=>openDetail("quality",{key:"categorical",title:"Categorical feature evidence"})} />
          <SmartCard icon={Gauge} label="Outliers" value={outlierColumns.length} note={outlierColumns.length?"columns affected":"clear"} tone={outlierColumns.length?"medium":"low"} onClick={()=>openDetail("quality",{key:"outliers",title:"Outlier evidence"})} />
          <SmartCard icon={GitCompare} label="Correlation" value={highCorrelations.length} note={highCorrelations.length?"high pairs":"clear"} tone={highCorrelations.length?"medium":"low"} onClick={()=>openDetail("quality",{key:"correlation",title:"Correlation evidence"})} />
          <SmartCard icon={ScanSearch} label="Low Info" value={lowInfoColumns.length} note="constant or near-unique" tone={lowInfoColumns.length?"medium":"low"} onClick={()=>openDetail("quality",{key:"lowInfo",title:"Low-information features"})} />
          <SmartCard icon={Target} label="Target" value={task.imbalance_ratio?`${metricValue(task.imbalance_ratio)}x`:"N/A"} note={task.minority_class?`minority ${task.minority_class}`:"not computed"} onClick={()=>openDetail("quality",{key:"target",title:"Target distribution"})}><ClassDistributionBars distribution={task.class_distribution} /></SmartCard>
        </div>
        {renderDetail("quality")}
      </section>

      <section className="metric-strip">
        {[
          ["MLRS",diagnosis.mlrs_score,"Lower is better","readiness risk",riskTone(diagnosis.mlrs_score)],
          ["LRS",diagnosis.lrs_score,"Lower is better","leakage risk",riskTone(diagnosis.lrs_score)],
          ["SCM",semantic?.scm_score,"Higher means larger change",semantic?"computed":"not applicable","neutral"],
          ["DSI",semantic?.dsi_score,"Higher means greater shift",semantic?"computed":"not applicable","neutral"],
          ["VRS",variantRecord?.vrs_score,"Higher is better",variantRecord?"variant readiness":"not applicable",variantRecord?.vrs_score>=80?"low":"neutral"]
        ].map(([label,value,meaning,state,tone])=><button type="button" key={label} className={`metric-strip-card ${tone}`} onClick={()=>openDetail("metric",{metric:label,state})}><span>{label}</span><strong>{value==null?"N/A":metricValue(value)}</strong><em>{meaning}</em><small>{state}</small></button>)}
        {renderDetail("metric")}
      </section>

      <section className="console-section diagnosis-derivation">
        <div className="console-section-head"><div><p className="eyebrow">Diagnosis Visual Summary</p><h2>Quality Evidence -> Risks -> Interventions</h2></div></div>
        <div className="derivation-list">
          {findings.slice(0,5).map((finding)=>{
            const option=relatedForFinding(finding);
            const evidence=Object.entries(finding.evidence||{})[0];
            return <button type="button" key={finding.code} onClick={()=>openDetail("derivation",{finding,related:option})}><span>{evidence?evidence[0].replaceAll("_"," "):"Evidence"}</span><i /> <strong>{finding.issue}</strong><i /> <em>{option?.title||"Review"}</em></button>;
          })}
        </div>
        {renderDetail("derivation")}
      </section>

      <main className="diagnosis-main-grid">
        <div className="diagnosis-primary-stack">
          <section className="console-section">
            <div className="console-section-head"><div><p className="eyebrow">Risk Explorer</p><h2>Findings</h2></div><div className="segmented-filter">{["all","critical","high","medium","low"].map((item)=><button type="button" key={item} className={riskFilter===item?"active":""} onClick={()=>setRiskFilter(item)}>{item}</button>)}</div></div>
            {!filteredFindings.length?<Notice>No findings for this filter.</Notice>:<div className="risk-console-list">{filteredFindings.map((item)=>{
              const cols=DiagnosisFindingColumns(item);
              const related=relatedForFinding(item);
              return <article key={item.code} role="button" tabIndex={0} className={`risk-console-card ${item.severity} interactive`} onClick={()=>openDetail("risk",{finding:item,related})} onKeyDown={(event)=>event.key==="Enter"&&openDetail("risk",{finding:item,related})}><div><Badge tone={item.severity}>{item.severity}</Badge><strong>{item.issue}</strong></div><p>{cols.length?`${cols.length} affected feature${cols.length===1?"":"s"}`:"Dataset-level evidence"}</p><span>{cols.slice(0,3).join(", ")||item.code}</span><footer><Button variant="secondary compact" onClick={(event)=>{event.stopPropagation();openDetail("risk",{finding:item,related});}}>Inspect</Button><Button variant="ghost compact" disabled={!related} onClick={(event)=>{event.stopPropagation();related&&setSelectedOptions((ids)=>ids.includes(related.id)?ids:[...ids,related.id]);}}>Plan Intervention</Button></footer></article>;
            })}</div>}
            {renderDetail("risk")}
          </section>

          <section className="console-section">
            <div className="console-section-head"><div><p className="eyebrow">Feature x Risk Map</p><h2>Risk matrix</h2></div><div className="segmented-filter"><button type="button" className={mapMode==="visual"?"active":""} onClick={()=>setMapMode("visual")}>Visual Map</button><button type="button" className={mapMode==="table"?"active":""} onClick={()=>setMapMode("table")}>Table View</button></div></div>
            {mapMode==="visual"?!heatRows.length?<Empty>No feature-level risk map is available.</Empty>:<div className="feature-risk-card-map">
              {heatRows.map((row)=>{
                const rowFindings=findingsForRiskMapRow(row,findings);
                const activeFamilies=visibleRiskFamilies.filter((family)=>row.familyKeys?.includes(family.key));
                return <article role="button" tabIndex={0} className="risk-map-summary-card" key={row.column} onClick={()=>openDetail("risk-map",{row})} onKeyDown={(event)=>event.key==="Enter"&&openDetail("risk-map",{row})}>
                  <div className="risk-map-summary-head">
                    <div><strong>{row.column}</strong><span>{row.role||"feature"} · {activeFamilies.length} risk {activeFamilies.length===1?"family":"families"} · {rowFindings.length||"no"} direct {rowFindings.length===1?"finding":"findings"}</span></div>
                    {highestSeverity(rowFindings)&&<Badge tone={highestSeverity(rowFindings)}>{highestSeverity(rowFindings)}</Badge>}
                  </div>
                  <div className="risk-map-chip-list">{activeFamilies.map((family)=>{
                  const matched=(row.risks||[]).filter((item)=>normalizeRiskFamily(item)===family.key);
                  const familyFindings=rowFindings.filter((finding)=>riskFamiliesForFinding(finding).includes(family.key));
                  const severity=highestSeverity(familyFindings);
                  return <button type="button" key={family.key} className={`risk-map-chip ${severity||"neutral"}`} aria-label={`${row.column} ${family.label} evidence`} title={matched.join(", ")||familyFindings.map((finding)=>finding.code).join(", ")||`${family.label} evidence`} onClick={(event)=>{event.stopPropagation();openDetail("risk-map",{row:{...row,risks:matched.length?matched:row.risks,familyKeys:[family.key]}});}}>
                    <strong>{family.label}</strong>
                    <span>{familyFindings.length?`${familyFindings.length} finding${familyFindings.length===1?"":"s"}`:matched.length?`${matched.length} signal${matched.length===1?"":"s"}`:"contract signal"}</span>
                  </button>;
                })}</div>
                </article>;
              })}
            </div>:<RiskMapTable rows={heatRows} onOpen={(row)=>openDetail("risk-map",{row})} />}
            {renderDetail("risk-map")}
          </section>

          <section className="console-section">
            <div className="console-section-head"><div><p className="eyebrow">Evidence</p><h2>Reproducibility and audit trail</h2></div><Button variant="secondary compact" onClick={()=>openDetail("evidence",{key:"inspector",title:"Evidence Inspector"})}>Open Inspector</Button></div>
            <div className="smart-grid evidence-grid">
              <SmartCard icon={FileStack} label="Fingerprint" value={shortHash(version.fingerprint?.combined_fingerprint)||"N/A"} note={version.fingerprint?.algorithm_version||"algorithm N/A"} onClick={()=>openDetail("evidence",{key:"fingerprint",title:"Fingerprint"})} />
              <SmartCard icon={Network} label="Lineage" value={version.parent_version_id?`V${version.parent_version_id} -> V${version.version_number}`:"Baseline"} note={methodLabel(version)} onClick={()=>openDetail("evidence",{key:"lineage",title:"Lineage"})} />
              <SmartCard icon={ClipboardCheck} label="Contract" value={contract?.readiness?.intervention_count??0} note={`${contract?.readiness?.required_decision_count??0} decisions`} onClick={()=>openDetail("evidence",{key:"contract",title:"Diagnosis contract"})} />
              <SmartCard icon={GitBranch} label="Stability" value={semantic?`SCM ${displayMetric(semantic.scm_score)}`:"N/A"} note={semantic?`DSI ${displayMetric(semantic.dsi_score)}`:"baseline or unavailable"} onClick={()=>openDetail("evidence",{key:"stability",title:"Stability evidence"})} />
              <SmartCard icon={ShieldCheck} label="Reproducibility" value={diagnosis?.ruleset_version||"N/A"} note={profile?.profiler_version||"profile N/A"} onClick={()=>openDetail("evidence",{key:"reproducibility",title:"Reproducibility evidence"})} />
            </div>
            {renderDetail("evidence")}
          </section>

          <section className="console-section">
            <div className="console-section-head"><div><p className="eyebrow">Intervention Planner</p><h2>Collapsed actions</h2></div><button type="button" className="decision-pill" onClick={()=>openDetail("decisions")}>Human decisions required: {contract?.human_decisions?.length||0}</button></div>
            {!interventions.length?<Empty>No intervention options were generated from current findings.</Empty>:<div className="planner-list">{interventions.map((option)=><article key={option.id} role="button" tabIndex={0} className={`planner-item ${selectedOptions.includes(option.id)?"selected":""}`} onClick={()=>openDetail("intervention",{option})} onKeyDown={(event)=>event.key==="Enter"&&openDetail("intervention",{option})}><div className="planner-item-row"><span><input type="checkbox" checked={selectedOptions.includes(option.id)} onClick={(event)=>event.stopPropagation()} onChange={()=>toggleOption(option.id)} /><strong>{option.title}</strong></span><Badge tone={option.severity}>{option.status}</Badge></div><p>{option.triggered_by?.join(", ")||option.source_findings?.join(", ")||"Finding"} - {option.affected_columns?.length||0} columns - {option.metric_impact?.reliability_effect||"direction documented"}</p><div className="planner-operation-row">{(option.operations||[]).slice(0,3).map((op,index)=><button type="button" key={`${option.id}-${index}`} onClick={(event)=>{event.stopPropagation();openDetail("operation",{option,op,index});}}>{op.operation?.replaceAll("_"," ")}</button>)}</div></article>)}</div>}
            {renderDetail("planner")}
          </section>

          <section className="ai-compact-row"><span>AI Evidence Explanation</span><Button variant="secondary compact" onClick={()=>openDetail("ai")}>View</Button>{renderDetail("ai")}</section>
        </div>

        <aside className="variant-plan-console">
          <p className="eyebrow">Variant Plan</p><h2>Selected interventions</h2>
          <div className="context-list compact">
            <button type="button" className="context-row clickable" onClick={()=>openDetail("plan",{key:"selected",title:"Selected interventions"})}><strong>Selected</strong><span>{selected.length}</span></button>
            <button type="button" className="context-row clickable" onClick={()=>openDetail("plan",{key:"operations",title:"Selected operations"})}><strong>Operations</strong><span>{selectedOps.length}</span></button>
            <button type="button" className="context-row clickable" onClick={()=>openDetail("plan",{key:"columns",title:"Affected columns"})}><strong>Columns</strong><span>{[...new Set(selectedOps.flatMap((item)=>item.columns||[]))].join(", ")||"Dataset-level"}</span></button>
            <button type="button" className="context-row clickable" onClick={()=>openDetail("decisions")}><strong>Human decisions</strong><span>{contract?.human_decisions?.length||0}</span></button>
            <button type="button" className="context-row clickable" onClick={()=>openDetail("plan",{key:"baseline",title:"Baseline version"})}><strong>Baseline</strong><span>V{version.version_number}</span></button>
            <button type="button" className="context-row clickable" onClick={()=>openDetail("plan",{key:"metrics",title:"Recommended metrics"})}><strong>Metrics</strong><span>{contract?.experiment_handoff?.recommended_metrics?.join(", ")||"Primary metric"}</span></button>
            <button type="button" className="context-row clickable" onClick={()=>openDetail("plan",{key:"constraints",title:"Plan constraints"})}><strong>Constraints</strong><span>{selected.map((item)=>item.metric_impact?.reliability_effect).filter(Boolean).length?"Review required":"None selected"}</span></button>
          </div>
          <Button variant="secondary" onClick={()=>openDetail("plan",{key:"selected",title:"Review Variant Plan"})}>Review Plan</Button>
          <Button id="open-variant-generator-btn" onClick={onOpenVariants} disabled={!onOpenVariants}><Zap size={14}/>Generate Variants</Button>
          {renderDetail("plan")}
          <details className="debug-disclosure"><summary>Advanced contract JSON</summary><pre className="pre">{JSON.stringify(contract||{},null,2)}</pre></details>
        </aside>
      </main>
    </>}
  </div>;
}

function EvidenceInspector({ version, profile, diagnosis, semantic, variantRecord, contract }) {
  return <div className="diagnosis-detail-tabs">
    <details open><summary>Quality</summary><DiagnosisEvidenceSummary version={version} profile={profile} diagnosis={diagnosis} contract={contract} /></details>
    <details><summary>Leakage</summary><pre className="pre">{JSON.stringify(diagnosis?.score_breakdown?.leakage_evidence||{},null,2)}</pre></details>
    <details><summary>Stability</summary><MiniEvidenceList title="SCM / DSI" rows={[["SCM",semantic?displayMetric(semantic.scm_score):"Not computed"],["DSI",semantic?displayMetric(semantic.dsi_score):"Not computed"],["Schema added",semantic?.report?.columns_added?.join(", ")||"N/A"],["Schema removed",semantic?.report?.columns_removed?.join(", ")||"N/A"]]} /></details>
    <details><summary>Reproducibility</summary><MiniEvidenceList title="Hashes" rows={[["Fingerprint",shortHash(version.fingerprint?.combined_fingerprint)||"N/A"],["Configuration",shortHash(version.configuration?.configuration_hash)||"N/A"],["Ruleset",diagnosis?.ruleset_version||"N/A"],["Method",methodLabel(version)]]} /></details>
    <details><summary>Variant</summary><MiniEvidenceList title="Variant evidence" rows={[["VRS",variantRecord?.vrs_score!=null?displayMetric(variantRecord.vrs_score):"N/A"],["Pipeline",variantRecord?.pipeline_id||"N/A"],["Rank",variantRecord?.vrs_rank||"N/A"]]} /></details>
  </div>;
}

function DecisionPanel({ decisions = [] }) {
  if(!decisions.length)return <Notice>No human approvals are required by the current plan.</Notice>;
  return <div className="decision-drawer-list">{decisions.map((item,index)=><article key={`${item.finding_code}-${index}`}><h3>{item.question}</h3><p>{item.recommended_default}</p><MiniEvidenceList title="Impact" rows={[["Accept",item.consequence_accept],["Reject",item.consequence_reject],["Scope",item.affected_columns?.join(", ")||"Dataset-level"]]} /><div className="row"><Button variant="secondary compact">Accept</Button><Button variant="ghost compact">Reject</Button></div></article>)}</div>;
}

// Deprecated quarantine: the exported DiagnosisPanel above is the only active Diagnosis workspace.
// These retained legacy panels are not exported or called and should not receive new behavior.
function DashboardDiagnosisPanelLegacy({ study, datasets = [], version, profile, diagnosis, initialContract = null, onVersion, onOpenVariants }) {
  const [contract,setContract]=useState(initialContract);
  const [status,setStatus]=useState("");
  const [diagnosisReport,setDiagnosisReport]=useState(null);
  const [diagnosisReportStatus,setDiagnosisReportStatus]=useState("");
  const [selectedOptions,setSelectedOptions]=useState([]);
  const [detail,setDetail]=useState(null);
  const [running,setRunning]=useState(false);
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!version?.id||!diagnosis){setContract(null);return;}
      if(initialContract?.header?.version_id===version.id){setContract(initialContract);setSelectedOptions(initialContract.intervention_options.map((item)=>item.id));setStatus("");return;}
      setStatus("Loading diagnosis contract...");
      try{
        const result=await datasetApi.diagnosisContract(version.id);
        if(active){setContract(result);setSelectedOptions(result.intervention_options.map((item)=>item.id));setStatus("");}
      }catch(err){
        if(active){setContract(null);setStatus(err.response?.data?.detail||"Could not load diagnosis contract.");}
      }
    };
    load();
    return()=>{active=false;};
  },[version?.id,diagnosis?.id,initialContract?.header?.version_id]);
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!version?.id||!diagnosis?.id){setDiagnosisReport(null);setDiagnosisReportStatus("");return;}
      setDiagnosisReportStatus("Preparing stored diagnosis interpretation...");
      try{
        const result=await aiApi.diagnosisInterpretation(study.id,version.id);
        if(active){setDiagnosisReport(result);setDiagnosisReportStatus("");}
      }catch(err){
        if(active){setDiagnosisReport(null);setDiagnosisReportStatus(aiFallbackMessage());}
      }
    };
    load();
    return()=>{active=false;};
  },[study.id,version?.id,diagnosis?.id]);
  const selector=<DiagnosisVersionSelector datasets={datasets} version={version} onVersion={onVersion} status={status} setStatus={setStatus} transientStatus={running?"Running":status.includes("failed")?"Failed":null} />;
  const runDiagnosis=async(recompute=false)=>{
    if(!version?.id)return;
    setRunning(true);
    setStatus(recompute?"Recomputing diagnosis...":"Running diagnosis...");
    try{
      await datasetApi.runDiagnosis(version.id,recompute);
      await onVersion(version.id);
      setStatus(recompute?"Diagnosis recomputed.":"Diagnosis complete.");
    }catch(err){
      setStatus(err.response?.data?.detail||"Diagnosis run failed.");
    }finally{
      setRunning(false);
    }
  };
  if(!version)return <div className="diagnosis-workspace stack">{selector}<Card><Empty>Select a dataset version to inspect its diagnosis.</Empty></Card></div>;
  if(!diagnosis)return <div className="diagnosis-workspace stack">
    {selector}
    <Card className="diagnosis-empty-run">
      <div>
        <p className="eyebrow">Not diagnosed</p>
        <h2>Persisted diagnosis evidence is missing for V{version.version_number}</h2>
        <p className="muted">Run the deterministic ProfilingService to DiagnosisService workflow and store the result against this immutable dataset version.</p>
      </div>
      <Button loading={running} onClick={()=>runDiagnosis(false)}><ShieldCheck size={15}/>Run Diagnosis</Button>
      {status&&<Notice error={status.includes("failed")||status.includes("Could not")}>{status}</Notice>}
    </Card>
  </div>;
  const selected=(contract?.intervention_options||[]).filter((item)=>selectedOptions.includes(item.id));
  const selectedOps=selected.flatMap((item)=>item.operations||[]);
  const summary=profile?.report?.summary||{};
  const columns=profile?.report?.columns||[];
  const task=profile?.report?.task_profile||{};
  const highCorrelations=profile?.report?.high_correlations||[];
  const missingColumns=columns.filter((row)=>Number(row.missing_count)>0).sort((a,b)=>Number(b.missing_ratio)-Number(a.missing_ratio));
  const outlierColumns=columns.filter((row)=>Number(row.outlier_count)>0).sort((a,b)=>Number(b.outlier_ratio)-Number(a.outlier_ratio));
  const lowInfoColumns=columns.filter((row)=>Number(row.unique_count)<=1||Number(row.unique_ratio)<=0.01);
  const scoreBreakdown=diagnosis.score_breakdown||{};
  const mlrsComponents=scoreBreakdown.mlrs_components||diagnosis.mlrs_components||{};
  const lrsComponents=scoreBreakdown.lrs_components||diagnosis.lrs_components||{};
  const variantRecord=version.variant_record;
  const semantic=version.semantic_diff;
  const exportReport=async()=>{
    setStatus("Preparing diagnosis report...");
    try{
      const blob=await datasetApi.diagnosisReport(version.id);
      downloadBlob(blob,`fedrepro-diagnosis-v${version.version_number}-report.docx`);
      setStatus("Diagnosis report exported.");
    }catch(err){
      setStatus(err.response?.data?.detail||"Could not export diagnosis report.");
    }
  };
  const exportContract=()=>{
    if(!contract)return;
    downloadBlob(new Blob([JSON.stringify({...contract,selected_option_ids:selectedOptions},null,2)],{type:"application/json"}),`fedrepro-diagnosis-v${version.version_number}-contract.json`);
  };
  const toggleOption=(id)=>setSelectedOptions((items)=>items.includes(id)?items.filter((item)=>item!==id):[...items,id]);
  const openRows=(title, rows, raw, eyebrow="Evidence")=>setDetail({title, eyebrow, raw, body:<MiniEvidenceList title={title} rows={rows} />});
  return <div className="diagnosis-workspace stack">
    {selector}
    <Card className="diagnosis-dashboard-head">
      <div className="version-page-head">
        <div>
          <p className="eyebrow">Diagnosis dashboard</p>
          <h2>{study.name}</h2>
          <p className="muted">V{version.version_number} - {methodLabel(version)} - {version.diagnosis_status||"Diagnosed"} - MLRS {displayMetric(diagnosis.mlrs_score)} - LRS {displayMetric(diagnosis.lrs_score)}</p>
        </div>
        <div className="summary-actions">
          <Badge tone={version.diagnosis_status==="Recompute Available"?"warning":"success"}>{version.diagnosis_status||"Diagnosed"}</Badge>
          <Button variant="secondary" loading={running} onClick={()=>runDiagnosis(true)}><ShieldCheck size={15}/>Recompute Diagnosis</Button>
          <Button variant="secondary" onClick={exportContract} disabled={!contract}><Copy size={15}/>Export contract</Button>
          <Button onClick={exportReport}><FileCheck2 size={15}/>Export report</Button>
        </div>
      </div>
      {status&&<Notice error={status.includes("Could not")||status.includes("failed")}>{status}</Notice>}
      <div className="diagnosis-status-strip">
        <button type="button" onClick={()=>openRows("Dataset identity", [["Dataset", contract?.header?.dataset_name||"Dataset"],["Version", `V${version.version_number}`],["Method", methodLabel(version)],["Created", formatDate(diagnosis.created_at)]], version)}>
          <Database size={14}/><span>{contract?.header?.dataset_name||"Dataset"}</span>
        </button>
        <button type="button" onClick={()=>openRows("Target and configuration", [["Target", version.configuration?.target_column||"N/A"],["Metric", version.configuration?.primary_metric||"N/A"],["Validation", version.configuration?.validation_strategy||"N/A"]], version.configuration)}>
          <Target size={14}/><span>{version.configuration?.target_column||"No target"}</span>
        </button>
        <button type="button" onClick={()=>openRows("Reproducibility", [["Fingerprint", shortHash(version.fingerprint?.combined_fingerprint)||"N/A"],["Configuration hash", shortHash(version.configuration?.configuration_hash)||"N/A"],["Profile report", version.profile_report_id||"N/A"],["Ruleset", diagnosis.ruleset_version]], {fingerprint:version.fingerprint, configuration:version.configuration})}>
          <FileStack size={14}/><span>{shortHash(version.fingerprint?.combined_fingerprint)||"No fingerprint"}</span>
        </button>
      </div>
    </Card>

    <section className="diagnosis-flow-section">
      <div className="section-kicker"><p className="eyebrow">Dataset Quality</p><h2>Profiling evidence</h2></div>
      <div className="smart-grid quality-grid">
        <SmartCard icon={TableProperties} label="Rows / columns" value={`${summary.row_count??version.row_count} / ${summary.column_count??version.column_count}`} note={`${summary.numeric_columns??"N/A"} numeric - ${summary.categorical_columns??"N/A"} categorical`} onClick={()=>openRows("Shape and types", [["Rows", summary.row_count??version.row_count],["Columns", summary.column_count??version.column_count],["Numeric columns", summary.numeric_columns??"N/A"],["Categorical columns", summary.categorical_columns??"N/A"]], summary)} />
        <SmartCard icon={AlertTriangle} label="Missingness" value={compactPct(summary.missing_ratio)} note={`${summary.missing_cells??0} cells - ${missingColumns.length} columns`} tone={summary.missing_ratio>.05?"medium":"low"} onClick={()=>setDetail({title:"Missingness", eyebrow:"Dataset Quality", raw:missingColumns, body:<div className="stack">{missingColumns.length?missingColumns.slice(0,12).map((row)=><MiniBar key={row.name} label={row.name} value={Number(row.missing_ratio)*100} max={100} tone="medium" />):<Notice>No missing values detected.</Notice>}</div>})} />
        <SmartCard icon={Copy} label="Duplicates" value={summary.duplicate_rows??"N/A"} note={`${compactPct(summary.duplicate_ratio)} duplicate ratio`} tone={summary.duplicate_ratio>.01?"medium":"low"} onClick={()=>openRows("Duplicate evidence", [["Duplicate rows", summary.duplicate_rows??"N/A"],["Duplicate ratio", compactPct(summary.duplicate_ratio)]], summary)} />
        <SmartCard icon={Gauge} label="Outliers" value={outlierColumns.length} note={outlierColumns[0]?`${outlierColumns[0].name} leads evidence`:"No numeric outlier signal"} tone={outlierColumns.length?"medium":"low"} onClick={()=>setDetail({title:"Outlier evidence", eyebrow:"Dataset Quality", raw:outlierColumns, body:<div className="stack">{outlierColumns.length?outlierColumns.slice(0,12).map((row)=><MiniBar key={row.name} label={row.name} value={Number(row.outlier_ratio)*100} max={100} tone="medium" />):<Notice>No outlier evidence detected.</Notice>}</div>})} />
        <SmartCard icon={GitCompare} label="Correlation" value={highCorrelations.length} note={highCorrelations[0]?`${highCorrelations[0].left} / ${highCorrelations[0].right}`:"No high-correlation pairs"} tone={highCorrelations.length?"medium":"low"} onClick={()=>setDetail({title:"Correlation evidence", eyebrow:"Dataset Quality", raw:highCorrelations, body:<div className="stack">{highCorrelations.length?highCorrelations.slice(0,12).map((row)=><MiniBar key={`${row.left}-${row.right}`} label={`${row.left} / ${row.right}`} value={Math.abs(Number(row.correlation))*100} max={100} tone="medium" />):<Notice>No strong correlation pairs crossed the reporting threshold.</Notice>}</div>})} />
        <SmartCard icon={Target} label="Target distribution" value={task.imbalance_ratio?`${metricValue(task.imbalance_ratio)}x`:"N/A"} note={task.minority_class?`Minority: ${task.minority_class}`:"Not computed"} tone={task.imbalance_ratio>=4?"high":task.imbalance_ratio?"low":"neutral"} onClick={()=>setDetail({title:"Target distribution", eyebrow:"Dataset Quality", raw:task, body:<ClassDistributionBars distribution={task.class_distribution} />})} />
        <SmartCard icon={ScanSearch} label="Low information" value={lowInfoColumns.length} note={lowInfoColumns[0]?.name||"No constant feature evidence"} tone={lowInfoColumns.length?"medium":"low"} onClick={()=>openRows("Constant or low-information features", lowInfoColumns.length?lowInfoColumns.map((row)=>[row.name, `${row.unique_count} unique - ${compactPct(row.unique_ratio)}`]):[["Status","No constant or low-information features available"]], lowInfoColumns)} />
      </div>
    </section>

    <section className="diagnosis-flow-section">
      <div className="section-kicker"><p className="eyebrow">Diagnosis Metrics</p><h2>Risk scores and computed indicators</h2></div>
      <div className="diagnosis-metric-stage">
        <RiskGauge label="MLRS" value={diagnosis.mlrs_score} tone={riskTone(diagnosis.mlrs_score)} onClick={()=>setDetail({title:"MLRS component breakdown", eyebrow:"Diagnosis Metrics", raw:scoreBreakdown, body:<div className="stack">{Object.entries(mlrsComponents).map(([key,value])=><MiniBar key={key} label={key.replaceAll("_"," ")} value={value} max={25} tone={riskTone(value)} />)}</div>})} />
        <RiskGauge label="LRS" value={diagnosis.lrs_score} tone={riskTone(diagnosis.lrs_score)} onClick={()=>setDetail({title:"LRS leakage evidence", eyebrow:"Diagnosis Metrics", raw:scoreBreakdown.leakage_evidence||lrsComponents, body:<div className="stack">{Object.entries(lrsComponents).map(([key,value])=><MiniBar key={key} label={key.replaceAll("_"," ")} value={value} max={35} tone={riskTone(value)} />)}</div>})} />
        <SmartCard icon={GitBranch} label="SCM" value={semantic?displayMetric(semantic.scm_score):"Not computed"} note={semantic?"Semantic comparability":"Baseline or unavailable"} onClick={()=>openRows("SCM / semantic comparability", [["SCM", semantic?displayMetric(semantic.scm_score):"Not computed"],["Ruleset", semantic?.ruleset_version||"N/A"]], semantic)} />
        <SmartCard icon={ScanSearch} label="DSI" value={semantic?displayMetric(semantic.dsi_score):"Not computed"} note={semantic?"Dataset shift indicator":"Baseline or unavailable"} onClick={()=>openRows("DSI / dataset shift", [["DSI", semantic?displayMetric(semantic.dsi_score):"Not computed"],["Missingness delta", semantic?.report?.missing_ratio_change!=null?signedPct(semantic.report.missing_ratio_change):"N/A"],["Duplicate delta", semantic?.report?.duplicate_rows?.delta??"N/A"]], semantic)} />
        <SmartCard icon={Zap} label="VRS" value={variantRecord?.vrs_score!=null?displayMetric(variantRecord.vrs_score):"N/A"} note={variantRecord?`${variantRecord.pipeline_id} - rank ${variantRecord.vrs_rank||"N/A"}`:"Only variant-generated versions"} tone={variantRecord?.vrs_score>=80?"low":variantRecord?.vrs_score?"medium":"neutral"} onClick={()=>openRows("VRS variant evidence", [["Pipeline", variantRecord?.pipeline_id||"N/A"],["VRS", variantRecord?.vrs_score!=null?displayMetric(variantRecord.vrs_score):"N/A"],["Rank", variantRecord?.vrs_rank||"N/A"],["Goal", variantRecord?.goal_satisfaction||"N/A"],["MLRS before", displayMetric(variantRecord?.mlrs_before)],["MLRS after", displayMetric(variantRecord?.mlrs_after)],["LRS after", displayMetric(variantRecord?.lrs_after)]], variantRecord)} />
        <SmartCard icon={AlertTriangle} label="Findings" value={diagnosis.findings.length} note={`${contract?.readiness?.status||"Diagnosis loaded"}`} tone={diagnosis.findings.length?"medium":"low"} onClick={()=>setDetail({title:"Severity distribution", eyebrow:"Diagnosis Metrics", raw:diagnosis.findings, body:<SeverityStrip findings={diagnosis.findings} />})} />
      </div>
    </section>

    <section className="diagnosis-flow-section">
      <div className="section-kicker"><p className="eyebrow">Risk Explorer</p><h2>Findings</h2></div>
      {!diagnosis.findings.length?<Notice>No material risk crossed the configured deterministic thresholds.</Notice>:<div className="risk-explorer-grid">{diagnosis.findings.map((item)=><button type="button" key={item.code} className={`risk-tile ${item.severity}`} onClick={()=>setDetail({title:item.issue, eyebrow:item.code, subtitle:item.risk, raw:item.evidence, body:<div className="stack"><MiniEvidenceList title="Finding" rows={[["Severity", item.severity],["Risk", item.risk],["Recommendation", item.recommendation],["Columns", DiagnosisFindingColumns(item).join(", ")||"Dataset-level"]]} /></div>})}><div><strong>{item.issue}</strong><Badge tone={item.severity}>{item.severity}</Badge></div><p>{item.recommendation}</p></button>)}</div>}
    </section>

    <section className="diagnosis-flow-section">
      <div className="section-kicker"><p className="eyebrow">Risk Map</p><h2>Feature x risk matrix</h2></div>
      <RiskHeatmap findings={diagnosis.findings} contract={contract} onInspect={setDetail} />
    </section>

    <section className="diagnosis-two-column">
      <Card>
        <p className="eyebrow">Interventions</p><h2>Evidence-triggered actions</h2>
        {!contract?.intervention_options?.length?<Empty>No intervention options were generated from the current diagnosis.</Empty>:<div className="intervention-list compact">{contract.intervention_options.map((option)=><button type="button" className={`intervention-card compact ${selectedOptions.includes(option.id)?"selected":""}`} key={option.id} onClick={()=>setDetail({title:option.title, eyebrow:"Intervention", subtitle:option.objective, raw:option, body:<div className="stack"><MiniEvidenceList title="Triggered by" rows={option.source_findings.map((item)=>[item, option.triggered_by.join(", ")])} /><MiniEvidenceList title="Operations" rows={option.operations.map((op)=>[op.operation.replaceAll("_"," "), op.purpose])} /><MetricImpactPreview impact={option.metric_impact} /></div>})}><span><input type="checkbox" checked={selectedOptions.includes(option.id)} onChange={(event)=>{event.stopPropagation();toggleOption(option.id);}} /> <strong>{option.title}</strong></span><Badge tone={option.severity}>{option.status}</Badge></button>)}</div>}
      </Card>
      <Card>
        <p className="eyebrow">Human Decisions</p><h2>Approvals before generation</h2>
        {!contract?.human_decisions?.length?<Notice>No user approvals are required by the current intervention plan.</Notice>:<div className="decision-list compact">{contract.human_decisions.map((item,index)=><button type="button" key={`${item.finding_code}-${index}`} onClick={()=>setDetail({title:item.question, eyebrow:"Human decision", raw:item, body:<MiniEvidenceList title="Decision impact" rows={[["Default", item.recommended_default],["Accepting", item.consequence_accept],["Rejecting", item.consequence_reject],["Scope", item.affected_columns.join(", ")||"Dataset-level"]]} />})}><strong>{item.question}</strong><span>{item.recommended_default}</span></button>)}</div>}
      </Card>
    </section>

    <section className="diagnosis-plan-evidence-grid">
      <Card className="sticky-variant-plan">
        <p className="eyebrow">Variant Plan</p><h2>Generator-ready plan</h2>
        <div className="context-list">
          <div className="context-row"><strong>Selected options</strong><span>{selected.length}</span></div>
          <div className="context-row"><strong>Total operations</strong><span>{selectedOps.length}</span></div>
          <div className="context-row"><strong>Affected columns</strong><span>{[...new Set(selectedOps.flatMap((item)=>item.columns||[]))].join(", ")||"Dataset-level"}</span></div>
          <div className="context-row"><strong>Baseline</strong><span>{contract?.experiment_handoff?.required_baseline||`V${version.version_number}`}</span></div>
          <div className="context-row"><strong>Recommended metrics</strong><span>{contract?.experiment_handoff?.recommended_metrics?.join(", ")||"Primary metric"}</span></div>
        </div>
        <Button id="open-variant-generator-btn" onClick={onOpenVariants} disabled={!onOpenVariants}><Zap size={14}/>Generate Variants</Button>
      </Card>
      <div className="stack">
        <Card>
          <p className="eyebrow">Evidence</p><h2>Reproducible outputs</h2>
          <div className="smart-grid evidence-grid">
            <SmartCard icon={FileStack} label="Fingerprint" value={shortHash(version.fingerprint?.combined_fingerprint)||"N/A"} note={version.fingerprint?.algorithm_version||"N/A"} onClick={()=>openRows("Fingerprint", [["File hash", shortHash(version.fingerprint?.file_hash)||"N/A"],["Schema hash", shortHash(version.fingerprint?.schema_hash)||"N/A"],["Metadata hash", shortHash(version.fingerprint?.metadata_hash)||"N/A"],["Combined", shortHash(version.fingerprint?.combined_fingerprint)||"N/A"]], version.fingerprint)} />
            <SmartCard icon={ClipboardCheck} label="Interventions" value={contract?.readiness?.intervention_count??0} note={`${contract?.readiness?.required_decision_count??0} decisions`} onClick={()=>openRows("Intervention readiness", [["Status", contract?.readiness?.status||"N/A"],["Interventions", contract?.readiness?.intervention_count??0],["Required decisions", contract?.readiness?.required_decision_count??0],["Finding count", contract?.readiness?.finding_count??diagnosis.findings.length]], contract?.readiness)} />
            <SmartCard icon={Network} label="Lineage" value={version.parent_version_id?`V${version.parent_version_id} -> V${version.version_number}`:"Baseline"} note={methodLabel(version)} onClick={()=>openRows("Lineage", [["Parent", version.parent_version_id||"Baseline"],["Version", `V${version.version_number}`],["Generation", methodLabel(version)],["Notes", version.version_notes||"N/A"]], version)} />
          </div>
          <details className="debug-disclosure"><summary>Advanced/debug evidence matrix</summary><DiagnosisEvidenceSummary version={version} profile={profile} diagnosis={diagnosis} contract={contract} /></details>
        </Card>
        <DiagnosisLLMReport report={diagnosisReport} status={diagnosisReportStatus} />
      </div>
    </section>

    <Card>
      <p className="eyebrow">Export / report section</p><h2>Structured outputs</h2>
      <div className="action-stack horizontal"><Button onClick={exportReport}><FileCheck2 size={15}/>Professional DOCX report</Button><Button variant="secondary" disabled={!contract} onClick={exportContract}><Copy size={15}/>Diagnosis contract JSON</Button></div>
    </Card>
    <DetailDrawer detail={detail} onClose={()=>setDetail(null)} />
  </div>;
}

function LegacyDiagnosisPanel({ study, datasets = [], version, profile, diagnosis, initialContract = null, onVersion, onOpenVariants }) {
  const [contract,setContract]=useState(initialContract);
  const [status,setStatus]=useState("");
  const [diagnosisReport,setDiagnosisReport]=useState(null);
  const [diagnosisReportStatus,setDiagnosisReportStatus]=useState("");
  const [selectedOptions,setSelectedOptions]=useState([]);
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!version?.id||!diagnosis){setContract(null);return;}
      if(initialContract?.header?.version_id===version.id){setContract(initialContract);setSelectedOptions(initialContract.intervention_options.map((item)=>item.id));setStatus("");return;}
      setStatus("Loading diagnosis contract...");
      try{
        const result=await datasetApi.diagnosisContract(version.id);
        if(active){setContract(result);setSelectedOptions(result.intervention_options.map((item)=>item.id));setStatus("");}
      }catch(err){
        if(active){setContract(null);setStatus(err.response?.data?.detail||"Could not load diagnosis contract.");}
      }
    };
    load();
    return()=>{active=false;};
  },[version?.id,diagnosis?.id,initialContract?.header?.version_id]);
  useEffect(()=>{
    let active=true;
    const load=async()=>{
      if(!version?.id||!diagnosis?.id){setDiagnosisReport(null);setDiagnosisReportStatus("");return;}
      setDiagnosisReportStatus("Preparing stored diagnosis interpretation...");
      try{
        const result=await aiApi.diagnosisInterpretation(study.id,version.id);
        if(active){setDiagnosisReport(result);setDiagnosisReportStatus("");}
      }catch(err){
        if(active){setDiagnosisReport(null);setDiagnosisReportStatus(aiFallbackMessage());}
      }
    };
    load();
    return()=>{active=false;};
  },[study.id,version?.id,diagnosis?.id]);
  const selector=<DiagnosisVersionSelector datasets={datasets} version={version} onVersion={onVersion} status={status} setStatus={setStatus} />;
  if(!diagnosis||!version)return <div className="diagnosis-workspace stack">{selector}<Card><Empty>Select a dataset version to inspect its diagnosis.</Empty></Card></div>;
  const chart=[{name:"MLRS",score:diagnosis.mlrs_score},{name:"LRS",score:diagnosis.lrs_score}];
  const selected=(contract?.intervention_options||[]).filter((item)=>selectedOptions.includes(item.id));
  const selectedOps=selected.flatMap((item)=>item.operations||[]);
  const exportReport=async()=>{
    setStatus("Preparing diagnosis report...");
    try{
      const blob=await datasetApi.diagnosisReport(version.id);
      downloadBlob(blob,`fedrepro-diagnosis-v${version.version_number}-report.docx`);
      setStatus("Diagnosis report exported.");
    }catch(err){
      setStatus(err.response?.data?.detail||"Could not export diagnosis report.");
    }
  };
  const exportContract=()=>{
    if(!contract)return;
    downloadBlob(new Blob([JSON.stringify({...contract,selected_option_ids:selectedOptions},null,2)],{type:"application/json"}),`fedrepro-diagnosis-v${version.version_number}-contract.json`);
  };
  const toggleOption=(id)=>setSelectedOptions((items)=>items.includes(id)?items.filter((item)=>item!==id):[...items,id]);
  return <div className="diagnosis-workspace stack">
    {selector}
    <Card className="diagnosis-header-card">
      <div className="version-page-head">
        <div><p className="eyebrow">Diagnosis header</p><h2>{study.name}</h2><p className="muted">{contract?.header?.dataset_name||"Dataset"} · V{version.version_number} · report #{diagnosis.id}</p></div>
        <div className="summary-actions"><Button variant="secondary" onClick={exportContract} disabled={!contract}><Copy size={15}/>Export contract</Button><Button onClick={exportReport}><FileCheck2 size={15}/>Export report</Button></div>
      </div>
      {status&&<Notice error={status.includes("Could not")}>{status}</Notice>}
      <div className="diagnosis-meta-grid">
        <VersionState label="Dataset" value={contract?.header?.dataset_name} />
        <VersionState label="Target" value={version.configuration?.target_column} />
        <VersionState label="Profile report" value={contract?.header?.profile_report_id||version.profile_report_id} />
        <VersionState label="Fingerprint" value={shortHash(contract?.header?.dataset_fingerprint||version.fingerprint?.combined_fingerprint)} mono />
        <VersionState label="Diagnosis ruleset" value={diagnosis.ruleset_version} />
        <VersionState label="Created" value={formatDate(diagnosis.created_at)} />
      </div>
    </Card>

    <Card>
      <p className="eyebrow">Diagnosis readiness summary</p><h2>{contract?.readiness?.status||"Diagnosis loaded"}</h2>
      <div className="grid grid-4">
        <MetricCard label="MLRS" value={metricValue(diagnosis.mlrs_score)} icon={Gauge} />
        <MetricCard label="LRS" value={metricValue(diagnosis.lrs_score)} icon={ShieldCheck} />
        <MetricCard label="Findings" value={diagnosis.findings.length} icon={AlertTriangle} />
        <MetricCard label="Interventions" value={contract?.readiness?.intervention_count??0} icon={ClipboardCheck} />
      </div>
      <ResponsiveContainer width="100%" height={170}><BarChart data={chart}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="name"/><YAxis domain={[0,100]}/><Tooltip/><Bar dataKey="score" fill="#245ca6"/></BarChart></ResponsiveContainer>
    </Card>

    {/* ── Variant Generator CTA ─────────────────────────────────────────── */}
    <Card style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)", border: "1px solid #4338ca" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <Zap size={18} style={{ color: "#818cf8" }} />
            <p className="eyebrow" style={{ margin: 0, color: "#818cf8" }}>Next step</p>
          </div>
          <h3 style={{ margin: "0 0 4px" }}>Generate Preprocessing Variants</h3>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>
            Diagnosis is complete — MLRS&nbsp;<strong style={{ color: "#e2e8f0" }}>{diagnosis.mlrs_score?.toFixed(1)}</strong> · LRS&nbsp;<strong style={{ color: "#e2e8f0" }}>{diagnosis.lrs_score?.toFixed(1)}</strong>.
            The Variant Generator will automatically build and rank preprocessing pipelines to improve these scores.
          </p>
        </div>
        <Button
          id="open-variant-generator-btn"
          onClick={onOpenVariants}
          disabled={!onOpenVariants}
          style={{ whiteSpace: "nowrap", background: "#4f46e5", borderColor: "#4f46e5" }}
        >
          <Zap size={14} />
          Generate Variants
        </Button>
      </div>
    </Card>

    <Card>
      <p className="eyebrow">Diagnosis statistics</p><h2>Evidence matrix</h2>
      <DiagnosisEvidenceSummary version={version} profile={profile} diagnosis={diagnosis} contract={contract} />
    </Card>

    <DiagnosisLLMReport report={diagnosisReport} status={diagnosisReportStatus} />

    <Card>
      <p className="eyebrow">Risk family overview</p><h2>Detected risk families</h2>
      {!contract?.risk_families?.length?<Empty>No diagnosis risk families were detected.</Empty>:<div className="diagnosis-family-grid">{contract.risk_families.map((item)=><article key={item.family} className="diagnosis-family"><div className="row"><strong>{item.family}</strong><Badge tone={item.severity}>{item.severity}</Badge></div><span>{item.finding_count} finding{item.finding_count===1?"":"s"} · {item.affected_columns.length} column{item.affected_columns.length===1?"":"s"}</span>{!!item.affected_columns.length&&<small>{item.affected_columns.join(", ")}</small>}</article>)}</div>}
    </Card>

    <Card>
      <p className="eyebrow">Dynamic intervention options</p><h2>Evidence-triggered actions</h2>
      {!contract?.intervention_options?.length?<Empty>No intervention options were generated from the current diagnosis.</Empty>:<div className="intervention-list">{contract.intervention_options.map((option)=><details className="intervention-card" key={option.id} open>
        <summary><label><input type="checkbox" checked={selectedOptions.includes(option.id)} onChange={()=>toggleOption(option.id)} /> <strong>{option.title}</strong></label><Badge tone={option.severity}>{option.status}</Badge></summary>
        <p>{option.objective}</p>
        <div className="diagnosis-split">
          <MiniEvidenceList title="Triggered by" rows={option.source_findings.map((item)=>[item, option.triggered_by.join(", ")])} />
          <MiniEvidenceList title="Affected columns" rows={(option.affected_columns.length?option.affected_columns:["Dataset-level"]).map((item)=>[item, "included in plan"])} />
        </div>
        <div className="operation-stack">{option.operations.map((op)=><div key={`${option.id}-${op.operation}`}><strong>{op.operation.replaceAll("_"," ")}</strong><span>{op.purpose}</span>{!!op.columns.length&&<small>{op.columns.join(", ")}</small>}</div>)}</div>
        <MetricImpactPreview impact={option.metric_impact} />
        {!!option.expected_changes.length&&<MiniEvidenceList title="Expected dataset changes" rows={option.expected_changes.map((item,index)=>[`Change ${index+1}`,item])} />}
        {!!option.risks_introduced.length&&<MiniEvidenceList title="Risks introduced" rows={option.risks_introduced.map((item,index)=>[`Risk ${index+1}`,item])} />}
      </details>)}</div>}
    </Card>

    <Card>
      <p className="eyebrow">Human decision queue</p><h2>Approvals before generation</h2>
      {!contract?.human_decisions?.length?<Notice>No user approvals are required by the current intervention plan.</Notice>:<div className="decision-list">{contract.human_decisions.map((item,index)=><article key={`${item.finding_code}-${index}`}><h3>{item.question}</h3><p>{item.recommended_default}</p><div className="context-list compact"><div className="context-row"><strong>Accepting</strong><span>{item.consequence_accept}</span></div><div className="context-row"><strong>Rejecting</strong><span>{item.consequence_reject}</span></div><div className="context-row"><strong>Scope</strong><span>{item.affected_columns.join(", ")||"Dataset-level"}</span></div></div></article>)}</div>}
    </Card>

    <div className="grid grid-2">
      <Card>
        <p className="eyebrow">Selected variant plan</p><h2>Generator-ready plan</h2>
        <div className="context-list">
          <div className="context-row"><strong>Selected options</strong><span>{selected.length}</span></div>
          <div className="context-row"><strong>Total operations</strong><span>{selectedOps.length}</span></div>
          <div className="context-row"><strong>Affected columns</strong><span>{[...new Set(selectedOps.flatMap((item)=>item.columns||[]))].join(", ")||"Dataset-level"}</span></div>
          <div className="context-row"><strong>Variant names</strong><span>{selected.map((item)=>`V${version.version_number} - ${item.title}`).join("; ")||"No variants selected"}</span></div>
        </div>
      </Card>
      <Card>
        <p className="eyebrow">Experiment handoff contract</p><h2>Future experiment inputs</h2>
        <div className="context-list">
          <div className="context-row"><strong>Baseline</strong><span>{contract?.experiment_handoff?.required_baseline||`V${version.version_number}`}</span></div>
          <div className="context-row"><strong>Recommended metrics</strong><span>{contract?.experiment_handoff?.recommended_metrics?.join(", ")||"Primary metric"}</span></div>
          <div className="context-row"><strong>Constraints</strong><span>{contract?.experiment_handoff?.constraints?.length||0}</span></div>
          <div className="context-row"><strong>Cautions</strong><span>{contract?.experiment_handoff?.cautions?.length||0}</span></div>
        </div>
        <details><summary>Raw contract preview</summary><pre className="pre">{JSON.stringify(contract?.experiment_handoff||{},null,2)}</pre></details>
      </Card>
    </div>

    <Card>
      <p className="eyebrow">Findings board</p><h2>Diagnosis evidence</h2>
      {!diagnosis.findings.length?<Notice>No material risk crossed the configured deterministic thresholds.</Notice>:<div className="stack">{diagnosis.findings.map((item)=><article key={item.code} className={`finding ${item.severity}`}><div className="row"><h2>{item.issue}</h2><Badge tone={item.severity}>{item.severity}</Badge></div><p><strong>Risk:</strong> {item.risk}</p><p><strong>Recommendation:</strong> {item.recommendation}</p><details><summary>Evidence</summary><pre className="pre">{JSON.stringify(item.evidence,null,2)}</pre></details></article>)}</div>}
    </Card>

    <Card>
      <p className="eyebrow">Column impact matrix</p><h2>Affected feature view</h2>
      {!contract?.column_impact?.length?<Empty>No column-specific diagnosis impacts were available.</Empty>:<DataTable rows={contract.column_impact} columns={[
        {key:"column",label:"Column"},
        {key:"role",label:"Role"},
        {key:"data_type",label:"Type"},
        {key:"risk_families",label:"Risks",render:(row)=>row.risk_families.join(", ")},
        {key:"recommended_operation_count",label:"Ops"}
      ]}/>}
    </Card>

    <Card>
      <p className="eyebrow">Export / report section</p><h2>Structured outputs</h2>
      <div className="action-stack horizontal"><Button onClick={exportReport}><FileCheck2 size={15}/>Professional DOCX report</Button><Button variant="secondary" disabled={!contract} onClick={exportContract}><Copy size={15}/>Diagnosis contract JSON</Button></div>
    </Card>
  </div>;
}

function MetricImpactPreview({ impact }) {
  if(!impact)return null;
  return <div className="metric-impact-preview">
    <h3>Metric impact preview</h3>
    <div className="context-list compact">
      <div className="context-row"><strong>Affected metrics</strong><span>{impact.affected_metrics?.join(", ")}</span></div>
      <div className="context-row"><strong>Possible positive effect</strong><span>{impact.possible_positive_effect}</span></div>
      <div className="context-row"><strong>Possible negative effect</strong><span>{impact.possible_negative_effect}</span></div>
      <div className="context-row"><strong>Reliability effect</strong><span>{impact.reliability_effect}</span></div>
      <div className="context-row"><strong>Final finding implication</strong><span>{impact.final_finding_implication}</span></div>
    </div>
    {!!impact.verification_required?.length&&<ul>{impact.verification_required.map((item,index)=><li key={index}>{item}</li>)}</ul>}
  </div>;
}

export function AIPanel({ study, version, profile, diagnosis }) {
  const [type,setType]=useState("study_description"); const [result,setResult]=useState(null); const [status,setStatus]=useState("");
  const sources={study_description:study.id,semantic_diff:version?.semantic_diff?.id,profile:profile?.id,diagnosis:diagnosis?.id};
  const run=async()=>{setStatus("Generating evidence interpretation...");setResult(null);try{setResult(await aiApi.explain(study.id,{explanation_type:type,source_entity_id:sources[type]}));setStatus("");}catch(err){setStatus(aiFallbackMessage());}};
  return <Card className="ai-panel"><h2>Optional AI explanation</h2><p className="muted">Ollama explains persisted evidence only. It cannot calculate metrics, modify findings, or change severity.</p><div className="form-grid"><Field label="Explanation type"><select value={type} onChange={(e)=>setType(e.target.value)}><option value="study_description">Improve study description</option><option value="semantic_diff">Explain semantic change</option><option value="profile">Explain profile</option><option value="diagnosis">Explain diagnosis</option></select></Field><div className="field"><label>&nbsp;</label><Button onClick={run} disabled={!sources[type]}>Generate with Ollama</Button></div></div>{status&&<Notice error={status.includes("failed")}>{status}</Notice>}{result&&<div style={{marginTop:16}}><p className="metric-label">{result.model} · evidence {result.source_evidence_hash.slice(0,12)}</p><div className="pre">{result.content}</div></div>}</Card>;
}

// ── VariantGeneratorPanel ─────────────────────────────────────────────────────

const GOALS = [
  { value: "maximize_accuracy",   label: "Maximize Accuracy",    desc: "Best overall predictive performance" },
  { value: "improve_recall",      label: "Improve Recall",       desc: "Prioritise minority-class detection" },
  { value: "fairness",            label: "Class Fairness",       desc: "Balance class representation" },
  { value: "faster_training",     label: "Faster Training",      desc: "Reduce preprocessing and training time" },
  { value: "lightweight_dataset", label: "Lightweight Dataset",  desc: "Minimise size and memory footprint" },
  { value: "explainable_model",   label: "Explainable Model",    desc: "Low-complexity, interpretable feature set" },
];

function vrsColor(score) {
  if (score == null) return "#6b7280";
  if (score >= 80) return "#22c55e";
  if (score >= 60) return "#eab308";
  if (score >= 40) return "#f97316";
  return "#ef4444";
}

function CostBadge({ cost }) {
  const map = { very_low: { label: "Very Low", color: "#22c55e" }, low: { label: "Low", color: "#84cc16" }, medium: { label: "Medium", color: "#f59e0b" }, high: { label: "High", color: "#ef4444" } };
  const { label, color } = map[cost] || { label: cost || "—", color: "#6b7280" };
  return <span style={{ background: color + "22", color, padding: "2px 8px", borderRadius: 4, fontSize: 12, fontWeight: 600 }}>{label}</span>;
}

function MlrsIndicator({ before, after, improvement }) {
  if (before == null || after == null) return <span className="muted">—</span>;
  const reduced = improvement > 0;
  return (
    <span title="MLRS is a risk score — lower is better" style={{ color: reduced ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
      {after.toFixed(1)} {reduced ? "↓" : "↑"} <span style={{ opacity: 0.7, fontSize: 12 }}>({reduced ? "-" : "+"}{Math.abs(improvement).toFixed(1)})</span>
    </span>
  );
}

function LrsCell({ lrs, caveat }) {
  if (lrs == null) return <span className="muted">—</span>;
  return (
    <span>
      {lrs.toFixed(1)}
      {caveat === "mi_selection_expected" && (
        <span
          title="LRS elevation is expected when Mutual Information feature selection is used and does not indicate real leakage."
          style={{ marginLeft: 4, cursor: "help", color: "#60a5fa" }}
        >ⓘ</span>
      )}
    </span>
  );
}

function PipelinePassport({ record }) {
  const [open, setOpen] = useState(false);
  const steps = record.steps || record.explanation_json?.steps || [];
  return (
    <details open={open} onToggle={e => setOpen(e.target.open)} style={{ marginTop: 8 }}>
      <summary style={{ cursor: "pointer", color: "#60a5fa", fontSize: 13 }}>
        {open ? "Hide" : "View"} pipeline passport ({steps.length} steps)
      </summary>
      <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: "2px solid #334155" }}>
        {steps.map((step, i) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <p style={{ fontWeight: 600, marginBottom: 2, fontSize: 13 }}>{i + 1}. {step.label}</p>
            <p style={{ color: "#94a3b8", fontSize: 12, margin: 0 }}>{step.explanation}</p>
            {step.params && Object.keys(step.params).length > 0 && (
              <pre style={{ fontSize: 11, color: "#64748b", margin: "4px 0 0" }}>{JSON.stringify(step.params, null, 2)}</pre>
            )}
          </div>
        ))}
        {record.explanation_json?.rationale && (
          <p style={{ fontStyle: "italic", color: "#94a3b8", fontSize: 12, borderTop: "1px solid #1e293b", paddingTop: 8, marginTop: 8 }}>
            {record.explanation_json.rationale}
          </p>
        )}
      </div>
    </details>
  );
}

function VariantRecordRow({ record, jobId, onRegistered }) {
  const [registering, setRegistering] = useState(false);
  const [registered, setRegistered] = useState(!!record.variant_version_id);

  const handleRegister = async () => {
    setRegistering(true);
    try {
      await variantApi.registerVariant(jobId, record.id, {});
      setRegistered(true);
      if (onRegistered) onRegistered();
    } catch (err) {
      alert(err.response?.data?.detail || "Registration failed");
    } finally {
      setRegistering(false);
    }
  };

  const satisfaction = record.goal_satisfaction;
  const satColor = { excellent: "#22c55e", good: "#84cc16", fair: "#f59e0b", poor: "#ef4444" }[satisfaction] || "#6b7280";

  return (
    <div style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, padding: "16px 20px", marginBottom: 12 }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: "#e2e8f0" }}>{record.pipeline_id}</span>
        {record.vrs_rank && (
          <span style={{ background: "#1e293b", color: "#60a5fa", padding: "2px 10px", borderRadius: 4, fontSize: 12 }}>
            Rank #{record.vrs_rank}
          </span>
        )}
        <CostBadge cost={record.estimated_cost} />
        {satisfaction && (
          <span style={{ color: satColor, fontWeight: 600, fontSize: 12 }}>{satisfaction.charAt(0).toUpperCase() + satisfaction.slice(1)}</span>
        )}
        {record.status === "failed" && <Badge tone="critical">Failed</Badge>}
      </div>

      {/* VRS score bar */}
      {record.vrs_score != null && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span style={{ fontSize: 12, color: "#94a3b8" }}>Variant Readiness Score (VRS)</span>
            <span style={{ fontWeight: 700, color: vrsColor(record.vrs_score) }}>{record.vrs_score.toFixed(1)}/100</span>
          </div>
          <div style={{ background: "#1e293b", borderRadius: 4, height: 6 }}>
            <div style={{ width: `${record.vrs_score}%`, background: vrsColor(record.vrs_score), height: "100%", borderRadius: 4, transition: "width 0.4s" }} />
          </div>
        </div>
      )}

      {/* Metrics grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8, marginBottom: 12 }}>
        <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>MLRS Risk ↓</div>
          <MlrsIndicator before={record.mlrs_before} after={record.mlrs_after} improvement={record.mlrs_improvement} />
        </div>
        <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>LRS After</div>
          <LrsCell lrs={record.lrs_after} caveat={record.lrs_caveat} />
        </div>
        <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>Missing %</div>
          <span style={{ fontWeight: 600 }}>
            {record.missing_values_pct_before != null ? record.missing_values_pct_before.toFixed(1) : "—"}
            {" → "}
            {record.missing_values_pct_after != null ? record.missing_values_pct_after.toFixed(1) : "—"}
          </span>
        </div>
        <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>Class Balance ↑</div>
          <span style={{ fontWeight: 600 }}>
            {record.class_balance_score_after != null ? (record.class_balance_score_after * 100).toFixed(0) + "%" : "—"}
          </span>
        </div>
        <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>Features</div>
          <span style={{ fontWeight: 600 }}>
            {record.feature_count_before != null ? record.feature_count_before : "—"}
            {" → "}
            {record.feature_count_after != null ? record.feature_count_after : "—"}
          </span>
        </div>
        <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>Rows</div>
          <span style={{ fontWeight: 600 }}>
            {record.row_count_after != null ? record.row_count_after.toLocaleString() : "—"}
          </span>
        </div>
        {record.execution_time_seconds != null && (
          <div style={{ background: "#1e293b", padding: "8px 12px", borderRadius: 6 }}>
            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 2 }}>Time</div>
            <span style={{ fontWeight: 600 }}>{record.execution_time_seconds.toFixed(1)}s</span>
          </div>
        )}
      </div>

      {/* Steps summary chips */}
      {record.steps && record.steps.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
          {record.steps.map((s, i) => (
            <span key={i} style={{ background: "#1e293b", color: "#94a3b8", padding: "2px 8px", borderRadius: 12, fontSize: 11 }}>
              {s.label}
            </span>
          ))}
        </div>
      )}

      {/* Passport */}
      {record.status === "completed" && <PipelinePassport record={record} />}

      {/* Actions */}
      <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
        {record.status === "completed" && !registered && (
          <Button onClick={handleRegister} disabled={registering}>
            <GitBranch size={14} />
            {registering ? "Registering…" : "Register as Version"}
          </Button>
        )}
        {registered && (
          <span style={{ color: "#22c55e", fontSize: 13, fontWeight: 600 }}>
            <CheckCircle2 size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
            Registered as V{record.variant_version_id}
          </span>
        )}
        {record.error_message && (
          <span style={{ color: "#ef4444", fontSize: 12 }}>{record.error_message}</span>
        )}
      </div>
    </div>
  );
}

export function VariantGeneratorPanel({ version, diagnosis }) {
  const [goal, setGoal] = useState("maximize_accuracy");
  const [nPipelines, setNPipelines] = useState(4);
  const [avoidSynthetic, setAvoidSynthetic] = useState(false);
  const [maxFeatures, setMaxFeatures] = useState("");
  const [job, setJob] = useState(null);
  const [status, setStatus] = useState("");
  const [polling, setPolling] = useState(false);
  const [existingJobs, setExistingJobs] = useState([]);

  const versionId = version?.id;
  const hasDiagnosis = !!diagnosis;

  // Load existing jobs for this version on mount
  useEffect(() => {
    if (!versionId) return;
    variantApi.listJobs(versionId).then(setExistingJobs).catch(() => {});
  }, [versionId]);

  // Polling: refresh job every 3 seconds while running
  useEffect(() => {
    if (!job || job.status !== "running") { setPolling(false); return; }
    setPolling(true);
    const interval = setInterval(async () => {
      try {
        const updated = await variantApi.getJob(job.id);
        setJob(updated);
        if (updated.status !== "running") { clearInterval(interval); setPolling(false); }
      } catch { clearInterval(interval); setPolling(false); }
    }, 3000);
    return () => clearInterval(interval);
  }, [job?.id, job?.status]);

  const handleGenerate = async () => {
    setStatus("Generating variants…");
    setJob(null);
    try {
      const constraints = { avoid_synthetic_data: avoidSynthetic };
      if (maxFeatures) constraints.max_features = parseInt(maxFeatures, 10);
      const result = await variantApi.createJob(versionId, {
        source_version_id: versionId,
        optimization_goal: goal,
        constraints,
        n_pipelines: nPipelines,
        force_regenerate: false,
      });
      setJob(result);
      setStatus("");
    } catch (err) {
      setStatus(err.response?.data?.detail || "Failed to create variant job");
    }
  };

  const activeJob = job || (existingJobs.length > 0 ? existingJobs[0] : null);
  const completedRecords = (activeJob?.records || []).filter(r => r.status === "completed");
  const failedRecords = (activeJob?.records || []).filter(r => r.status === "failed");
  const runningRecords = (activeJob?.records || []).filter(r => r.status === "running");
  const progressPct = activeJob?.total_variants_planned > 0
    ? Math.round(activeJob.total_variants_completed / activeJob.total_variants_planned * 100)
    : 0;

  if (!hasDiagnosis) {
    return (
      <div className="stack">
        <Notice>
          <strong>Diagnosis required before variant generation.</strong><br />
          Run data diagnosis on this version first, then return here to generate preprocessing variants.
        </Notice>
      </div>
    );
  }

  return (
    <div className="stack">
      {/* Header */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
          <Zap size={20} style={{ color: "#818cf8" }} />
          <h2 style={{ margin: 0 }}>Variant Generator</h2>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Automatically generate and evaluate candidate preprocessing pipelines for this dataset version.
          All scoring is deterministic — AI is not involved in ranking.
        </p>
      </Card>

      {/* Configuration */}
      <Card>
        <p className="eyebrow">Configuration</p>
        <h3>Optimisation Goal &amp; Constraints</h3>

        <div className="form-grid" style={{ marginBottom: 16 }}>
          <Field label="Optimisation Goal">
            <select id="variant-goal-select" value={goal} onChange={e => setGoal(e.target.value)}>
              {GOALS.map(g => (
                <option key={g.value} value={g.value}>{g.label} — {g.desc}</option>
              ))}
            </select>
          </Field>
          <Field label="Number of Pipelines (2–8)">
            <input
              id="variant-n-pipelines"
              type="number" min={2} max={8} value={nPipelines}
              onChange={e => setNPipelines(Math.min(8, Math.max(2, parseInt(e.target.value) || 4)))}
            />
          </Field>
          <Field label="Max Features (optional)">
            <input
              id="variant-max-features"
              type="number" min={1} placeholder="No limit"
              value={maxFeatures} onChange={e => setMaxFeatures(e.target.value)}
            />
          </Field>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, cursor: "pointer" }}>
          <input id="variant-avoid-synthetic" type="checkbox" checked={avoidSynthetic} onChange={e => setAvoidSynthetic(e.target.checked)} />
          <span>Avoid synthetic data (exclude SMOTE / ADASYN)</span>
        </label>

        <Button id="variant-generate-btn" onClick={handleGenerate} disabled={!versionId || activeJob?.status === "running"}>
          <Zap size={14} />
          Generate Variants
        </Button>

        {status && <Notice error={status.includes("Failed")} style={{ marginTop: 12 }}>{status}</Notice>}
      </Card>

      {/* Job status */}
      {activeJob && (
        <Card>
          <p className="eyebrow">Job Status</p>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 12, flexWrap: "wrap" }}>
            <h3 style={{ margin: 0 }}>Job #{activeJob.id}</h3>
            <Badge tone={
              activeJob.status === "completed" ? "success" :
              activeJob.status === "failed" ? "critical" :
              activeJob.status === "running" ? "warning" : "neutral"
            }>{activeJob.status}</Badge>
            <span className="muted" style={{ fontSize: 13 }}>Goal: {activeJob.optimization_goal}</span>
            {polling && <span style={{ color: "#f59e0b", fontSize: 12 }}>● Polling every 3s…</span>}
          </div>

          {activeJob.status === "running" && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 12 }}>
                <span className="muted">{activeJob.total_variants_completed} / {activeJob.total_variants_planned} pipelines complete</span>
                <span style={{ fontWeight: 600 }}>{progressPct}%</span>
              </div>
              <div style={{ background: "#1e293b", borderRadius: 4, height: 8 }}>
                <div style={{ width: `${progressPct}%`, background: "#818cf8", height: "100%", borderRadius: 4, transition: "width 0.4s" }} />
              </div>
            </div>
          )}

          {activeJob.error_message && (
            <Notice error style={{ marginTop: 8 }}>{activeJob.error_message}</Notice>
          )}

          {failedRecords.length > 0 && (
            <Notice style={{ marginTop: 8 }}>
              {failedRecords.length} pipeline(s) failed. See individual records below.
            </Notice>
          )}
        </Card>
      )}

      {/* Results */}
      {completedRecords.length > 0 && (
        <Card>
          <p className="eyebrow">Pipeline Rankings</p>
          <h3>{completedRecords.length} completed pipeline{completedRecords.length > 1 ? "s" : ""}</h3>
          <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            MLRS is a risk score — lower is better (↓ means improvement). VRS combines all components weighted by goal.
          </p>
          {completedRecords.map(record => (
            <VariantRecordRow
              key={record.id}
              record={record}
              jobId={activeJob.id}
              onRegistered={() => variantApi.getJob(activeJob.id).then(setJob)}
            />
          ))}
        </Card>
      )}

      {/* Existing jobs list */}
      {existingJobs.length > 1 && (
        <Card>
          <p className="eyebrow">Previous Jobs</p>
          <h3>Job history for this version</h3>
          <div className="context-list">
            {existingJobs.map(j => (
              <div key={j.id} className="context-row" style={{ cursor: "pointer" }} onClick={() => setJob(j)}>
                <strong>Job #{j.id} — {j.optimization_goal}</strong>
                <Badge tone={j.status === "completed" ? "success" : j.status === "failed" ? "critical" : "neutral"}>{j.status}</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}


