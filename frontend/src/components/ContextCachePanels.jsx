import React from 'react';
import {
  Boxes,
  Layers,
  Cpu,
  ScrollText,
  ListChecks,
  Brain,
  CheckCircle2,
  ShieldAlert,
  History,
  ThumbsDown,
  CircleDot,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

function Panel({ title, icon: Icon, children, testId }) {
  return (
    <Card data-testid={testId} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
      <CardContent className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-6 h-6 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
            <Icon className="w-3.5 h-3.5" />
          </div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">{title}</div>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

function Empty({ label }) {
  return <div className="text-xs text-[color:var(--ink-600)] font-mono">{label}</div>;
}

export default function ContextCachePanels({ cache }) {
  if (!cache) return null;
  const id = cache.project_identity || {};
  const arch = cache.architecture || {};
  const cs = cache.current_state || {};
  const mem = cache.conversation_memory || {};
  const archEntries = Object.entries(arch).filter(([, v]) => (v || '').trim().length > 0);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Panel title="Project Identity" icon={Boxes} testId="panel-project-identity">
        <div className="space-y-2">
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="text-lg font-semibold text-[color:var(--ink-50)]">{id.type || '—'}</span>
            {(id.stack || []).map((s) => (
              <Badge
                key={s}
                className="bg-[color:var(--surface-800)] text-[color:var(--ink-200)] border border-[color:var(--border-700)] rounded-full"
                variant="outline"
              >
                {s}
              </Badge>
            ))}
          </div>
          <div className="text-sm text-[color:var(--ink-200)]">{id.purpose || <Empty label="No purpose captured." />}</div>
          <div className="text-sm text-[color:var(--ink-400)]">{id.architecture_summary}</div>
        </div>
      </Panel>

      <Panel title="Architecture" icon={Layers} testId="panel-architecture">
        {archEntries.length === 0 ? (
          <Empty label="No architecture inferred yet." />
        ) : (
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {archEntries.map(([k, v]) => (
              <div key={k} className="rounded-md border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/50 p-2.5">
                <dt className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">{k}</dt>
                <dd className="text-xs text-[color:var(--ink-200)] mt-0.5">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </Panel>

      <Panel title="Components" icon={Cpu} testId="panel-components">
        {(!cache.components || cache.components.length === 0) ? (
          <Empty label="No components extracted." />
        ) : (
          <ul className="space-y-1.5">
            {cache.components.map((c, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-[color:var(--surface-800)] border border-[color:var(--border-700)] text-[color:var(--ink-300)] mt-0.5">
                  {c.kind || 'module'}
                </span>
                <div>
                  <div className="text-sm text-[color:var(--ink-50)] font-mono">{c.name}</div>
                  {c.purpose ? <div className="text-xs text-[color:var(--ink-400)]">{c.purpose}</div> : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Decisions" icon={ScrollText} testId="panel-decisions">
        {(!cache.decisions || cache.decisions.length === 0) ? (
          <Empty label="No decisions captured." />
        ) : (
          <ul className="space-y-2">
            {cache.decisions.map((d, i) => (
              <li key={i} className="rounded-md border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/50 p-2.5">
                <div className="text-sm text-[color:var(--ink-50)]">{d.title}</div>
                {d.rationale ? <div className="text-xs text-[color:var(--ink-400)] mt-1">{d.rationale}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Current State" icon={ListChecks} testId="panel-current-state">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <StateList label="Implemented" items={cs.implemented} icon={CheckCircle2} tone="success" />
          <StateList label="In progress" items={cs.in_progress} icon={CircleDot} tone="accent" />
          <StateList label="Known issues" items={cs.known_issues} icon={ShieldAlert} tone="warning" />
        </div>
      </Panel>

      <Panel title="Conversation Memory" icon={Brain} testId="panel-conversation-memory">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <MemoryList label="Permanent knowledge" icon={Brain} items={mem.permanent_knowledge} tone="accent" />
          <MemoryList label="Temporary task context" icon={History} items={mem.temporary_task_context} tone="muted" />
          <MemoryList label="Resolved issues" icon={CheckCircle2} items={mem.resolved_issues} tone="success" />
          <MemoryList label="Rejected approaches" icon={ThumbsDown} items={mem.rejected_approaches} tone="muted" />
          <MemoryList label="Open issues" icon={ShieldAlert} items={mem.open_issues} tone="warning" />
        </div>
      </Panel>
    </div>
  );
}

function StateList({ label, items, icon: Icon, tone }) {
  const dot =
    tone === 'success'
      ? 'text-[color:var(--mint-400)]'
      : tone === 'warning'
      ? 'text-[color:var(--amber-500)]'
      : 'text-[color:var(--teal-300)]';
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">
        <Icon className={`w-3 h-3 ${dot}`} /> {label}
      </div>
      {(items || []).length === 0 ? (
        <div className="text-xs text-[color:var(--ink-600)] font-mono mt-1">—</div>
      ) : (
        <ul className="mt-1.5 space-y-1 text-xs text-[color:var(--ink-200)]">
          {items.map((it, i) => (
            <li key={i} className="leading-snug">• {it}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function MemoryList({ label, icon: Icon, items, tone }) {
  const badgeCls =
    tone === 'success'
      ? 'bg-[rgba(93,226,180,0.10)] text-[color:var(--mint-400)] border-[rgba(93,226,180,0.28)]'
      : tone === 'warning'
      ? 'bg-[rgba(246,193,119,0.10)] text-[color:var(--amber-500)] border-[rgba(246,193,119,0.28)]'
      : tone === 'accent'
      ? 'bg-[rgba(32,178,170,0.10)] text-[color:var(--teal-300)] border-[rgba(53,199,191,0.28)]'
      : 'bg-[color:var(--surface-800)] text-[color:var(--ink-300)] border-[color:var(--border-700)]';

  return (
    <div className="rounded-md border border-[color:var(--border-700)] p-2.5 bg-[color:var(--bg-900)]/50">
      <div className={`inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded-full border ${badgeCls}`}>
        <Icon className="w-3 h-3" /> {label}
      </div>
      {(items || []).length === 0 ? (
        <div className="mt-2 text-xs text-[color:var(--ink-600)] font-mono">—</div>
      ) : (
        <ul className="mt-2 space-y-1 text-xs text-[color:var(--ink-200)]">
          {items.map((it, i) => (
            <li key={i} className="leading-snug">• {it}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
