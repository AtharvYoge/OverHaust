import React from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  Layers,
  ListTodo,
  LineChart,
  Plug,
  Settings as SettingsIcon,
  Command,
  LogOut,
  Plus,
  Database,
  Sparkles,
} from 'lucide-react';
import { NAV } from '@/constants/testIds';
import { useAuth } from '@/lib/auth';
import { ProjectAPI } from '@/lib/api';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import LocalCacheStatus from '@/components/LocalCacheStatus';

const navItems = [
  { to: '/app', end: true, icon: LayoutDashboard, label: 'Overview', tid: NAV.overview },
  { to: '/app/projects', icon: FolderKanban, label: 'Projects', tid: NAV.projects },
  { to: '/app/analytics', icon: LineChart, label: 'Analytics', tid: NAV.analytics },
  { to: '/app/integrations', icon: Plug, label: 'Integrations', tid: NAV.integrations },
  { to: '/app/settings', icon: SettingsIcon, label: 'Settings', tid: NAV.settings },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleSeed = async () => {
    try {
      const proj = await ProjectAPI.seedLabkot();
      toast.success('LabKOT demo loaded', { description: 'Preloaded project + realistic conversation.' });
      navigate(`/app/projects/${proj.id}`);
    } catch (e) {
      toast.error('Failed to load demo', { description: String(e?.message || e) });
    }
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen bg-[color:var(--bg-950)] text-[color:var(--ink-50)] flex">
        {/* Sidebar */}
        <aside className="hidden md:flex md:flex-col w-[260px] border-r border-[color:var(--border-700)] bg-[color:var(--bg-900)] sticky top-0 h-screen">
          <div className="h-14 flex items-center gap-2 px-5 border-b border-[color:var(--border-700)]">
            <div className="w-7 h-7 rounded-md bg-gradient-to-br from-[color:var(--teal-400)] to-[color:var(--teal-500)] flex items-center justify-center shadow-[0_0_0_1px_rgba(53,199,191,0.35),0_6px_20px_rgba(32,178,170,0.35)]">
              <Layers className="w-4 h-4 text-[color:var(--bg-950)]" strokeWidth={2.5} />
            </div>
            <div className="flex flex-col leading-tight">
              <span className="text-sm font-semibold tracking-tight">OverHaust</span>
              <span className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ink-600)]">Context Runtime</span>
            </div>
          </div>

          <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
            <div className="px-2 pb-2 text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Workspace</div>
            {navItems.map((it) => (
              <NavLink
                key={it.label}
                to={it.to}
                end={it.end}
                data-testid={it.tid}
                className={({ isActive }) =>
                  `group flex items-center gap-3 px-3 h-9 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-[rgba(53,199,191,0.10)] text-[color:var(--teal-300)] border border-[rgba(53,199,191,0.28)]'
                      : 'text-[color:var(--ink-200)] hover:bg-[rgba(233,238,245,0.04)] border border-transparent'
                  }`
                }
              >
                <it.icon className="w-4 h-4" strokeWidth={2} />
                <span>{it.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="p-3 border-t border-[color:var(--border-700)]">
            <LocalCacheStatus />
            <div className="mt-3 flex items-center gap-2 px-2 py-2 rounded-md bg-[color:var(--surface-850)] border border-[color:var(--border-700)]">
              <div className="w-7 h-7 rounded-full bg-[color:var(--surface-800)] border border-[color:var(--border-700)] flex items-center justify-center text-[11px] font-mono text-[color:var(--ink-200)]">
                {(user?.email || 'u').slice(0, 1).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs truncate text-[color:var(--ink-50)]">{user?.email}</div>
                <div className="text-[10px] text-[color:var(--ink-600)]">Demo workspace</div>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    className="p-1.5 rounded-md hover:bg-[rgba(233,238,245,0.06)] text-[color:var(--ink-400)]"
                    onClick={() => { logout(); navigate('/'); }}
                    aria-label="Sign out"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>Sign out</TooltipContent>
              </Tooltip>
            </div>
          </div>
        </aside>

        {/* Main */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Topbar */}
          <header className="h-14 sticky top-0 z-20 flex items-center gap-3 px-4 sm:px-6 border-b border-[color:var(--border-700)] bg-[color:var(--bg-950)]/85 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--bg-950)]/70">
            <div className="flex items-center gap-2 text-[color:var(--ink-400)] text-sm min-w-0">
              <Command className="w-4 h-4" />
              <span className="font-mono truncate">{humanPath(location.pathname)}</span>
            </div>
            <div className="flex-1" />
            <Button
              variant="secondary"
              size="sm"
              onClick={handleSeed}
              data-testid={NAV.seedDemo}
              className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-2"
            >
              <Sparkles className="w-3.5 h-3.5" /> Load LabKOT demo
            </Button>
            <Button
              size="sm"
              onClick={() => navigate('/app/projects?new=1')}
              data-testid={NAV.newProject}
              className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2"
            >
              <Plus className="w-3.5 h-3.5" /> New project
            </Button>
          </header>

          <main className="flex-1 overflow-y-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}

function humanPath(p) {
  const parts = p.split('/').filter(Boolean);
  if (parts.length === 0) return '/';
  return parts.join(' / ');
}
