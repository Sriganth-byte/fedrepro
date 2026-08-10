import axios from "axios";

const api = axios.create({ baseURL: "/api", timeout: 660000 });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("fedrepro_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
api.interceptors.response.use((response) => response, (error) => {
  if (error.response?.status === 401) {
    localStorage.removeItem("fedrepro_token");
    if (window.location.pathname !== "/login") window.location.assign("/login");
  }
  return Promise.reject(error);
});

export const authApi = {
  login: (payload) => api.post("/auth/login", payload).then((r) => r.data),
  register: (payload) => api.post("/auth/register", payload).then((r) => r.data)
};
export const dashboardApi = { get: () => api.get("/dashboard").then((r) => r.data) };
export const studyApi = {
  list: (search = "", mlTask = "") => api.get("/studies", { params: { ...(search ? { search } : {}), ...(mlTask ? { ml_task: mlTask } : {}) } }).then((r) => r.data),
  get: (id) => api.get(`/studies/${id}`).then((r) => r.data),
  create: (payload) => api.post("/studies", payload).then((r) => r.data),
  update: (id, payload) => api.patch(`/studies/${id}`, payload).then((r) => r.data),
  currentConfiguration: (id) => api.get(`/studies/${id}/configuration`).then((r) => r.data),
  configurationHistory: (id) => api.get(`/studies/${id}/configurations`).then((r) => r.data),
  createConfiguration: (id, payload) => api.post(`/studies/${id}/configurations`, payload).then((r) => r.data),
  executiveReport: (id, includeAi = false) => api.get(`/studies/${id}/executive-report`, { params: { include_ai: includeAi }, responseType: "blob" }).then((r) => r.data),
  findings: (id) => api.get(`/studies/${id}/findings`).then((r) => r.data),
  allFindings: () => api.get("/research-findings").then((r) => r.data),
  // Refinement #1: fetch a specific version by version number
  configurationByVersion: (studyId, versionNumber) =>
    api.get(`/studies/${studyId}/configurations/${versionNumber}`).then((r) => r.data),
  // Refinement #1: field-level diff between two protocol versions
  configurationDiff: (studyId, fromVersion, toVersion) =>
    api.get(`/studies/${studyId}/configurations/diff`, {
      params: { from_version: fromVersion, to_version: toVersion },
    }).then((r) => r.data),
};
export const datasetApi = {
  list: (studyId) => api.get(`/studies/${studyId}/datasets`).then((r) => r.data),
  register: (studyId, data, progress) => api.post(`/studies/${studyId}/datasets/register`, data, { onUploadProgress: progress }).then((r) => r.data),
  configure: (registrationId, payload) => api.post(`/registrations/${registrationId}/configure`, payload).then((r) => r.data),
  registrationReport: (registrationId) => api.get(`/registrations/${registrationId}/explanation-report`).then((r) => r.data),
  version: (versionId) => api.get(`/versions/${versionId}`).then((r) => r.data),
  versionEvidenceReport: (versionId) => api.get(`/versions/${versionId}/explanation-report`).then((r) => r.data),
  generateVersionEvidenceReport: (versionId) => api.post(`/versions/${versionId}/explanation-report/generate`).then((r) => r.data),
  analysis: (versionId) => api.get(`/versions/${versionId}/analysis`).then((r) => r.data),
  deleteVersion: (versionId) => api.delete(`/versions/${versionId}`),
  diff: (versionId) => api.get(`/versions/${versionId}/semantic-diff`).then((r) => r.data),
  compare: (versionId, againstVersionId) => api.get(`/versions/${versionId}/compare`, { params: { against_version_id: againstVersionId } }).then((r) => r.data),
  recreationBundle: (versionId) => api.get(`/versions/${versionId}/recreation-bundle`).then((r) => r.data),
  verifyRecreation: (data) => api.post("/versions/recreate/verify", data).then((r) => r.data),
  profile: (versionId) => api.get(`/versions/${versionId}/profile`).then((r) => r.data),
  diagnosis: (versionId) => api.get(`/versions/${versionId}/diagnosis`).then((r) => r.data),
  diagnosisContract: (versionId) => api.get(`/versions/${versionId}/diagnosis-contract`).then((r) => r.data),
  diagnosisReport: (versionId) => api.get(`/versions/${versionId}/diagnosis-report`, { responseType: "blob" }).then((r) => r.data)
};
export const aiApi = {
  explain: (studyId, payload) => api.post(`/ai/studies/${studyId}/explain`, payload).then((r) => r.data),
  semanticMetrics: (studyId, diffId) => api.post(`/ai/studies/${studyId}/semantic-diffs/${diffId}/metrics-interpretation`).then((r) => r.data),
  semanticDiffInterpretation: (studyId, diffId) => api.post(`/ai/studies/${studyId}/semantic-diffs/${diffId}/interpretation`).then((r) => r.data),
  versionExecutiveSummary: (studyId, versionId) => api.post(`/ai/studies/${studyId}/versions/${versionId}/executive-summary`).then((r) => r.data),
  diagnosisInterpretation: (studyId, versionId) => api.post(`/ai/studies/${studyId}/versions/${versionId}/diagnosis-interpretation`).then((r) => r.data)
};
export const variantApi = {
  createJob: (versionId, payload) => api.post(`/versions/${versionId}/variant-jobs`, payload).then((r) => r.data),
  listJobs: (versionId) => api.get(`/versions/${versionId}/variant-jobs`).then((r) => r.data),
  getJob: (jobId) => api.get(`/variant-jobs/${jobId}`).then((r) => r.data),
  registerVariant: (jobId, recordId, payload) => api.post(`/variant-jobs/${jobId}/records/${recordId}/register`, payload).then((r) => r.data),
  variantTree: (versionId) => api.get(`/versions/${versionId}/variant-tree`).then((r) => r.data),
};

