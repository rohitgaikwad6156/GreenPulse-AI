import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BookOpenText,
  ChartNoAxesCombined,
  ChevronRight,
  CircleHelp,
  FlaskConical,
  LayoutDashboard,
  Map,
  Menu,
  PanelLeftClose,
  RadioTower,
  SlidersHorizontal,
  Sprout,
} from "lucide-react";

const navigation = [
  { label: "Overview", path: "/", icon: LayoutDashboard },
  { label: "Heat Map", path: "/heat-map", icon: Map },
  { label: "Root Cause Analysis", path: "/root-cause", icon: ChartNoAxesCombined },
  { label: "Scenario Simulator", path: "/scenario-simulator", icon: SlidersHorizontal },
  { label: "Climate Action Optimizer", path: "/climate-action-optimizer", icon: Sprout },
  { label: "Validation", path: "/validation", icon: Activity },
  { label: "Research Layers", path: "/research-layers", icon: RadioTower },
  { label: "Methodology", path: "/methodology", icon: BookOpenText },
];

function Sidebar({ onNavigate, onClose }) {
  return (
    <div className="flex h-full flex-col border-r border-[#e5ebe4] bg-white">
      <div className="flex h-20 items-center justify-between border-b border-[#edf1eb] px-5">
        <Link to="/" onClick={onNavigate} className="flex items-center gap-3" aria-label="GreenPulse AI overview">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#e8f2e9] text-[#2e714c]">
            <Sprout size={22} strokeWidth={2.1} aria-hidden="true" />
          </span>
          <span className="leading-tight">
            <span className="block text-[17px] font-bold tracking-tight text-[#193b2a]">GreenPulse AI</span>
            <span className="block text-[10px] font-semibold uppercase tracking-[0.17em] text-[#7b9181]">Climate planning</span>
          </span>
        </Link>
        <button onClick={onClose} className="rounded-lg p-2 text-[#698073] hover:bg-[#f2f6f1] lg:hidden" aria-label="Close menu">
          <PanelLeftClose size={20} aria-hidden="true" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-6">
        <p className="px-3 pb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-[#9aaa9e]">Workspace</p>
        <nav aria-label="Main navigation" className="space-y-1">
          {navigation.map(({ label, path, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              onClick={onNavigate}
              className={({ isActive }) =>
                `group flex min-h-11 items-center gap-3 rounded-lg px-3 text-[13px] font-medium transition-colors ${
                  isActive
                    ? "bg-[#eaf4eb] text-[#246442]"
                    : "text-[#63766a] hover:bg-[#f3f7f2] hover:text-[#244a34]"
                }`
              }
            >
              <Icon size={18} strokeWidth={1.9} aria-hidden="true" />
              <span className="flex-1">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="border-t border-[#edf1eb] p-4">
        <div className="rounded-xl border border-[#e4ebe2] bg-[#f7faf6] p-3.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-[#315f43]">
            <CircleHelp size={15} aria-hidden="true" />
            Research workspace
          </div>
          <p className="mt-2 text-[11px] leading-5 text-[#728577]">
            Follow the overview to check inputs, then explore heat, explanations, scenarios, planning and validation.
          </p>
        </div>
      </div>
    </div>
  );
}

export default function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const currentPage = navigation.find((item) => item.path === pathname)?.label ?? "Overview";

  return (
    <div className="min-h-screen bg-[#f6f8f5]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 lg:block">
        <Sidebar onNavigate={() => setMenuOpen(false)} onClose={() => setMenuOpen(false)} />
      </aside>

      {menuOpen && (
        <div className="fixed inset-0 z-[2000] isolate lg:hidden">
          <button
            className="absolute inset-0 z-[2000] bg-[#153026]/35"
            aria-label="Close navigation"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="relative z-[2100] h-full w-72 max-w-[85vw] shadow-xl">
            <Sidebar onNavigate={() => setMenuOpen(false)} onClose={() => setMenuOpen(false)} />
          </aside>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#e5ebe4] bg-white/95 px-4 backdrop-blur sm:px-7 lg:px-9">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setMenuOpen(true)}
              className="rounded-lg p-2 text-[#496453] hover:bg-[#f2f6f1] lg:hidden"
              aria-label="Open menu"
              aria-expanded={menuOpen}
            >
              <Menu size={21} aria-hidden="true" />
            </button>
            <span className="hidden text-xs font-medium text-[#8c9b91] sm:inline">Workspace</span>
            <ChevronRight size={14} className="hidden text-[#b5c0b8] sm:inline" aria-hidden="true" />
            <span className="truncate text-sm font-semibold text-[#314d3b]">{currentPage}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden rounded-full border border-[#e7ede6] bg-[#f9fbf8] px-3 py-1.5 text-[11px] font-medium text-[#607467] sm:inline-flex">
              Pune / PCMC study area
            </span>
            <Link to="/" className="inline-flex items-center gap-2 rounded-full border border-[#e5ebe4] bg-white px-3 py-1.5 text-[11px] font-semibold text-[#61776a]">
              <span className="h-1.5 w-1.5 rounded-full bg-[#bb9b50]" />
              Research status
            </Link>
          </div>
        </header>

        <main id="main-content" className="mx-auto max-w-[1500px] px-4 py-7 sm:px-7 sm:py-9 lg:px-9">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
