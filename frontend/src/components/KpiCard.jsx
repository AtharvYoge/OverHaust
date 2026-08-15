import React from 'react';
import { Card, CardContent } from '@/components/ui/card';

export default function KpiCard({ label, value, sub, accent, testId, mono = true }) {
  return (
    <Card
      data-testid={testId}
      className="relative overflow-hidden bg-[color:var(--surface-850)] border-[color:var(--border-700)] hover:border-[color:var(--border-650)] transition-colors"
    >
      {accent && (
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[color:var(--teal-400)]/60 to-transparent" />
      )}
      <CardContent className="p-5">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">{label}</div>
        <div className={`mt-2 text-3xl leading-none ${mono ? 'metric-num' : 'font-semibold'} text-[color:var(--ink-50)]`}>
          {value}
        </div>
        {sub ? <div className="mt-2 text-xs text-[color:var(--ink-400)] font-mono">{sub}</div> : null}
      </CardContent>
    </Card>
  );
}
