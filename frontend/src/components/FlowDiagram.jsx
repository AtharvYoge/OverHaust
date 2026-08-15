import React from 'react';
import { ArrowRight, Cpu, Braces, Sparkles } from 'lucide-react';

export default function FlowDiagram({ testId }) {
  return (
    <div data-testid={testId} className="relative w-full">
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 rounded-[24px] bg-[radial-gradient(600px_circle_at_10%_10%,rgba(32,178,170,0.22),transparent_60%),radial-gradient(500px_circle_at_90%_20%,rgba(93,226,180,0.14),transparent_65%)]" />
        <div className="absolute inset-0 rounded-[24px] bg-grid bg-grid-fade opacity-40" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] gap-3 md:gap-2 items-stretch p-4 md:p-6">
        <FlowNode label="Raw project" primary="500,000" secondary="tokens (estimated)" tone="muted" icon={Braces} />
        <Arrow />
        <FlowNode label="Context Runtime" primary="compressor" secondary="analyze → cache" tone="accent" icon={Cpu} />
        <Arrow />
        <FlowNode label="Persistent cache" primary="< 8,000" secondary="tokens relevant" tone="success" icon={Sparkles} />
        <Arrow />
        <FlowNode label="AI Agent" primary="Cursor · Claude" secondary="receives context" tone="muted" icon={Cpu} />
      </div>

      <div className="px-6 pb-6 -mt-2 text-[11px] text-[color:var(--ink-600)] font-mono tabular text-center md:text-left">
        Numbers shown are prototype / estimated. Real reduction depends on your inputs.
      </div>
    </div>
  );
}

function Arrow() {
  return (
    <div className="hidden md:flex items-center justify-center text-[color:var(--ink-600)]">
      <ArrowRight className="w-4 h-4" />
    </div>
  );
}

function FlowNode({ label, primary, secondary, tone, icon: Icon }) {
  const toneCls =
    tone === 'accent'
      ? 'border-[rgba(53,199,191,0.35)] bg-[rgba(32,178,170,0.08)] text-[color:var(--teal-300)]'
      : tone === 'success'
      ? 'border-[rgba(93,226,180,0.30)] bg-[rgba(93,226,180,0.06)] text-[color:var(--mint-400)]'
      : 'border-[color:var(--border-700)] bg-[color:var(--surface-850)] text-[color:var(--ink-200)]';

  return (
    <div className={`rounded-[14px] border p-3 md:p-4 flex flex-col gap-1 min-h-[102px] justify-between ${toneCls} shadow-[var(--shadow-card)]`}>
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] opacity-80">
        {Icon ? <Icon className="w-3 h-3" /> : null} {label}
      </div>
      <div className="text-2xl md:text-3xl metric-num leading-none">{primary}</div>
      <div className="text-[11px] opacity-70 font-mono">{secondary}</div>
    </div>
  );
}
