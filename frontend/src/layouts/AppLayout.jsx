import { useEffect, useState } from "react";
import {
  BarChart3,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  Database,
  LogOut,
  Menu,
  PanelLeftClose,
  Workflow,
  X
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ThemeToggle } from "../components/UI";

const navigation = [
  { label: "Dashboard",         description: "Research overview",       to: "/dashboard", icon: BarChart3    },
  { label: "ML Studies",        description: "Evidence workspaces",     to: "/studies",   icon: Database     },
  { label: "Research Findings", description: "Consolidated results",    to: "/findings",  icon: BookOpenCheck },
];

const routeTitles = {
  "/dashboard": ["Research dashboard",   "Phase I evidence console"],
  "/studies":   ["ML studies",           "Dataset research workspaces"],
  "/findings":  ["Research findings",    "Consolidated deterministic evidence"],
};

export default function AppLayout() {
  const { logout } = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();
  const [collapsed,   setCollapsed]   = useState(false);
  const [mobileOpen,  setMobileOpen]  = useState(false);

  const isWorkspace = location.pathname.startsWith("/studies/");
  const title = isWorkspace
    ? ["Study workspace", "Version-aware dataset research"]
    : (routeTitles[location.pathname] || ["FedRepro", "Data-centric ML research"]);

  // Apply persisted theme on mount to avoid FOUC
  useEffect(() => {
    try {
      const saved = localStorage.getItem("fedrepro-theme");
      if (saved) document.documentElement.setAttribute("data-theme", saved);
    } catch {}
  }, []);

  // Close mobile nav on route change
  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  const signOut = () => { logout(); navigate("/login"); };

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      {/* Mobile scrim */}
      {mobileOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* ── Sidebar ── */}
      <aside className={`sidebar${mobileOpen ? " mobile-open" : ""}`} aria-label="Main navigation">
        <div className="sidebar-brand">
          <NavLink className="brand" to="/dashboard" aria-label="FedRepro home">
            <span className="brand-mark" aria-hidden="true">
              <Workflow size={19} strokeWidth={2.2} />
            </span>
            {!collapsed && (
              <span className="brand-copy">
                <strong>FedRepro</strong>
                <small>Research Console</small>
              </span>
            )}
          </NavLink>
          <button
            className="icon-button mobile-close"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <div className="nav-section">
          {!collapsed && <p className="nav-label">Workspace</p>}
          <nav className="side-nav" aria-label="Primary navigation">
            {navigation.map(({ label, description, to, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => isActive ? "active" : ""}
                title={collapsed ? label : undefined}
                aria-label={collapsed ? label : undefined}
              >
                <Icon size={17} strokeWidth={2} aria-hidden="true" />
                {!collapsed && (
                  <span>
                    <strong>{label}</strong>
                    <small>{description}</small>
                  </span>
                )}
                {!collapsed && <ChevronRight className="nav-chevron" size={14} aria-hidden="true" />}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="sidebar-foot">
          {!collapsed && (
            <div className="phase-card">
              <span className="status-dot" aria-label="System active" />
              <div>
                <strong>Phase I Active</strong>
                <small>Deterministic evidence pipeline</small>
              </div>
            </div>
          )}
          <button
            className="collapse-button"
            onClick={() => setCollapsed(c => !c)}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
            title={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {collapsed
              ? <ChevronRight size={16} aria-hidden="true" />
              : <><PanelLeftClose size={16} aria-hidden="true" /><span>Collapse</span></>}
          </button>
        </div>
      </aside>

      {/* ── Main column ── */}
      <div className="app-column">
        {/* Topbar */}
        <header className="topbar" role="banner">
          <div className="topbar-context">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} aria-hidden="true" />
            </button>
            <div>
              <strong>{title[0]}</strong>
              <span>{title[1]}</span>
            </div>
          </div>

          <div className="topbar-actions">
            <ThemeToggle />
            <div className="researcher-chip" aria-label="Signed-in researcher">
              <span aria-hidden="true">FR</span>
              <div>
                <strong>Researcher</strong>
                <small>Authenticated</small>
              </div>
            </div>
            <button
              className="button secondary compact"
              onClick={signOut}
              aria-label="Sign out"
            >
              <LogOut size={14} aria-hidden="true" />
              Sign out
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="page" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
