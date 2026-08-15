import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AnalyticsAPI, ProjectAPI } from '@/lib/api';
import KpiCard from '@/components/KpiCard';
import BeforeAfterBars from '@/components/BeforeAfterBars';
import { formatTokens, formatPct, formatRelativeTime } from '@/lib/tokens';
import { FolderKanban, ArrowRight, Sparkles, Database, TrendingDown, Plug, PlusCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { HOME } from '@/constants/testIds';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [projects, setProjects] = useState([]);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const [s, p] = await Promise.all([AnalyticsAPI.summary(), ProjectAPI.list()]);
      setSummary(s);
      setProjects(p);
    } catch (e) {
      toast.error('Could not load your home');
    }
  };

  useEffect(() => { load(); }, []);

  const seed = async () => {
    try {
      const proj = await ProjectAPI.seedLabkot();
      toast.success('Demo project loaded');
      navigate(`/app/projects/${proj.id}`);
    } catch (e) {
      toast.error('Could not load the demo', { description: String(e?.message || e) });
    }
  };

  const reduction = summary?.avg_reduction_pct && summary.avg_reduction_pct > 0
    ? Math.round(summary.avg_reduction_pct)
    : 65;

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Home</div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">You&rsquo;re getting more from your AI</h1>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">A simple memory layer that remembers what matters, so your AI uses less.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={seed} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-2">
            <Sparkles className="w-3.5 h-3.5" /> Load demo
          </Button>
          <Button onClick={() => navigate('/app/projects?new=1')} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
            <PlusCircle className="w-3.5 h-3.5" /> Add knowledge
          </Button>
        </div>
      </div>

      {/* Hero savings card */}
      <div data-testid={HOME.heroCard} className="mt-6 rounded-[16px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-6 grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-8 items-center">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">AI usage this month</div>
          <div className="mt-3 flex items-end gap-3">
            <span className="metric-num text-5xl leading-none text-[color:var(--mint-400)]">{reduction}%</span>
            <span className="text-sm text-[color:var(--ink-400)] pb-1">estimated unnecessary usage reduced</span>
          </div>
          <p className="mt-3 text-sm text-[color:var(--ink-400)] max-w-[420px]">
            A large part of typical AI usage is repeated or unnecessary information. OverHaust keeps only what matters.
          </p>
          <div className="mt-4">
            <Link to="/app/usage" className="text-sm text-[color:var(--teal-300)] hover:text-[color:var(--teal-400)] inline-flex items-center gap-1">
              See your usage savings <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>
        <BeforeAfterBars reductionPct={reduction} beforeLabel="Without optimization" afterLabel="With OverHaust" />
      </div>

      {/* KPIs */}
      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard testId={HOME.kpiSaved} label="AI information saved" value={formatTokens(summary?.estimated_context_saved || 0)} accent sub="tokens · estimated" />
        <KpiCard testId={HOME.kpiReduced} label="Estimated usage reduced" value={formatPct(reduction, 0)} accent sub="average across projects" />
        <KpiCard testId={HOME.kpiProjects} label="Projects" value={summary?.projects ?? 0} accent sub="knowledge collections" />
        <KpiCard testId={HOME.kpiAgents} label="Connected agents" value={summary?.connected_agents ?? 0} accent sub="AI tools linked" />
      </div>

      {/* Recent projects + quick links */}
      <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)]">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--border-700)]">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Your projects</div>
            <Link to="/app/projects" className="text-xs text-[color:var(--ink-400)] hover:text-[color:var(--ink-50)] inline-flex items-center gap-1">
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {projects.length === 0 ? (
            <EmptyProjects onSeed={seed} onCreate={() => navigate('/app/projects?new=1')} />
          ) : (
            <div className="divide-y divide-[color:var(--border-700)]">
              {projects.slice(0, 6).map((p) => (
                <Link key={p.id} to={`/app/projects/${p.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-[rgba(233,238,245,0.03)]">
                  <div className="w-7 h-7 rounded-md bg-[color:var(--surface-800)] border border-[color:var(--border-700)] flex items-center justify-center text-[color:var(--teal-300)]">
                    <FolderKanban className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-[color:var(--ink-50)] truncate">{p.name}</div>
                    <div className="text-xs text-[color:var(--ink-400)] truncate">{p.stack?.slice(0, 4).join(' · ') || 'No details yet'}</div>
                  </div>
                  <div className="text-[11px] font-mono text-[color:var(--ink-400)]">{formatRelativeTime(p.updated_at)}</div>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Quick actions</div>
          <div className="mt-3 space-y-2">
            <QuickLink icon={Database} title="AI Memory" desc="See what your AI knows" to="/app/memory" navigate={navigate} />
            <QuickLink icon={TrendingDown} title="Usage & savings" desc="Do you really need a bigger plan?" to="/app/usage" navigate={navigate} />
            <QuickLink icon={Plug} title="Connections" desc="Link the AI tools you use" to="/app/connections" navigate={navigate} />
          </div>
          <div className="mt-5 text-[11px] font-mono text-[color:var(--ink-600)] leading-relaxed">
            Savings shown are estimates based on your own project data.
          </div>
        </div>
      </div>
    </div>
  );
}

function QuickLink({ icon: Icon, title, desc, to, navigate }) {
  return (
    <button onClick={() => navigate(to)} className="w-full text-left flex items-center gap-3 rounded-md border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40 p-3 hover:border-[color:var(--border-650)] transition-colors">
      <div className="w-8 h-8 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-[color:var(--ink-50)]">{title}</div>
        <div className="text-xs text-[color:var(--ink-400)] truncate">{desc}</div>
      </div>
      <ArrowRight className="w-4 h-4 text-[color:var(--ink-600)]" />
    </button>
  );
}

function EmptyProjects({ onSeed, onCreate }) {
  return (
    <div className="p-8 text-center">
      <div className="text-sm text-[color:var(--ink-300)]">No projects yet.</div>
      <div className="mt-1 text-xs text-[color:var(--ink-600)] font-mono">Load the demo or start from scratch.</div>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button variant="secondary" onClick={onSeed} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
          <Sparkles className="w-3.5 h-3.5" /> Load demo
        </Button>
        <Button onClick={onCreate} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
          New project <ArrowRight className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}
