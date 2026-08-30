import type { ReactNode } from "react";
import { BackendStatus } from "../BackendStatus";
import { LogoMark, PlusIcon } from "../icons/Icons";
import { Button } from "../ui/Button";
import { NavItem } from "./PageLayout";
import { MAIN_NAV, SETTINGS_NAV, type AppView } from "../../types/navigation";
import type { BackendHealthStatus } from "../../hooks/useBackendHealth";
import {
  ChatIcon,
  FolderIcon,
  HomeIcon,
  SettingsIcon,
} from "../icons/Icons";
import "./layout.css";

const ICONS: Record<AppView, ReactNode> = {
  home: <HomeIcon />,
  projects: <FolderIcon />,
  chat: <ChatIcon />,
  settings: <SettingsIcon />,
};

interface SidebarProps {
  activeView: AppView;
  onNavigate: (view: AppView) => void;
  backendStatus: BackendHealthStatus;
  onBackendRetry: () => void;
}

export function Sidebar({
  activeView,
  onNavigate,
  backendStatus,
  onBackendRetry,
}: SidebarProps) {
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden="true">
          <LogoMark />
        </span>
        <span className="sidebar__wordmark">OverHaust</span>
      </div>

      <div className="sidebar__actions">
        <Button
          variant="primary"
          size="md"
          icon={<PlusIcon width={16} height={16} />}
          className="sidebar__new-btn"
        >
          New Project
        </Button>
      </div>

      <nav className="sidebar__nav">
        {MAIN_NAV.map((item) => (
          <NavItem
            key={item.id}
            label={item.label}
            icon={ICONS[item.id]}
            active={activeView === item.id}
            onClick={() => onNavigate(item.id)}
          />
        ))}
      </nav>

      <div className="sidebar__footer">
        <BackendStatus status={backendStatus} onRetry={onBackendRetry} />
        <div className="sidebar__divider" role="separator" />
        <NavItem
          label={SETTINGS_NAV.label}
          icon={ICONS.settings}
          active={activeView === SETTINGS_NAV.id}
          onClick={() => onNavigate(SETTINGS_NAV.id)}
        />
      </div>
    </aside>
  );
}

interface AppShellProps {
  activeView: AppView;
  onNavigate: (view: AppView) => void;
  backendStatus: BackendHealthStatus;
  onBackendRetry: () => void;
  children: ReactNode;
}

export function AppShell({
  activeView,
  onNavigate,
  backendStatus,
  onBackendRetry,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar
        activeView={activeView}
        onNavigate={onNavigate}
        backendStatus={backendStatus}
        onBackendRetry={onBackendRetry}
      />
      <main className="app-main">{children}</main>
    </div>
  );
}
