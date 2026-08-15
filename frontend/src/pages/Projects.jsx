import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { ProjectAPI } from '@/lib/api';
import { PROJECT } from '@/constants/testIds';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { FolderKanban, Plus, X, Sparkles, Trash2 } from 'lucide-react';
import { formatRelativeTime } from '@/lib/tokens';

const STACK_SUGGESTIONS = [
  'React', 'TypeScript', 'Next.js', 'FastAPI', 'Node.js', 'Python', 'Go', 'Rust',
  'PostgreSQL', 'MongoDB', 'Redis', 'Flutter', 'Dart', 'Swift', 'Kotlin', 'GraphQL',
];

export default function Projects() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      setItems(await ProjectAPI.list());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const openCreate = params.get('new') === '1';
  const setCreate = (open) => {
    if (open) params.set('new', '1'); else params.delete('new');
    setParams(params, { replace: true });
  };

  const seed = async () => {
    try {
      const p = await ProjectAPI.seedLabkot();
      toast.success('LabKOT demo loaded');
      navigate(`/app/projects/${p.id}`);
    } catch (e) {
      toast.error('Seed failed');
    }
  };

  const remove = async (p) => {
    if (!window.confirm(`Delete "${p.name}"? This will remove all context and caches.`)) return;
    try {
      await ProjectAPI.remove(p.id);
      toast.success('Project deleted');
      load();
    } catch { toast.error('Delete failed'); }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Projects</div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">My Projects</h1>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">Each project keeps its own AI memory and prepared context.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={seed} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
            <Sparkles className="w-3.5 h-3.5" /> Load demo
          </Button>
          <Button data-testid={PROJECT.createButton} onClick={() => setCreate(true)} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
            <Plus className="w-3.5 h-3.5" /> New project
          </Button>
        </div>
      </div>

      <div data-testid={PROJECT.table} className="mt-6 rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] overflow-hidden">
        <div className="grid grid-cols-[1fr_240px_120px_60px] px-4 py-2 text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] border-b border-[color:var(--border-700)]">
          <div>Name</div><div>Stack</div><div className="text-right">Updated</div><div />
        </div>
        {loading ? (
          <div className="p-6 text-sm text-[color:var(--ink-400)]">Loading…</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center">
            <div className="text-sm text-[color:var(--ink-300)]">No projects yet.</div>
            <div className="mt-1 text-xs text-[color:var(--ink-600)] font-mono">Try the demo to see the full flow instantly.</div>
          </div>
        ) : items.map((p) => (
          <div key={p.id} className="grid grid-cols-[1fr_240px_120px_60px] items-center px-4 py-3 border-b border-[color:var(--border-700)] hover:bg-[rgba(233,238,245,0.03)]">
            <Link to={`/app/projects/${p.id}`} className="flex items-center gap-3 min-w-0">
              <div className="w-7 h-7 rounded-md bg-[color:var(--surface-800)] border border-[color:var(--border-700)] flex items-center justify-center text-[color:var(--teal-300)]">
                <FolderKanban className="w-3.5 h-3.5" />
              </div>
              <div className="min-w-0">
                <div className="text-sm text-[color:var(--ink-50)] truncate">{p.name}</div>
                <div className="text-xs text-[color:var(--ink-400)] truncate">{p.description || 'No description'}</div>
              </div>
            </Link>
            <div className="flex flex-wrap gap-1">
              {p.stack?.slice(0, 4).map((s) => (
                <Badge key={s} variant="outline" className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] text-[color:var(--ink-200)] rounded-full">{s}</Badge>
              ))}
            </div>
            <div className="text-right font-mono tabular text-xs text-[color:var(--ink-400)]">{formatRelativeTime(p.updated_at)}</div>
            <div className="text-right">
              <button onClick={() => remove(p)} className="p-1.5 rounded hover:bg-[rgba(255,107,107,0.10)] text-[color:var(--ink-400)] hover:text-[color:var(--red-500)]" aria-label="Delete">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      <CreateProjectDialog open={openCreate} onOpenChange={setCreate} onCreated={(p) => { setCreate(false); navigate(`/app/projects/${p.id}`); }} />
    </div>
  );
}

function CreateProjectDialog({ open, onOpenChange, onCreated }) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [stack, setStack] = useState([]);
  const [chip, setChip] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) { setName(''); setDescription(''); setStack([]); setChip(''); }
  }, [open]);

  const addChip = (val) => {
    const v = (val || '').trim();
    if (!v) return;
    setStack((s) => (s.includes(v) ? s : [...s, v]));
    setChip('');
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!name.trim()) { toast.error('Name required'); return; }
    setBusy(true);
    try {
      const p = await ProjectAPI.create({ name, description, stack });
      toast.success('Project created');
      onCreated?.(p);
    } catch (e) {
      toast.error('Create failed', { description: String(e?.message || e) });
    } finally { setBusy(false); }
  };

  const remaining = useMemo(() => STACK_SUGGESTIONS.filter((s) => !stack.includes(s)), [stack]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[color:var(--surface-850)] border border-[color:var(--border-700)]">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription className="text-[color:var(--ink-400)]">
            Give your project a name, a short description, and any tools it uses. You can add knowledge after.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs text-[color:var(--ink-400)]">Project name</label>
            <Input data-testid={PROJECT.createNameInput} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. LabKOT" className="bg-[rgba(255,255,255,0.03)] border-[color:var(--border-700)]" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-[color:var(--ink-400)]">Description</label>
            <Textarea data-testid={PROJECT.createDescInput} value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="One-liner about what this project is" className="bg-[rgba(255,255,255,0.03)] border-[color:var(--border-700)]" />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-[color:var(--ink-400)]">Tech stack</label>
            <div className="flex flex-wrap gap-1.5">
              {stack.map((s) => (
                <span key={s} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-[rgba(32,178,170,0.10)] text-[color:var(--teal-300)] border border-[rgba(53,199,191,0.28)]">
                  {s}
                  <button type="button" onClick={() => setStack((prev) => prev.filter((x) => x !== s))}>
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              <input
                data-testid={PROJECT.createStackInput}
                value={chip}
                onChange={(e) => setChip(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addChip(chip); }
                  if (e.key === 'Backspace' && !chip) setStack((s) => s.slice(0, -1));
                }}
                placeholder="Add and press Enter"
                className="bg-transparent text-sm outline-none min-w-[160px] text-[color:var(--ink-50)] placeholder:text-[color:var(--ink-600)]"
              />
            </div>
            <div className="flex flex-wrap gap-1 pt-1">
              {remaining.slice(0, 12).map((s) => (
                <button key={s} type="button" onClick={() => addChip(s)} className="text-[11px] px-1.5 py-0.5 rounded-full border border-[color:var(--border-700)] text-[color:var(--ink-400)] hover:text-[color:var(--ink-50)] hover:border-[color:var(--border-650)]">
                  + {s}
                </button>
              ))}
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)]">Cancel</Button>
            <Button type="submit" data-testid={PROJECT.createSubmit} disabled={busy} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)]">
              {busy ? 'Creating…' : 'Create project'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
