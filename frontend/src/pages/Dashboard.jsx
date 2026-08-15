import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnalyticsAPI, ProjectAPI } from '@/lib/api';
import KpiCard from '@/components/KpiCard';
import { formatTokens, formatPct, formatRelativeTime } from '@/lib/tokens';
import { Layers, FolderKanban, Gauge, Zap, ArrowRight, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([AnalyticsAPI.summary(), ProjectAPI.list()]);
      setSummary(s);
      setProjects(p);
    } catch (e) {
      toast.error('Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const seed = async () => {
    try {
      const proj = await ProjectAPI.seedLabkot();
      toast.success('LabKOT demo loaded');
      navigate(`/app/projects/${proj.id}`);
    } catch (e) {
      toast.error('Seed failed', { description: String(e?.message || e) });
    }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Overview</div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">Context Runtime</h1>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">A persistent knowledge layer for your AI coding agents.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={seed} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-2">
            <Sparkles className="w-3.5 h-3.5" /> Load LabKOT demo
          </Button>
          <Button onClick={() => navigate('/app/projects?new=1')} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
            New project <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard testId="kpi-projects" label="Projects" value={summary?.projects ?? 0} accent sub="Workspaces indexed" />
        <KpiCard testId="kpi-context-stored" label="Context stored" value={formatTokens(summary?.total_cache_tokens || 0)} accent sub={`from ${formatTokens(summary?.total_raw_tokens || 0)} raw · estimated`} />
        <KpiCard testId="kpi-avg-reduction" label="Avg reduction" value={formatPct(summary?.avg_reduction_pct || 0)} accent sub="Across cache builds" />
        <KpiCard testId="kpi-context-saved" label="Est. context saved" value={formatTokens(summary?.estimated_context_saved || 0)} accent sub={`${summary?.knowledge_items || 0} knowledge items`} />
      </div>

      <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)]">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--border-700)]">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Recent projects</div>
            <Link to="/app/projects" className="text-xs text-[color:var(--ink-400)] hover:text-[color:var(--ink-50)] inline-flex items-center gap-1">
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {projects.length === 0 ? (
            <EmptyProjects onSeed={seed} onCreate={() => navigate('/app/projects?new=1')} />
          ) : (
            <div className="divide-y divide-[color:var(--border-700)]">
              {projects.slice(0, 6).map((p) => (
                <Link
                  key={p.id}
                  to={`/app/projects/${p.id}`}
                  className="flex items-center gap-3 px-5 py-3 hover:bg-[rgba(233,238,245,0.03)]"
                >
                  <div className="w-7 h-7 rounded-md bg-[color:var(--surface-800)] border border-[color:var(--border-700)] flex items-center justify-center text-[color:var(--teal-300)]">
                    <FolderKanban className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-[color:var(--ink-50)] truncate">{p.name}</div>
                    <div className="text-xs text-[color:var(--ink-500)] text-[color:var(--ink-400)] truncate">
                      {p.stack?.slice(0, 4).join(' · ') || 'No stack'}
                    </div>
                  </div>
                  <div className="text-[11px] font-mono text-[color:var(--ink-400)]">{formatRelativeTime(p.updated_at)}</div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Runtime status</div>
          <div className="mt-3 space-y-3">
            <StatusRow icon={Layers} label="Cache builds" value={summary?.total_cache_builds || 0} />
            <StatusRow icon={Gauge} label="Task queries" value={summary?.total_tasks || 0} />
            <StatusRow icon={Zap} label="Knowledge items" value={summary?.knowledge_items || 0} />
          </div>
          <div className="mt-6 text-[11px] font-mono text-[color:var(--ink-600)] leading-relaxed">
            Metrics are estimated (chars/4 heuristic). Real tokenizer integration is planned.
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="w-3.5 h-3.5 text-[color:var(--ink-400)]" />
      <span className="text-sm text-[color:var(--ink-300)] flex-1">{label}</span>
      <span className="font-mono tabular text-sm text-[color:var(--ink-50)]">{value}</span>
    </div>
  );
}

function EmptyProjects({ onSeed, onCreate }) {
  return (
    <div className="p-8 text-center">
      <div className="text-sm text-[color:var(--ink-300)]">No projects yet.</div>
      <div className="mt-1 text-xs text-[color:var(--ink-600)] font-mono">Preload the demo or create one from scratch.</div>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button variant="secondary" onClick={onSeed} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
          <Sparkles className="w-3.5 h-3.5" /> Load LabKOT demo
        </Button>
        <Button onClick={onCreate} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
          New project <ArrowRight className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}
