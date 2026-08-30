import { useState } from "react";
import { AppShell } from "./components/layout/AppShell";
import { PageHeader, viewTitle } from "./components/layout/PageLayout";
import { useBackendHealth } from "./hooks/useBackendHealth";
import { ChatPage } from "./pages/ChatPage";
import { HomePage } from "./pages/HomePage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SettingsPage } from "./pages/SettingsPage";
import type { AppView } from "./types/navigation";

const VIEW_DESCRIPTIONS: Partial<Record<AppView, string>> = {
  home: "Your starting point for exploring indexed codebases.",
  projects: "Manage repositories indexed by OverHaust.",
  chat: "Ask questions and trace flows across your project.",
  settings: "Preferences for appearance, workspace, and backend.",
};

function ActivePage({
  view,
  backendStatus,
  onBackendRetry,
}: {
  view: AppView;
  backendStatus: ReturnType<typeof useBackendHealth>["status"];
  onBackendRetry: () => void;
}) {
  switch (view) {
    case "home":
      return <HomePage />;
    case "projects":
      return <ProjectsPage />;
    case "chat":
      return <ChatPage />;
    case "settings":
      return (
        <SettingsPage backendStatus={backendStatus} onBackendRetry={onBackendRetry} />
      );
  }
}

export default function App() {
  const [activeView, setActiveView] = useState<AppView>("home");
  const { status: backendStatus, retry: onBackendRetry } = useBackendHealth();

  return (
    <AppShell
      activeView={activeView}
      onNavigate={setActiveView}
      backendStatus={backendStatus}
      onBackendRetry={onBackendRetry}
    >
      <PageHeader
        title={viewTitle(activeView)}
        description={VIEW_DESCRIPTIONS[activeView]}
      />
      <ActivePage
        view={activeView}
        backendStatus={backendStatus}
        onBackendRetry={onBackendRetry}
      />
    </AppShell>
  );
}
