# FedRepro Feature Mapping

**Last updated:** 2026-08-16

This map connects product features to the active implementation files, API routes, UI entry points, documentation, and verification coverage. Use it as a quick audit checklist when docs or behavior change.

## Product Features

| Feature | Backend owner | API surface | Frontend owner | Documentation | Verification |
|---|---|---|---|---|---|
| Authentication | `backend/app/api/routes/auth.py`, `backend/app/core/security.py` | `POST /api/auth/register`, `POST /api/auth/login` | `frontend/src/pages/AuthPage.jsx`, `frontend/src/context/AuthContext.jsx` | `README.md`, `docs/UI_PAGE_GUIDE.md` | `backend/tests/test_api_workflow.py` |
| Dashboard | `ReportingService`, `studies.py` dashboard route | `GET /api/dashboard` | `frontend/src/pages/DashboardPage.jsx` | `README.md`, `docs/UI_PAGE_GUIDE.md`, `docs/UI_REFERENCE.md` | `backend/tests/test_api_workflow.py` |
| Study protocol and lineage | `StudyService`, `StudyConfigurationRepository`, `studies.py` | `/api/studies`, `/api/studies/{id}/configuration`, `/api/studies/{id}/configurations*` | `frontend/src/pages/StudiesPage.jsx`, `frontend/src/pages/StudyWorkspace.jsx` | `docs/REFINEMENT_1_IMPLEMENTATION_REPORT.md`, `docs/ARCHITECTURE.md` | `backend/tests/test_study_configuration_refinement.py` |
| Dataset registration and configuration | `DatasetWorkflowService`, `datasets.py`, `local_storage.py` | `POST /api/studies/{id}/datasets/register`, `POST /api/registrations/{id}/configure` | `StudyWorkspace.jsx`, `WorkspacePanels.jsx` | `README.md`, `docs/UI_PAGE_GUIDE.md` | `backend/tests/test_api_workflow.py`, `backend/tests/test_analysis_services.py` |
| Immutable versions and fingerprints | `FingerprintService`, `DatasetWorkflowService`, `datasets.py` | `GET /api/versions/{id}`, `GET /api/versions/{id}/recreation-bundle`, `POST /api/versions/recreate/verify` | `Versions & Fingerprints` panel in `WorkspacePanels.jsx` | `docs/ARCHITECTURE.md`, `docs/UI_REFERENCE.md` | `backend/tests/test_api_workflow.py`, `backend/tests/test_analysis_services.py` |
| Semantic diff, SCM, and DSI | `SemanticDiffService`, `datasets.py` | `GET /api/versions/{id}/semantic-diff`, `GET /api/versions/{id}/compare` | `StudyWorkspace.jsx`, `DiagnosisPanel` | `docs/ARCHITECTURE.md`, `docs/AGENT_KNOWLEDGE_BASE.md` | `backend/tests/test_analysis_services.py` |
| Profile and diagnosis evidence | `ProfilingService`, `DiagnosisService`, `DiagnosisContractService`, `datasets.py` | `GET /api/versions/{id}/profile`, `GET /api/versions/{id}/diagnosis`, `POST /api/versions/{id}/diagnosis/run`, `GET /api/versions/{id}/diagnosis-contract` | `DiagnosisPanel` in `WorkspacePanels.jsx` | `docs/UI_PAGE_GUIDE.md`, `docs/UI_REFERENCE.md` | `backend/tests/test_analysis_services.py`, `backend/tests/test_api_workflow.py` |
| Startup evidence warmup | `EvidenceWarmupService`, `backend/app/main.py` | Runs during FastAPI lifespan when enabled | Reflected through diagnosis status in workspace views | `README.md`, `docs/ARCHITECTURE.md`, `docs/AGENT_KNOWLEDGE_BASE.md` | Backend tests plus manual startup verification |
| Variant generation and promotion | `VariantGeneratorOrchestrator`, `VariantBuilderService`, `VariantEvaluatorService`, `variants.py` | `POST /api/versions/{id}/variant-jobs`, `GET /api/variant-jobs/{id}`, `POST /api/variant-jobs/{job_id}/records/{record_id}/register`, `GET /api/versions/{id}/variant-tree` | `VariantGeneratorPanel` in `WorkspacePanels.jsx` | `docs/VARIANT_GENERATOR_REPORT.md`, `docs/ARCHITECTURE.md` | `backend/tests/test_variant_services.py` |
| Reports and exports | `ExecutiveReportService`, `DiagnosisReportService`, `DatasetExplanationReportService`, `datasets.py`, `studies.py` | `GET /api/studies/{id}/executive-report`, `GET /api/versions/{id}/diagnosis-report`, `GET/POST /api/versions/{id}/explanation-report`, `GET /api/registrations/{id}/explanation-report` | Export actions in `StudyWorkspace.jsx` and `WorkspacePanels.jsx` | `README.md`, `docs/UI_PAGE_GUIDE.md` | `backend/tests/test_api_workflow.py` |
| Optional AI explanations | `InstantInsightService`, `AIContextBuilder`, `AIInsightJobService`, `AIExplanationService`, `ai.py` | `/api/versions/{id}/analysis`, `/api/ai/studies/{id}/...`, `ai_insight_jobs` | `aiApi` in `frontend/src/api/client.js`, diagnosis AI panel actions | `README.md`, `docs/ARCHITECTURE.md` | `backend/tests/test_ai_insight_jobs.py`; manual with local Ollama |
| Research findings overview | `ReportingService`, `studies.py` | `GET /api/studies/{id}/findings`, `GET /api/research-findings` | `frontend/src/pages/ResearchFindingsPage.jsx` | `docs/UI_PAGE_GUIDE.md`, `docs/UI_REFERENCE.md` | `backend/tests/test_api_workflow.py` |

## Maintained Utilities

| Utility | Status | Purpose |
|---|---|---|
| `tools/recompute_all_dataset_evidence.py` | Kept | Deliberate one-off recomputation across dataset versions |

Removed one-off local scripts during the 2026-08-16 cleanup:

- `tools/capture_chrome_page.js`
- `tools/generate_implementation_report.py`

## Current Documentation Set

| Document | Status |
|---|---|
| `README.md` | Current project overview and setup |
| `docs/ARCHITECTURE.md` | Current system architecture and API route inventory |
| `docs/UI_REFERENCE.md` | Current UI implementation reference |
| `docs/UI_PAGE_GUIDE.md` | Current user workflow guide |
| `docs/AGENT_KNOWLEDGE_BASE.md` | Current fast-load engineering reference |
| `docs/VARIANT_GENERATOR_REPORT.md` | Historical detailed implementation report for variant work; still matches active feature boundaries |
| `docs/REFINEMENT_1_IMPLEMENTATION_REPORT.md` | Historical detailed implementation report for protocol versioning; still matches active feature boundaries |
| `docs/TECHNICAL_IMPLEMENTATION_REPORT.md` | Detailed implementation assessment retained under docs |
| `docs/GITHUB_READY.md` | Git checklist retained under docs |

## Verification Commands

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm.cmd run build
```
