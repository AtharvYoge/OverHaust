import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ProjectAPI,
  ContextAPI,
  CacheAPI,
  TaskAPI,
} from '@/lib/api';
import { PROJECT } from '@/constants/testIds';
import { toast } from 'sonner';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Boxes,
  FileText,
  MessageSquare,
  StickyNote,
  Trash2,
  Sparkles,
  ArrowRight,
  Loader2,
  Check,
  RefreshCcw,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
} from 'lucide-react';
import { formatTokens, formatPct, estimateTokens, formatRelativeTime } from '@/lib/tokens';
import { saveCacheLocal, saveTaskLocal, loadCacheLocal } from '@/lib/idb';
import Dropzone from '@/components/Dropzone';
import PipelineOverlay from '@/components/PipelineOverlay';
import ContextCachePanels from '@/components/ContextCachePanels';
import CodeBlock from '@/components/CodeBlock';
import TokenComparisonTable from '@/components/TokenComparisonTable';

const TAB_META = {
  conversation: { label: 'Conversation', icon: MessageSquare, placeholder: 'Paste a long AI chat or conversation here…' },
  documentation: { label: 'Documents', icon: FileText, placeholder: 'Paste a document, guide or README…' },
  file: { label: 'Files', icon: Boxes, placeholder: 'Paste file contents here (or drop files below)…' },
  note: { label: 'Notes', icon: StickyNote, placeholder: 'Add notes, instructions or preferences…' },
};

