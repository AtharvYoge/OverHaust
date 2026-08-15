import React, { useEffect, useMemo, useState } from 'react';
import { AnalyticsAPI } from '@/lib/api';
import KpiCard from '@/components/KpiCard';
import { formatTokens, formatPct } from '@/lib/tokens';
import { ANALYTICS } from '@/constants/testIds';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer, LineChart, Line, Legend,
} from 'recharts';

export default function Analytics() {
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [s, h] = await Promise.all([AnalyticsAPI.summary(), AnalyticsAPI.history()]);
        setSummary(s);
        setHistory(h || []);
      } catch {
        // ignore
      }
    })();
  }, []);

  const barData = useMemo(() => [
    { label: 'Raw', tokens: summary?.total_raw_tokens || 0 },
    { label: 'Cache', tokens: summary?.total_cache_tokens || 0 },
  ], [summary]);

  const lineData = useMemo(() => (history || []).map((h, i) => ({
    idx: i + 1,
    reduction: Math.round(h.reduction_pct || 0),
    raw: h.raw_tokens || 0,
    cache: h.cache_tokens || 0,
  })), [history]);

  const mostUsed = useMemo(() => {
    // Aggregate top knowledge based on history counts across builds
    const counts = {};
    for (const h of history) {
      counts[h.project_id] = (counts[h.project_id] || 0) + 1;
    }
    return Object.entries(counts).map(([pid, cnt]) => ({ project: pid.slice(0, 8), builds: cnt })).sort((a, b) => b.builds - a.builds).slice(0, 8);
  }, [history]);

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Analytics</div>
      <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">Runtime metrics</h1>
      <p className="mt-1 text-sm text-[color:var(--ink-400)]">Token counts are estimated (chars/4) — replace with a real tokenizer later.</p>

      <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Raw tokens" value={formatTokens(summary?.total_raw_tokens || 0)} sub="Across latest builds" accent />
        <KpiCard label="Cache tokens" value={formatTokens(summary?.total_cache_tokens || 0)} sub="After compression" accent />
        <KpiCard label="Avg reduction" value={formatPct(summary?.avg_reduction_pct || 0)} sub="Per cache build" accent />
        <KpiCard label="Task queries" value={summary?.total_tasks || 0} sub="Optimized assemblies" accent />
      </div>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div data-testid={ANALYTICS.before} className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Context size — before / after</div>
          <div className="mt-2 h-[240px]">
            <ResponsiveContainer>
              <BarChart data={barData} margin={{ top: 20, right: 24, bottom: 12, left: -8 }}>
                <CartesianGrid stroke="rgba(233,238,245,0.08)" vertical={false} />
                <XAxis dataKey="label" stroke="rgba(233,238,245,0.5)" tick={{ fontSize: 11 }} />
                <YAxis stroke="rgba(233,238,245,0.5)" tick={{ fontSize: 11 }} tickFormatter={(v) => formatTokens(v)} />
                <RTooltip contentStyle={tooltipStyle} formatter={(v) => [formatTokens(v), 'tokens']} />
                <Bar dataKey="tokens" radius={[6, 6, 0, 0]} fill="#20B2AA" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div data-testid={ANALYTICS.line} className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Reduction over time</div>
          <div className="mt-2 h-[240px]">
            <ResponsiveContainer>
              <LineChart data={lineData} margin={{ top: 20, right: 24, bottom: 12, left: -8 }}>
                <CartesianGrid stroke="rgba(233,238,245,0.08)" vertical={false} />
                <XAxis dataKey="idx" stroke="rgba(233,238,245,0.5)" tick={{ fontSize: 11 }} />
                <YAxis stroke="rgba(233,238,245,0.5)" tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                <RTooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}%`, 'reduction']} />
                <Line type="monotone" dataKey="reduction" stroke="#5DE2B4" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div data-testid={ANALYTICS.most} className="mt-4 rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Cache builds per project</div>
        {mostUsed.length === 0 ? (
          <div className="mt-2 text-sm text-[color:var(--ink-400)]">No analytics yet — run your first cache build.</div>
        ) : (
          <div className="mt-2 h-[220px]">
            <ResponsiveContainer>
              <BarChart data={mostUsed} layout="vertical" margin={{ top: 10, right: 24, bottom: 10, left: 24 }}>
                <CartesianGrid stroke="rgba(233,238,245,0.08)" horizontal={false} />
                <XAxis type="number" stroke="rgba(233,238,245,0.5)" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="project" stroke="rgba(233,238,245,0.5)" tick={{ fontSize: 11 }} />
                <RTooltip contentStyle={tooltipStyle} />
                <Bar dataKey="builds" radius={[0, 6, 6, 0]} fill="#6AA9FF" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

const tooltipStyle = {
  background: 'hsl(var(--popover))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 12,
  fontSize: 12,
};
