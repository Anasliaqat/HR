import {
  Bell,
  BriefcaseBusiness,
  CalendarDays,
  ChevronLeft,
  ChevronDown,
  FileSearch,
  LayoutDashboard,
  Mail,
  Menu,
  Moon,
  Search,
  Sun,
  UsersRound,
  Voicemail,
  Settings,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../services/api";

const navigation = [
  { label: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
  { label: "Evaluate CV", to: "/", icon: FileSearch },
  { label: "Jobs", to: "/jobs", icon: BriefcaseBusiness },
  { label: "Candidates", to: "/candidates", icon: UsersRound },
  { label: "Screening", to: "/screening", icon: Voicemail },
  { label: "Interviews", to: "/interviews", icon: CalendarDays },
  { label: "Email automation", to: "/email-automation", icon: Mail },
];

const pageNames = {
  "/": "Evaluate CV",
  "/dashboard": "Dashboard",
  "/jobs": "Jobs",
  "/candidates": "Candidates",
  "/resumes": "Resume evaluation",
  "/screening": "Screening",
  "/interviews": "Interviews",
  "/email-automation": "Email automation",
  "/settings": "Settings",
};

function getStoredTheme() {
  try {
    return window.localStorage.getItem("hireflow.theme") === "light"
      ? "light"
      : "dark";
  } catch {
    return "dark";
  }
}

export default function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const searchInput = useRef(null);
  const currentPage = pageNames[location.pathname] ?? "Hiring workspace";
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState(getStoredTheme);
  const [search, setSearch] = useState("");
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationData, setNotificationData] = useState(null);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [notificationError, setNotificationError] = useState("");

  const filteredPages = useMemo(() => {
    const query = search.trim().toLowerCase();
    return navigation.filter(({ label }) => !query || label.toLowerCase().includes(query));
  }, [search]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("hireflow.theme", theme);
    } catch {
      // Theme still applies for this session when browser storage is unavailable.
    }
  }, [theme]);

  useEffect(() => {
    setSearch("");
    setNotificationsOpen(false);
    setProfileOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function handleSearchShortcut(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInput.current?.focus();
      }
    }
    window.addEventListener("keydown", handleSearchShortcut);
    return () => window.removeEventListener("keydown", handleSearchShortcut);
  }, []);

  useEffect(() => {
    if (!notificationsOpen || notificationData) return undefined;
    let active = true;
    setNotificationLoading(true);
    setNotificationError("");
    Promise.all([api.getCandidates(), api.getInterviews()])
      .then(([candidates, interviews]) => {
        if (active) setNotificationData({ candidates, interviews });
      })
      .catch((error) => {
        if (active) setNotificationError(error.message);
      })
      .finally(() => {
        if (active) setNotificationLoading(false);
      });
    return () => {
      active = false;
    };
  }, [notificationsOpen, notificationData]);

  const reviewCount =
    notificationData?.candidates?.filter((candidate) => !candidate.hr_approved).length ?? 0;
  const upcomingCount =
    notificationData?.interviews?.filter(
      (interview) =>
        interview.status === "scheduled" &&
        new Date(interview.start_at).getTime() >= Date.now(),
    ).length ?? 0;
  const notificationCount = reviewCount + upcomingCount;

  function submitSearch(event) {
    event.preventDefault();
    if (!filteredPages.length) return;
    navigate(filteredPages[0].to);
    setSearch("");
  }

  return (
    <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="sidebar-brand-row">
          <NavLink className="brand" to="/" aria-label="Hireflow home">
            <span className="brand-mark">H</span>
            <span className="brand-copy">
              <strong>HR ASSISTANT</strong>
              <small>HR workspace</small>
            </span>
          </NavLink>
          <button
            type="button"
            className="icon-button sidebar-collapse-button"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setCollapsed((value) => !value)}
          >
            {collapsed ? <Menu size={17} /> : <ChevronLeft size={17} />}
          </button>
        </div>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {navigation.map(({ label, to, icon: Icon }) => (
            <NavLink
              key={to}
              end={to === "/"}
              to={to}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `nav-link${isActive ? " active" : ""}`
              }
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <span className="online-dot" />
          <span>
            <strong>HR review enabled</strong>
            <small>AI is advisory only</small>
          </span>
        </div>
        <NavLink
          to="/settings"
          title={collapsed ? "Settings" : undefined}
          className={({ isActive }) =>
            `nav-link settings-link${isActive ? " active" : ""}`
          }
        >
          <Settings size={18} strokeWidth={1.8} />
          <span>Settings</span>
        </NavLink>
        <div className="sidebar-profile">
          <span className="avatar">HR</span>
          <span className="profile-copy">
            <strong>HR workspace</strong>
            <small>Administrator</small>
          </span>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="icon-button mobile-nav-toggle"
              aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
              onClick={() => setCollapsed((value) => !value)}
            >
              <Menu size={18} />
            </button>
            <div className="breadcrumbs">
              Workspace <span>/</span> <strong>{currentPage}</strong>
            </div>
          </div>
          <div className="topbar-meta">
            <form className="global-search" role="search" onSubmit={submitSearch}>
              <Search size={16} />
              <input
                ref={searchInput}
                aria-label="Search workspace pages"
                placeholder="Search pages..."
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onFocus={() => setNotificationsOpen(false)}
              />
              <kbd>Ctrl/⌘ K</kbd>
              {search && (
                <div className="global-search-results">
                  {filteredPages.length ? filteredPages.map(({ label, to, icon: Icon }) => (
                    <NavLink key={to} to={to} onClick={() => setSearch("")}>
                      <Icon size={16} /> {label}
                    </NavLink>
                  )) : <span className="search-no-results">No matching pages</span>}
                </div>
              )}
            </form>
            <div className="topbar-control-wrap">
              <button
                type="button"
                className={`icon-button topbar-control${notificationsOpen ? " active" : ""}`}
                aria-label={`Notifications${notificationCount ? `, ${notificationCount} items` : ""}`}
                aria-expanded={notificationsOpen}
                onClick={() => {
                  setNotificationsOpen((value) => !value);
                  setProfileOpen(false);
                }}
              >
                <Bell size={17} />
                {notificationCount > 0 && <span className="notification-dot" />}
              </button>
              {notificationsOpen && (
                <section className="popover notification-popover" aria-label="Notifications">
                  <div className="popover-heading">
                    <strong>Notifications</strong>
                    <span>{notificationCount} updates</span>
                  </div>
                  {notificationLoading ? (
                    <p className="popover-message">Loading workspace updates…</p>
                  ) : notificationError ? (
                    <p className="popover-error">{notificationError}</p>
                  ) : (
                    <>
                      <NavLink to="/candidates" className="notification-item">
                        <span className="notification-item-icon"><UsersRound size={16} /></span>
                        <span><strong>{reviewCount} candidates need review</strong><small>Check applications awaiting an HR decision</small></span>
                      </NavLink>
                      <NavLink to="/interviews" className="notification-item">
                        <span className="notification-item-icon notification-violet"><CalendarDays size={16} /></span>
                        <span><strong>{upcomingCount} upcoming interviews</strong><small>View your scheduled conversations</small></span>
                      </NavLink>
                    </>
                  )}
                  <button
                    type="button"
                    className="popover-refresh"
                    onClick={() => setNotificationData(null)}
                  >
                    Refresh updates
                  </button>
                </section>
              )}
            </div>
            <button
              type="button"
              className="icon-button topbar-control theme-toggle"
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              onClick={() => setTheme((value) => value === "dark" ? "light" : "dark")}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <div className="topbar-control-wrap profile-menu-wrap">
              <button
                type="button"
                className="profile-trigger"
                aria-label="Open profile menu"
                aria-expanded={profileOpen}
                onClick={() => {
                  setProfileOpen((value) => !value);
                  setNotificationsOpen(false);
                }}
              >
                <span className="avatar avatar-small">HR</span>
                <ChevronDown size={14} />
              </button>
              {profileOpen && (
                <div className="popover profile-popover">
                  <div className="profile-popover-copy"><strong>HR workspace</strong><small>Administrator</small></div>
                  <NavLink to="/settings"><Settings size={15} /> Workspace settings</NavLink>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>Hireflow · AI-assisted, human-led hiring</span>
          <span>Candidate decisions always require HR review</span>
        </footer>
      </div>
    </div>
  );
}
