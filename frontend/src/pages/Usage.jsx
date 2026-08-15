import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnalyticsAPI, UsageAPI } from '@/lib/api';
import { USAGE } from '@/constants/testIds';
import { formatTokens } from '@/lib/tokens';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { CreditCard, TrendingDown, Gauge, ArrowRight, CheckCircle2, Sparkles } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer, LineChart, Line,
} from 'recharts';

const tooltipStyle = { background: 'hsl(var(--popover))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 };

export default function Usage() {
  const [advice, setAdvice] = useState(null);
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [a, s, h] = await Promise.all([
          UsageAPI.planAdvisor(),
          AnalyticsAPI.summary(),
          AnalyticsAPI.history().catch(() => []),
        ]);
        setAdvice(a); setSummary(s); setHistory(h || []);
      } catch (e) {
        // keep silent, show skeletons
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const barData = useMemo(() => ([
    { label: 'Before', tokens: advice?.original_tokens || summary?.total_raw_tokens || 0 },
    { label: 'After', tokens: advice?.optimized_tokens || summary?.total_cache_tokens || 0 },
  ]), [advice, summary]);

  const lineData = useMemo(() => (history || []).map((h, i) => ({ idx: i + 1, reduction: Math.round(h.reduction_pct || 0) })), [history]);

  if (loading || !advice) {
    return (
      <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1100px] mx-auto space-y-4">
        <Skeleton className="h-8 w-56 bg-[color:var(--surface-800)]" />
        <Skeleton className="h-40 rounded-[14px] bg-[color:var(--surface-800)]" />
        <Skeleton className="h-56 rounded-[14px] bg-[color:var(--surface-800)]" />
      </div>
    );
  }

  const reduction = advice.estimated_reduction_pct;

  return (
    <div data-testid={USAGE.page} className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1100px] mx-auto">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Usage</div>
          <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">Make your AI credits go further</h1>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">Everything here is an estimate based on your own project data.</p>
        </div>
      </div>

      <Tabs defaultValue="simple" className="mt-6">
        <TabsList data-testid={USAGE.viewToggle} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)]">
          <TabsTrigger value="simple" className="data-[state=active]:bg-[color:var(--bg-900)] data-[state=active]:text-[color:var(--teal-300)]">Simple view</TabsTrigger>
          <TabsTrigger value="advanced" className="data-[state=active]:bg-[color:var(--bg-900)] data-[state=active]:text-[color:var(--teal-300)]">Advanced view</TabsTrigger>
        </TabsList>

        {/* SIMPLE */}
        <TabsContent value="simple" className="mt-5 space-y-4">
          <Card data-testid={USAGE.simpleMetric} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-6 sm:p-8">
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Your estimated savings</div>
              <div className="mt-3 flex items-end gap-3 flex-wrap">
                <span className="metric-num text-6xl leading-none text-[color:var(--mint-400)]">{reduction}%</span>
                <span className="text-sm text-[color:var(--ink-400)] pb-2">of unnecessary AI context removed</span>
              </div>
              <p className="mt-3 text-sm text-[color:var(--ink-400)] max-w-[560px]">
                You saved approximately <span className="text-[color:var(--ink-50)]">{formatTokens(advice.information_saved_tokens)}</span> of
                information your AI didn&rsquo;t need to reprocess.
              </p>
            </CardContent>
          </Card>

          {/* Credit savings */}
          <Card data-testid={USAGE.creditCard} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-6">
              <div className="flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-[color:var(--amber-500)]" />
                <div className="text-lg font-semibold">Before you buy more AI credits&hellip;</div>
              </div>
              <div className="mt-4 grid grid-cols-1 sm:grid-cols-[1fr_1px_1fr] gap-6 items-center">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">You&rsquo;ve used (estimated)</div>
                  <div className="mt-2 metric-num text-4xl text-[color:var(--ink-50)]">{advice.current_usage_pct}%</div>
                  <div className="text-xs text-[color:var(--ink-400)]">of your monthly AI allowance</div>
                  <Progress value={advice.current_usage_pct} className="mt-3 h-2 bg-[color:var(--surface-800)]" />
                </div>
                <div className="hidden sm:block h-16 w-px bg-[color:var(--border-700)]" />
                <div>
                  <p className="text-sm text-[color:var(--ink-200)]">
                    A large part of your recent usage came from <span className="text-[color:var(--amber-500)]">repeated or unnecessary information</span> ({advice.unnecessary_pct}%, estimated).
                  </p>
                  <Button onClick={() => navigate('/app/projects')} className="mt-4 bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
                    Optimize your AI usage <ArrowRight className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Plan advisor */}
          <Card data-testid={USAGE.planAdvisor} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-6">
              <div className="flex items-center gap-2">
                <Gauge className="w-4 h-4 text-[color:var(--teal-300)]" />
                <div className="text-lg font-semibold">Do you really need to upgrade?</div>
              </div>
              <div className="mt-5 grid grid-cols-1 sm:grid-cols-3 gap-3">
                <AdvisorStat label="Current usage" value={`${advice.current_usage_pct}%`} tone="muted" />
                <AdvisorStat label="Potential unnecessary" value={`${advice.unnecessary_pct}%`} tone="warning" />
                <AdvisorStat label="Estimated optimized usage" value={`${advice.optimized_usage_pct}%`} tone="success" />
              </div>
              <div className={`mt-4 rounded-[12px] border p-4 flex items-start gap-3 ${
                advice.can_stay_on_plan
                  ? 'border-[rgba(93,226,180,0.30)] bg-[rgba(93,226,180,0.06)]'
                  : 'border-[rgba(246,193,119,0.30)] bg-[rgba(246,193,119,0.06)]'
              }`}>
                <CheckCircle2 className={`w-4 h-4 mt-0.5 ${advice.can_stay_on_plan ? 'text-[color:var(--mint-400)]' : 'text-[color:var(--amber-500)]'}`} />
                <div>
                  <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Recommendation</div>
                  <div className="text-sm text-[color:var(--ink-50)] mt-0.5">{advice.recommendation}</div>
                </div>
              </div>
              <div className="mt-3 text-[11px] font-mono text-[color:var(--ink-600)] leading-relaxed">{advice.disclaimer}</div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ADVANCED */}
        <TabsContent value="advanced" className="mt-5 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Card data-testid={USAGE.advancedOriginal} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
              <CardContent className="p-5">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Original context</div>
                <div className="mt-2 metric-num text-3xl text-[color:var(--ink-50)]">{formatTokens(advice.original_tokens)}</div>
                <div className="text-xs text-[color:var(--ink-400)] font-mono">tokens · estimated</div>
              </CardContent>
            </Card>
            <Card data-testid={USAGE.advancedOptimized} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
              <CardContent className="p-5">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Optimized context</div>
                <div className="mt-2 metric-num text-3xl text-[color:var(--mint-400)]">{formatTokens(advice.optimized_tokens)}</div>
                <div className="text-xs text-[color:var(--ink-400)] font-mono">tokens · estimated</div>
              </CardContent>
            </Card>
            <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
              <CardContent className="p-5">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Estimated reduction</div>
                <div className="mt-2 metric-num text-3xl text-[color:var(--teal-300)]">{reduction}%</div>
                <div className="text-xs text-[color:var(--ink-400)] font-mono">chars/4 heuristic</div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
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
            <div className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Reduction over time</div>
              {lineData.length === 0 ? (
                <div className="mt-3 text-sm text-[color:var(--ink-400)]">No history yet — update an AI Memory to see this chart.</div>
              ) : (
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
              )}
            </div>
          </div>
          <div className="text-[11px] font-mono text-[color:var(--ink-600)]">Token counts are estimated (chars/4). OverHaust doesn&rsquo;t control third-party AI provider billing.</div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function AdvisorStat({ label, value, tone }) {
  const cls = tone === 'success'
    ? 'text-[color:var(--mint-400)]'
    : tone === 'warning'
    ? 'text-[color:var(--amber-500)]'
    : 'text-[color:var(--ink-50)]';
  return (
    <div className="rounded-[12px] border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40 p-4">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">{label}</div>
      <div className={`mt-2 metric-num text-2xl ${cls}`}>{value}</div>
    </div>
  );
}
