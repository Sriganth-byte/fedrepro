import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";

const AppLayout = lazy(() => import("./layouts/AppLayout"));
const AuthPage = lazy(() => import("./pages/AuthPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const ResearchFindingsPage = lazy(() => import("./pages/ResearchFindingsPage"));
const StudiesPage = lazy(() => import("./pages/StudiesPage"));
const StudyWorkspace = lazy(() => import("./pages/StudyWorkspace"));

function Protected({children}){const {authenticated}=useAuth();return authenticated?children:<Navigate to="/login" replace/>;}
export default function App(){return <Suspense fallback={<p className="muted">Loading FedRepro…</p>}><Routes><Route path="/login" element={<AuthPage/>}/><Route element={<Protected><AppLayout/></Protected>}><Route index element={<Navigate to="/dashboard" replace/>}/><Route path="dashboard" element={<DashboardPage/>}/><Route path="studies" element={<StudiesPage/>}/><Route path="studies/:studyId" element={<StudyWorkspace/>}/><Route path="findings" element={<ResearchFindingsPage/>}/></Route><Route path="*" element={<Navigate to="/dashboard" replace/>}/></Routes></Suspense>;}
