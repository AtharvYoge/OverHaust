import React from 'react';

/**
 * Dramatic before/after comparison of how much information reaches the AI.
 * Non-technical by default ("information"), can show token labels when `tokens` given.
 */
export default function BeforeAfterBars({
  reductionPct = 65,
  beforeLabel = 'Without OverHaust',
  afterLabel = 'With OverHaust',
  beforeSub = 'Everything sent every time',
  afterSub = 'Only what your AI needs',
  compact = false,
  testId,
}) {
  const pct = Math.max(4, Math.min(96, Math.round(reductionPct)));
  const afterWidth = 100 - pct;

  return (
    <div data-testid={testId} className="w-full">
      <div className={compact ? 'space-y-3' : 'space-y-4'}>
        <Row
          label={beforeLabel}
          sub={beforeSub}
          width={100}
          tone="before"
          valueText="100%"
        />
        <Row
          label={afterLabel}
          sub={afterSub}
          width={afterWidth}
          tone="after"
          valueText={`${afterWidth}%`}
        />
      </div>
      <div className="mt-4 flex items-center gap-2 text-sm">
        <span className="metric-num text-2xl text-[color:var(--mint-400)]">{pct}%</span>
        <span className="text-[color:var(--ink-400)]">less unnecessary information sent to your AI</span>
      </div>
      <div className="mt-1 text-[11px] font-mono text-[color:var(--ink-600)]">Estimated</div>
    </div>
  );
}

function Row({ label, sub, width, tone, valueText }) {
  const barCls =
    tone === 'after'
      ? 'bg-gradient-to-r from-[color:var(--teal-500)] to-[color:var(--mint-500)]'
      : 'bg-[rgba(233,238,245,0.22)]';
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-[color:var(--ink-200)]">{label}</span>
        <span className="text-[11px] font-mono tabular text-[color:var(--ink-400)]">{valueText}</span>
      </div>
      <div className="h-3 rounded-full bg-[color:var(--surface-800)] border border-[color:var(--border-700)] overflow-hidden">
        <div
          className={`h-full rounded-full ${barCls} transition-[width] duration-500`}
          style={{ width: `${width}%` }}
        />
      </div>
      {sub ? <div className="mt-1 text-[11px] text-[color:var(--ink-600)]">{sub}</div> : null}
    </div>
  );
}
