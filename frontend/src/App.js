import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { Toaster } from 'sonner';
import '@/App.css';

import { AuthProvider, useAuth } from '@/lib/auth';
import Landing from '@/pages/Landing';
import Login from '@/pages/Login';
import Dashboard from '@/pages/Dashboard';
import Projects from '@/pages/Projects';
import ProjectDetail from '@/pages/ProjectDetail';
import AIMemory from '@/pages/AIMemory';
import Usage from '@/pages/Usage';
import Connections from '@/pages/Connections';
import Settings from '@/pages/Settings';
import AppShell from '@/components/AppShell';

const RequireAuth = () => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[color:var(--bg-950)] text-[color:var(--ink-400)]">
        <span className="font-mono text-sm">Loading your AI memory…</span>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
};

function App() {
  return (
    <div className="App dark">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route element={<RequireAuth />}>
              <Route path="/app" element={<AppShell />}>
                <Route index element={<Dashboard />} />
                <Route path="projects" element={<Projects />} />
                <Route path="projects/:id" element={<ProjectDetail />} />
                <Route path="memory" element={<AIMemory />} />
                <Route path="usage" element={<Usage />} />
                <Route path="connections" element={<Connections />} />
                <Route path="settings" element={<Settings />} />
                {/* Back-compat redirects for old paths */}
                <Route path="analytics" element={<Navigate to="/app/usage" replace />} />
                <Route path="integrations" element={<Navigate to="/app/connections" replace />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: 'hsl(var(--popover))',
              color: 'hsl(var(--popover-foreground))',
              border: '1px solid hsl(var(--border))',
            },
          }}
        />
      </AuthProvider>
    </div>
  );
}

export default App;