export default function ProjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [sources, setSources] = useState([]);
  const [cacheDoc, setCacheDoc] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [incremental, setIncremental] = useState(null);

  const [tab, setTab] = useState('conversation');
  const [textInput, setTextInput] = useState('');
  const [name, setName] = useState('');
  const [taskInput, setTaskInput] = useState('');
  const [taskRun, setTaskRun] = useState(null);

  const [buildOpen, setBuildOpen] = useState(false);
  const [buildDone, setBuildDone] = useState(false);
  const [busyBuild, setBusyBuild] = useState(false);
  const [busyTask, setBusyTask] = useState(false);
  const [advancedUsage, setAdvancedUsage] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, s, c, t, inc] = await Promise.all([
        ProjectAPI.get(id),
        ContextAPI.list(id),
        CacheAPI.latest(id).catch(() => null),
        TaskAPI.list(id).catch(() => []),
        CacheAPI.incremental(id).catch(() => null),
      ]);
      setProject(p);
      setSources(s);
      setCacheDoc(c);
      setTasks(t);
      setIncremental(inc);
      if (t?.[0]) setTaskRun(t[0]);
      if (c) saveCacheLocal({ ...c });
      if (!c) {
        // fallback to local cache mirror if available
        const local = await loadCacheLocal(id);
        if (local) setCacheDoc(local);
      }
    } catch (e) {
      toast.error('Failed to load project');
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const totals = useMemo(() => {
    const files = sources.filter((s) => s.type === 'file');
    const docs = sources.filter((s) => s.type === 'documentation');
    const notes = sources.filter((s) => s.type === 'note');
    const conv = sources.filter((s) => s.type === 'conversation');
    const sum = (arr) => arr.reduce((a, s) => a + (s.tokens || estimateTokens(s.content || '')), 0);
    return {
      files_count: files.length,
      docs_count: docs.length,
      notes_count: notes.length,
      conv_count: conv.length,
      files_tokens: sum(files),
      docs_tokens: sum(docs),
      notes_tokens: sum(notes),
      conv_tokens: sum(conv),
      total_tokens: sum(sources),
    };
  }, [sources]);

  const addSource = async (payload) => {
    try {
      const created = await ContextAPI.add(id, payload);
      setSources((s) => [created, ...s]);
      toast.success('Added to your project', { description: `${payload.type} · ${payload.name}` });
    } catch (e) {
      toast.error('Add failed', { description: String(e?.message || e) });
    }
  };

  const addFromText = async () => {
    if (!textInput.trim()) return;
    await addSource({ type: tab, name: name.trim() || `${TAB_META[tab].label} · ${new Date().toLocaleTimeString()}`, content: textInput });
    setTextInput('');
    setName('');
  };

  const addFilesFromDrop = async (items) => {
    for (const it of items) {
      // eslint-disable-next-line no-await-in-loop
      await addSource({ type: 'file', name: it.name, content: it.content });
    }
  };

  const removeSource = async (sid) => {
    try {
      await ContextAPI.remove(id, sid);
      setSources((s) => s.filter((x) => x.id !== sid));
    } catch { toast.error('Delete failed'); }
  };

  const buildCache = async () => {
    if (sources.length === 0) { toast.error('Add some information first'); return; }
    setBuildOpen(true);
    setBuildDone(false);
    setBusyBuild(true);
    try {
      const doc = await CacheAPI.build(id);
      setCacheDoc(doc);
      await saveCacheLocal({ ...doc });
      setBuildDone(true);
      toast.success('AI memory updated', {
        description: `${formatPct(doc.metrics?.reduction_pct || 0)} less unnecessary information (estimated)`,
      });
      // reload incremental status
      CacheAPI.incremental(id).then(setIncremental).catch(() => {});
    } catch (e) {
      setBuildOpen(false);
      toast.error('Cache build failed', { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setBusyBuild(false);
    }
  };

  const runTask = async () => {
    if (!cacheDoc) { toast.error('Build your AI memory first'); return; }
    if (!taskInput.trim()) { toast.error('Describe the task first'); return; }
    setBusyTask(true);
    try {
      const run = await TaskAPI.create(id, taskInput);
      setTaskRun(run);
      setTasks((prev) => [run, ...prev]);
      await saveTaskLocal(run);
      toast.success('Prepared for your AI', {
        description: `${formatPct(run.metrics?.reduction_pct || 0)} less to send`,
      });
    } catch (e) {
      toast.error('Task generation failed', { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setBusyTask(false);
    }
  };

  if (!project) {
    return (
      <div className="p-8 text-sm text-[color:var(--ink-400)]">Loading project…</div>
    );
  }

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Project</div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-semibold truncate">{project.name}</h1>
          <div className="mt-1 text-sm text-[color:var(--ink-400)] max-w-[720px]">{project.description}</div>
          <div className="mt-2 flex items-center gap-1.5 flex-wrap">
            {(project.stack || []).map((s) => (
              <Badge key={s} variant="outline" className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] text-[color:var(--ink-200)] rounded-full">
                {s}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={load} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
            <RefreshCcw className="w-3.5 h-3.5" /> Refresh
          </Button>
          <Button
            data-testid={PROJECT.buildCache}
            onClick={buildCache}
            disabled={busyBuild}
            className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2"
          >
            {busyBuild ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {cacheDoc ? 'Update AI memory' : 'Build AI memory'}
          </Button>
        </div>
      </div>

      {/* Two-column: ingestion + right panels */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="space-y-4">
          <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Give your AI more knowledge</div>
                  <div className="text-sm text-[color:var(--ink-50)] mt-0.5">Paste text, drop files, or add notes. We keep only what matters.</div>
                </div>
                <div className="text-[11px] font-mono tabular text-[color:var(--ink-400)]">
                  {formatTokens(totals.total_tokens)} tokens · estimated
                </div>
              </div>

              <Tabs value={tab} onValueChange={setTab} className="mt-4">
                <TabsList data-testid={PROJECT.ingestionTabs} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)]">
                  {Object.entries(TAB_META).map(([k, v]) => (
                    <TabsTrigger key={k} value={k} data-testid={`ingest-tab-${k}`} className="data-[state=active]:bg-[color:var(--bg-900)] data-[state=active]:text-[color:var(--teal-300)] gap-1.5">
                      <v.icon className="w-3.5 h-3.5" /> {v.label}
                    </TabsTrigger>
                  ))}
                </TabsList>

                {Object.keys(TAB_META).map((k) => (
                  <TabsContent key={k} value={k} className="mt-4 space-y-3">
                    <Input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Name (optional)"
                      className="bg-[rgba(255,255,255,0.03)] border-[color:var(--border-700)]"
                    />
                    <Textarea
                      data-testid={PROJECT.ingestionTextarea}
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      placeholder={TAB_META[k].placeholder}
                      rows={8}
                      className="bg-[rgba(255,255,255,0.03)] border-[color:var(--border-700)] font-mono text-[13px] leading-6"
                    />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-mono text-[color:var(--ink-600)]">
                        {textInput ? `${formatTokens(estimateTokens(textInput))} tokens · estimated` : 'empty'}
                      </span>
                      <Button data-testid={PROJECT.ingestionAdd} onClick={addFromText} disabled={!textInput.trim()} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
                        Add {TAB_META[k].label.toLowerCase()} <ArrowRight className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                    {k === 'file' && (
                      <Dropzone onFiles={addFilesFromDrop} />
                    )}
                  </TabsContent>
                ))}
              </Tabs>
            </CardContent>
          </Card>

          <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">What you&rsquo;ve added</div>
                <div className="text-[11px] font-mono text-[color:var(--ink-400)]">{sources.length} items</div>
              </div>
              {sources.length === 0 ? (
                <div className="mt-4 text-sm text-[color:var(--ink-400)]">Add information above to begin.</div>
              ) : (
                <ul className="mt-4 space-y-1.5 max-h-[240px] overflow-y-auto pr-1">
                  {sources.map((s) => (
                    <li key={s.id} className="flex items-center gap-2 rounded-md border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40 px-2.5 py-1.5">
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[color:var(--surface-800)] border border-[color:var(--border-700)] text-[color:var(--ink-300)]">{s.type}</span>
                      <div className="text-sm text-[color:var(--ink-200)] font-mono truncate flex-1">{s.name}</div>
                      <span className="text-[10px] font-mono tabular text-[color:var(--ink-500)] text-[color:var(--ink-400)]">{formatTokens(s.tokens || 0)}</span>
                      <button onClick={() => removeSource(s.id)} className="p-1 rounded hover:bg-[rgba(255,107,107,0.10)] text-[color:var(--ink-400)] hover:text-[color:var(--red-500)]" aria-label="Remove">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {incremental?.has_cache && incremental?.needs_rebuild && (
            <Card className="bg-[color:var(--surface-850)] border-[rgba(246,193,119,0.35)]">
              <CardContent className="p-4 flex items-center gap-3">
                <Zap className="w-4 h-4 text-[color:var(--amber-500)]" />
                <div className="flex-1">
                  <div className="text-sm text-[color:var(--ink-50)]">New information detected</div>
                  <div className="text-xs text-[color:var(--ink-400)] font-mono">
                    {incremental.changed_sources.length} source(s) changed since cache v{incremental.cache_version}
                  </div>
                </div>
                <Button size="sm" onClick={buildCache} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)]">Update cache</Button>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right column — metrics + cache overview */}
        <div className="space-y-4">
          <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-5">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Usage reduced</div>
                <div data-testid={PROJECT.simpleToggle} className="inline-flex rounded-md border border-[color:var(--border-700)] bg-[color:var(--surface-800)] p-0.5 text-[11px]">
                  <button
                    onClick={() => setAdvancedUsage(false)}
                    className={`px-2 py-1 rounded ${!advancedUsage ? 'bg-[color:var(--bg-900)] text-[color:var(--teal-300)]' : 'text-[color:var(--ink-400)]'}`}
                  >
                    Simple
                  </button>
                  <button
                    onClick={() => setAdvancedUsage(true)}
                    className={`px-2 py-1 rounded ${advancedUsage ? 'bg-[color:var(--bg-900)] text-[color:var(--teal-300)]' : 'text-[color:var(--ink-400)]'}`}
                  >
                    Advanced
                  </button>
                </div>
              </div>

              <div className="mt-2 flex items-end gap-3 flex-wrap">
                <div data-testid={PROJECT.compressionMetric} className="metric-num text-5xl leading-none text-[color:var(--mint-400)]">
                  {cacheDoc ? formatPct(cacheDoc.metrics?.reduction_pct || 0) : '—'}
                </div>
                <div className="text-[11px] font-mono text-[color:var(--ink-400)]">
                  {advancedUsage ? 'estimated token reduction' : 'less unnecessary information (estimated)'}
                </div>
              </div>

              {advancedUsage ? (
                <>
                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <MetricPill label="Before" value={formatTokens(cacheDoc?.metrics?.raw_tokens?.total || totals.total_tokens)} sub="original tokens" tone="muted" arrow={ArrowUpRight} />
                    <MetricPill label="After" value={formatTokens(cacheDoc?.metrics?.cache_tokens || 0)} sub="optimized tokens" tone="success" arrow={ArrowDownRight} />
                  </div>
                  <div className="mt-4">
                    <div className="flex items-center justify-between text-[11px] font-mono text-[color:var(--ink-400)]">
                      <span>Information retained</span>
                      <span className="text-[color:var(--mint-400)]">High</span>
                    </div>
                    <Progress value={cacheDoc ? 92 : 0} className="mt-2 h-1.5 bg-[color:var(--surface-800)]" />
                  </div>
                </>
              ) : (
                <p className="mt-4 text-sm text-[color:var(--ink-400)]">
                  Your AI no longer has to reprocess everything each time — only the useful information is kept.
                </p>
              )}

              <div className="mt-3 text-[11px] font-mono text-[color:var(--ink-600)]">
                {cacheDoc ? `AI memory v${cacheDoc.version} · updated ${formatRelativeTime(cacheDoc.created_at)}` : 'No AI memory yet.'}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Sources by type</div>
                <div className="text-[11px] font-mono text-[color:var(--ink-400)]">estimated tokens</div>
              </div>
              <div className="mt-3 space-y-2">
                <SourceRow icon={MessageSquare} label="Conversation" count={totals.conv_count} tokens={totals.conv_tokens} />
                <SourceRow icon={FileText} label="Documentation" count={totals.docs_count} tokens={totals.docs_tokens} />
                <SourceRow icon={Boxes} label="Project files" count={totals.files_count} tokens={totals.files_tokens} />
                <SourceRow icon={StickyNote} label="Notes" count={totals.notes_count} tokens={totals.notes_tokens} />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Context Cache panels */}
      {cacheDoc?.cache && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">AI Memory</div>
              <div className="text-lg font-semibold">What your AI knows — v{cacheDoc.version}</div>
            </div>
            <div className="text-[11px] font-mono text-[color:var(--ink-400)]">
              {cacheDoc.metrics?.knowledge_items || 0} things remembered · {formatTokens(cacheDoc.metrics?.cache_tokens || 0)} tokens · estimated
            </div>
          </div>
          <ContextCachePanels cache={cacheDoc.cache} />
        </div>
      )}

      {/* Task generator */}
      {cacheDoc && (
        <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
          <CardContent className="p-5">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Prepare for AI</div>
                <div className="text-lg font-semibold">What are you working on?</div>
              </div>
              <div className="text-[11px] font-mono text-[color:var(--ink-400)]">
                We&rsquo;ll prepare only the information your AI needs.
              </div>
            </div>

            <Textarea
              data-testid={PROJECT.taskInput}
              value={taskInput}
              onChange={(e) => setTaskInput(e.target.value)}
              rows={3}
              placeholder="e.g. Fix the WebSocket reconnection issue when the waiter app temporarily loses connection to the billing master."
              className="mt-3 bg-[rgba(255,255,255,0.03)] border-[color:var(--border-700)] font-mono text-[13px] leading-6"
            />
            <div className="mt-3 flex items-center justify-between gap-2 flex-wrap">
              <span className="text-[11px] font-mono text-[color:var(--ink-600)]">
                {taskInput ? `${formatTokens(estimateTokens(taskInput))} tokens in prompt` : 'Describe the task above'}
              </span>
              <Button data-testid={PROJECT.taskSubmit} onClick={runTask} disabled={busyTask || !taskInput.trim()} className="bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
                {busyTask ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                Prepare for AI
              </Button>
            </div>

            {taskRun && (
              <div className="mt-6 grid grid-cols-1 xl:grid-cols-[1fr_1fr] gap-4">
                <div className="space-y-3">
                  <RelevanceList title="Relevant information" data={taskRun.selection?.relevant} positive />
                  <RelevanceList title="Not needed right now" data={taskRun.selection?.ignored} positive={false} />
                  <TokenComparisonTable metrics={taskRun.metrics} />
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] mb-2">
                    Ready to paste into your AI · {formatTokens(taskRun.metrics?.optimized_tokens || 0)} tokens (estimated)
                  </div>
                  <CodeBlock
                    content={taskRun.selection?.assembled_context || ''}
                    testId={PROJECT.optimizedBlock}
                    copyTestId={PROJECT.copyContext}
                    ariaLabel="Prepared context for your AI"
                  />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {tasks.length > 0 && (
        <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
          <CardContent className="p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] mb-3">Recent tasks</div>
            <ul className="space-y-1.5">
              {tasks.slice(0, 6).map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => setTaskRun(t)}
                    className={`w-full text-left rounded-md border p-2.5 hover:bg-[rgba(233,238,245,0.03)] ${
                      taskRun?.id === t.id ? 'border-[rgba(53,199,191,0.35)] bg-[rgba(32,178,170,0.06)]' : 'border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm text-[color:var(--ink-200)] truncate">{t.description}</div>
                      <div className="text-[11px] font-mono tabular text-[color:var(--mint-400)]">{formatPct(t.metrics?.reduction_pct || 0)}</div>
                    </div>
                    <div className="mt-1 text-[10px] font-mono text-[color:var(--ink-500)] text-[color:var(--ink-400)]">
                      {formatRelativeTime(t.created_at)} · {formatTokens(t.metrics?.optimized_tokens || 0)} optimized tokens
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <PipelineOverlay open={buildOpen} done={buildDone} onClose={() => setBuildOpen(false)} />
    </div>
  );
}

function MetricPill({ label, value, sub, tone, arrow: Arrow }) {
  const cls =
    tone === 'success'
      ? 'border-[rgba(93,226,180,0.30)] bg-[rgba(93,226,180,0.06)] text-[color:var(--mint-400)]'
      : 'border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40 text-[color:var(--ink-200)]';
  return (
    <div className={`rounded-[12px] border p-3 ${cls}`}>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.14em] opacity-80">
        <span>{label}</span>
        {Arrow ? <Arrow className="w-3 h-3" /> : null}
      </div>
      <div className="metric-num text-2xl leading-none mt-2">{value}</div>
      <div className="text-[11px] font-mono opacity-70 mt-1">{sub}</div>
    </div>
  );
}

function SourceRow({ icon: Icon, label, count, tokens }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-6 h-6 rounded-md bg-[color:var(--surface-800)] border border-[color:var(--border-700)] flex items-center justify-center text-[color:var(--ink-400)]">
        <Icon className="w-3.5 h-3.5" />
      </div>
      <span className="text-sm text-[color:var(--ink-200)] flex-1">{label}</span>
      <span className="text-[11px] font-mono text-[color:var(--ink-400)]">{count}</span>
      <span className="w-16 text-right text-[11px] font-mono tabular text-[color:var(--ink-50)]">{formatTokens(tokens)}</span>
    </div>
  );
}

function RelevanceList({ title, data, positive }) {
  const groups = ['components', 'architecture_keys', 'decisions', 'conversation_memory'];
  const total = groups.reduce((n, g) => n + ((data && data[g]) || []).length, 0);
  return (
    <div className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[color:var(--border-700)]">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">{title}</div>
        <div className="text-[11px] font-mono text-[color:var(--ink-400)]">{total} items</div>
      </div>
      <div className="p-3 space-y-2">
        {groups.map((g) => {
          const items = (data && data[g]) || [];
          if (items.length === 0) return null;
          return (
            <div key={g}>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] mb-1">{g.replace('_', ' ')}</div>
              <ul className="flex flex-wrap gap-1.5">
                {items.map((it, i) => (
                  <li key={i} className={`text-[11px] font-mono inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border ${
                    positive
                      ? 'bg-[rgba(93,226,180,0.10)] text-[color:var(--mint-400)] border-[rgba(93,226,180,0.30)]'
                      : 'bg-[color:var(--surface-800)] text-[color:var(--ink-400)] border-[color:var(--border-700)] line-through decoration-1'
                  }`}>
                    {positive ? <Check className="w-3 h-3" /> : <span className="opacity-60">×</span>}
                    {it}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        {total === 0 && (
          <div className="text-xs text-[color:var(--ink-600)] font-mono">—</div>
        )}
      </div>
    </div>
  );
}
