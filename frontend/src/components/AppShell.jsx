import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BookOpenText,
  ChartNoAxesCombined,
  ChevronRight,
  LayoutDashboard,
  Map,
  Menu,
  X,
  RadioTower,
  SlidersHorizontal,
  Sprout,
} from "lucide-react";

const navigation = [
  { label: "Overview", path: "/", icon: LayoutDashboard },
  { label: "Heat Map", path: "/heat-map", icon: Map },
  {
    label: "Root Cause Analysis",
    path: "/root-cause",
    icon: ChartNoAxesCombined,
  },
  {
    label: "Scenario Simulator",
    path: "/scenario-simulator",
    icon: SlidersHorizontal,
  },
  {
    label: "Climate Action Optimizer",
    path: "/climate-action-optimizer",
    icon: Sprout,
  },
  { label: "Validation", path: "/validation", icon: Activity },
  { label: "Research Layers", path: "/research-layers", icon: RadioTower },
  { label: "Methodology", path: "/methodology", icon: BookOpenText },
];

function Sidebar({ onNavigate, onClose }) {
  return (
    <div className="workspace-sidebar">
      <div className="sidebar-brand">
        <Link to="/" onClick={onNavigate} aria-label="GreenPulse AI overview">
          <span className="brand-mark">
            <Sprout size={25} aria-hidden="true" />
          </span>
          <span>
            <strong>GreenPulse AI</strong>
            <small>Climate planning</small>
          </span>
        </Link>
        {onClose && (
          <button
            onClick={onClose}
            className="icon-button"
            aria-label="Close menu"
          >
            <X size={21} />
          </button>
        )}
      </div>
      <nav aria-label="Main navigation" className="sidebar-navigation">
        {navigation.map(({ label, path, icon: Icon }, index) => (
          <div key={path}>
            {[0, 3, 6].includes(index) && (
              <p className="nav-group">
                {index === 0
                  ? "Explore"
                  : index === 3
                    ? "Plan & evaluate"
                    : "Reference"}
              </p>
            )}
            <NavLink
              to={path}
              end={path === "/"}
              onClick={onNavigate}
              className={({ isActive }) =>
                `nav-item ${isActive ? "is-active" : ""}`
              }
            >
              <Icon size={19} strokeWidth={1.7} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          </div>
        ))}
      </nav>
      <div className="sidebar-note">
        <span className="eyebrow">Evidence before action</span>
        <p>
          A research workspace for understanding surface heat and exploring
          climate interventions.
        </p>
        <Link to="/methodology" onClick={onNavigate}>
          Our methods & limitations{" "}
          <ChevronRight size={15} aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}

export default function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const dialog = useRef(null);
  const main = useRef(null);
  const previousPath = useRef(null);
  const { pathname } = useLocation();
  const currentPage =
    navigation.find((item) => item.path === pathname)?.label ?? "Overview";
  useEffect(() => {
    document.title = `${currentPage} · GreenPulse AI`;
    if (previousPath.current !== null && previousPath.current !== pathname) {
      window.scrollTo(0, 0);
      main.current?.focus({ preventScroll: true });
    }
    previousPath.current = pathname;
  }, [pathname, currentPage]);
  useEffect(() => {
    if (!menuOpen) return;
    dialog.current.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const query = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => {
      if (query.matches) setMenuOpen(false);
    };
    query.addEventListener("change", closeOnDesktop);
    return () => {
      dialog.current?.close();
      document.body.style.overflow = overflow;
      query.removeEventListener("change", closeOnDesktop);
    };
  }, [menuOpen]);
  return (
    <div className="workspace">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className="desktop-sidebar">
        <Sidebar />
      </aside>
      <dialog
        ref={dialog}
        className="mobile-navigation"
        aria-label="Workspace navigation"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const items = [
            ...event.currentTarget.querySelectorAll(
              "a[href], button:not([disabled])",
            ),
          ];
          const first = items[0];
          const last = items[items.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
        onClose={() => setMenuOpen(false)}
        onClick={(event) => {
          if (event.target === dialog.current) setMenuOpen(false);
        }}
      >
        <Sidebar
          onNavigate={() => {
            dialog.current.close();
            setMenuOpen(false);
          }}
          onClose={() => setMenuOpen(false)}
        />
      </dialog>
      <div className="workspace-body">
        <header className="workspace-header">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setMenuOpen(true)}
              className="icon-button lg:hidden"
              aria-label="Open menu"
              aria-expanded={menuOpen}
              aria-haspopup="dialog"
            >
              <Menu size={22} aria-hidden="true" />
            </button>
            <span className="hidden text-sm text-[#63736a] sm:inline">
              Workspace
            </span>
            <ChevronRight
              size={14}
              className="hidden text-[#63736a] sm:inline"
              aria-hidden="true"
            />
            <span className="truncate text-sm font-semibold">
              {currentPage}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-5">
            <span className="hidden text-xs text-[#63736a] xl:inline">
              Pune / PCMC study area
            </span>
            <Link to="/" className="research-link">
              Research workspace
            </Link>
          </div>
        </header>
        <main
          id="main-content"
          ref={main}
          tabIndex={-1}
          className="workspace-content"
        >
          <Outlet />
        </main>
        <footer className="workspace-footer">
          GreenPulse AI{" "}
          <span>Research informs decisions. Evidence comes first.</span>
        </footer>
      </div>
    </div>
  );
}
