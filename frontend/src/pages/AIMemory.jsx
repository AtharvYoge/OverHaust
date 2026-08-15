import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ProjectAPI, CacheAPI } from '@/lib/api';
import { MEMORY } from '@/constants/testIds';
import { formatRelativeTime } from '@/lib/tokens';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Brain, FolderKanban, BookMarked, ScrollText, Boxes, ShieldCheck, Activity,
  Sparkles, ArrowRight, Clock,
} from 'lucide-react';
import { toast } from 'sonner';

// Map the underlying knowledge buckets to friendly, non-technical categories.
const CATEGORY_DEFS = [
  {
    key: 'project_information', title: 'Project information', icon: FolderKanban,
    collect: (c) => {
      const id = c.project_identity || {};
      const arch = c.architecture || {};
      const out = [];
      if (id.purpose) out.push(id.purpose);
      if (id.architecture_summary) out.push(id.architecture_summary);
      Object.values(arch).forEach((v) => { if (v && String(v).trim()) out.push(String(v)); });
      return out;
    },
  },
  {
    key: 'instructions', title: 'Important instructions', icon: BookMarked,
    collect: (c) => (c.conversation_memory?.permanent_knowledge) || [],
  },
  {
    key: 'decisions', title: 'Previous decisions', icon: ScrollText,
    collect: (c) => (c.decisions || []).map((d) => d.title || d).filter(Boolean),
  },
  {
    key: 'documents', title: 'Documents & components', icon: Boxes,
    collect: (c) => (c.components || []).map((x) => x.name || x).filter(Boolean),
  },
  {
    key: 'preferences', title: 'Preferences & guardrails', icon: ShieldCheck,
    collect: (c) => (c.conversation_memory?.rejected_approaches) || [],
  },
  {
    key: 'current_work', title: 'Current work', icon: Activity,
    collect: (c) => {
      const cs = c.current_state || {};
      const mem = c.conversation_memory || {};
      return [...(cs.in_progress || []), ...(cs.known_issues || []), ...(mem.open_issues || [])];
    },
  },
];

export default function AIMemory() {
  const [loading, setLoading] = useState(true);
  const [entries, setEntries] = useState([]); // { project, cache, created_at }
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const projects = await ProjectAPI.list();
        const withCaches = await Promise.all(
          projects.map(async (p) => {
            const doc = await CacheAPI.latest(p.id).catch(() => null);
            return doc ? { project: p, cache: doc.cache, created_at: doc.created_at } : null;
          })
        );
        setEntries(withCaches.filter(Boolean));
      } catch (e) {
        toast.error('Could not load AI Memory');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const categories = useMemo(() => {
    return CATEGORY_DEFS.map((def) => {
      const items = [];
      for (const e of entries) {
        for (const it of def.collect(e.cache || {})) {
          items.push({ text: it, project: e.project.name });
        }
      }
      return { ...def, items };
    });
  }, [entries]);

  const recent = useMemo(() => {
    return [...entries]
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
      .slice(0, 6);
  }, [entries]);

  const seed = async () => {
    try {
      const proj = await ProjectAPI.seedLabkot();
      toast.success('Demo project loaded');
      navigate(`/app/projects/${proj.id}`);
    } catch (e) {
      toast.error('Could not load the demo');
    }
  };

  const hasMemory = entries.length > 0;

  return (
    <div data-testid={MEMORY.page} className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
          <Brain className="w-4.5 h-4.5" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">AI Memory</div>
          <h1 className="text-2xl sm:text-3xl font-semibold">Things your AI knows</h1>
        </div>
      </div>
      <p className="mt-3 text-sm text-[color:var(--ink-400)] max-w-[720px]">
        We keep the useful information from your projects and conversations so your AI doesn&rsquo;t have to
        start from scratch every time.
      </p>

      {loading ? (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-[14px] bg-[color:var(--surface-800)]" />
          ))}
        </div>
      ) : !hasMemory ? (
        <Card className="mt-6 bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
          <CardContent className="p-10 text-center">
            <div className="text-sm text-[color:var(--ink-200)]">Your AI doesn&rsquo;t remember anything yet.</div>
            <div className="mt-1 text-xs text-[color:var(--ink-600)] font-mono">Add information to a project, or load the demo to see this filled in.</div>
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button variant="secondary" onClick={seed} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
                <Sparkles className="w-3.5 h-3.5" /> Load demo
              </Button>
              <Button onClick={() => navigate('/app/projects?new=1')} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
                Add knowledge <ArrowRight className="w-3.5 h-3.5" />
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <div data-testid={MEMORY.categories} className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {categories.map((cat) => (
              <Card key={cat.key} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
                        <cat.icon className="w-3.5 h-3.5" />
                      </div>
                      <div className="text-sm font-semibold">{cat.title}</div>
                    </div>
                    <span className="text-[11px] font-mono tabular text-[color:var(--ink-400)]">{cat.items.length}</span>
                  </div>
                  {cat.items.length === 0 ? (
                    <div className="mt-3 text-xs text-[color:var(--ink-600)] font-mono">Nothing captured yet.</div>
                  ) : (
                    <ul className="mt-3 space-y-1.5">
                      {cat.items.slice(0, 6).map((it, i) => (
                        <li key={i} className="text-sm text-[color:var(--ink-200)] leading-snug flex gap-2">
                          <span className="text-[color:var(--mint-400)] mt-1.5 w-1 h-1 rounded-full bg-[color:var(--mint-400)] shrink-0" />
                          <span className="line-clamp-2">{it.text}</span>
                        </li>
                      ))}
                      {cat.items.length > 6 && (
                        <li className="text-[11px] font-mono text-[color:var(--ink-600)] pl-3">+ {cat.items.length - 6} more</li>
                      )}
                    </ul>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          <div data-testid={MEMORY.recent} className="mt-6 rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)]">
            <div className="px-5 py-3 border-b border-[color:var(--border-700)] flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-[color:var(--ink-400)]" />
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Recently updated</div>
            </div>
            <div className="divide-y divide-[color:var(--border-700)]">
              {recent.map((e) => (
                <button
                  key={e.project.id}
                  onClick={() => navigate(`/app/projects/${e.project.id}`)}
                  className="w-full text-left flex items-center gap-3 px-5 py-3 hover:bg-[rgba(233,238,245,0.03)]"
                >
                  <div className="w-7 h-7 rounded-md bg-[color:var(--surface-800)] border border-[color:var(--border-700)] flex items-center justify-center text-[color:var(--teal-300)]">
                    <FolderKanban className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-[color:var(--ink-50)] truncate">{e.project.name}</div>
                    <div className="text-xs text-[color:var(--ink-400)]">Memory updated</div>
                  </div>
                  <div className="text-[11px] font-mono text-[color:var(--ink-400)]">{formatRelativeTime(e.created_at)}</div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
