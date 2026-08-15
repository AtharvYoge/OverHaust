import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight, ChevronRight, Layers, Zap, Clock, CreditCard, RefreshCw, TrendingDown,
  Code2, Sparkles, PenTool, Rocket, FlaskConical, GraduationCap, Building2, Check, Plug,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { LANDING } from '@/constants/testIds';
import MemoryLayerVisual from '@/components/MemoryLayerVisual';
import BeforeAfterBars from '@/components/BeforeAfterBars';

const PAINS = [
  { icon: Zap, title: 'My tokens disappear too quickly.', body: 'You start working with an AI and suddenly your usage is almost gone.' },
  { icon: CreditCard, title: "I'm constantly buying credit packs.", body: "You shouldn't have to keep paying extra just because your AI has too much to process." },
  { icon: TrendingDown, title: "I'm upgrading my plan just for more usage.", body: 'You may not need a bigger plan. You may simply be sending too much unnecessary information.' },
  { icon: RefreshCw, title: 'My AI keeps going over the same things.', body: 'Your conversations, files, instructions and past decisions keep getting repeated.' },
  { icon: Clock, title: 'Responses are getting slower.', body: 'The more information your AI has to process, the more work it does before responding.' },
];

const AUDIENCE = [
  { icon: Code2, title: 'Developers', body: 'Get more from Cursor, Claude Code, Replit and coding agents.' },
  { icon: Sparkles, title: 'Vibe Coders', body: 'Build apps without constantly worrying about hitting usage limits.' },
  { icon: PenTool, title: 'Creators', body: 'Keep projects, ideas, scripts and research organized for AI.' },
  { icon: Rocket, title: 'Founders', body: 'Give your AI agents persistent knowledge about your company and projects.' },
  { icon: FlaskConical, title: 'Researchers', body: 'Keep large amounts of research available without resending everything.' },
  { icon: GraduationCap, title: 'Students', body: 'Keep notes, study material and project information available to AI.' },
  { icon: Building2, title: 'Businesses', body: 'Give AI agents a reliable knowledge layer across large amounts of information.' },
];

const AGENTS = [
  { name: 'Cursor', status: 'available' },
  { name: 'Claude', status: 'available' },
  { name: 'ChatGPT', status: 'available' },
  { name: 'Claude Code', status: 'agent_connection' },
  { name: 'Replit', status: 'agent_connection' },
  { name: 'Gemini', status: 'coming_soon' },
  { name: 'Windsurf', status: 'coming_soon' },
  { name: 'OpenHands', status: 'coming_soon' },
  { name: 'OpenClaw', status: 'coming_soon' },
  { name: 'Hermes', status: 'coming_soon' },
];

const STATUS_META = {
  available: { label: 'Available', cls: 'bg-[rgba(93,226,180,0.12)] text-[color:var(--mint-400)] border-[rgba(93,226,180,0.28)]' },
  agent_connection: { label: 'Agent Connection', cls: 'bg-[rgba(106,169,255,0.12)] text-[color:var(--blue-500)] border-[rgba(106,169,255,0.28)]' },
  coming_soon: { label: 'Coming Soon', cls: 'bg-[rgba(246,193,119,0.12)] text-[color:var(--amber-500)] border-[rgba(246,193,119,0.28)]' },
};

const PLANS = [
  { name: 'Free', price: '$0', tagline: 'For trying the product', features: ['1 project', 'Add your own knowledge', 'Prepare context for any AI', 'Local-first memory'], cta: 'Try It Free', highlight: false },
  { name: 'Pro', price: 'Soon', tagline: 'For individuals who use AI heavily', features: ['Unlimited projects', 'Larger AI memory', 'Usage savings insights', 'Priority processing'], cta: 'Join waitlist', highlight: true },
  { name: 'Team', price: 'Soon', tagline: 'For teams sharing AI knowledge', features: ['Shared team memory', 'Multiple connected agents', 'Team usage analytics', 'Encrypted sync (planned)'], cta: 'Join waitlist', highlight: false },
];

export default function Landing() {
  const navigate = useNavigate();
  const goApp = () => navigate('/login');

  return (
    <div className="min-h-screen bg-[color:var(--bg-950)] text-[color:var(--ink-50)] relative overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-grid bg-grid-fade opacity-30" />
        <div className="absolute inset-x-0 top-0 h-[70vh] bg-[radial-gradient(900px_circle_at_20%_10%,rgba(32,178,170,0.16),transparent_55%),radial-gradient(700px_circle_at_80%_15%,rgba(93,226,180,0.10),transparent_60%)]" />
      </div>

      {/* Nav */}
      <header className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pt-6 flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-[color:var(--teal-400)] to-[color:var(--teal-500)] flex items-center justify-center shadow-[0_0_0_1px_rgba(53,199,191,0.35),0_6px_20px_rgba(32,178,170,0.35)]">
            <Layers className="w-4 h-4 text-[color:var(--bg-950)]" strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">OverHaust</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ink-600)]">AI Memory Layer</div>
          </div>
        </Link>
        <div className="flex-1" />
        <nav className="hidden md:flex items-center gap-6 text-sm text-[color:var(--ink-200)]">
          <a href="#how" className="hover:text-[color:var(--ink-50)]">How it works</a>
          <a href="#audience" className="hover:text-[color:var(--ink-50)]">Who it's for</a>
          <a href="#pricing" className="hover:text-[color:var(--ink-50)]">Pricing</a>
        </nav>
        <Button
          variant="secondary"
          data-testid={LANDING.signIn}
          className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)]"
          onClick={goApp}
        >
          Sign in
        </Button>
      </header>

      {/* Hero */}
      <section data-testid={LANDING.hero} className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pt-14 sm:pt-20 pb-10">
        <div className="grid grid-cols-1 lg:grid-cols-[1.05fr_1fr] gap-10 items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-700)] bg-[color:var(--surface-850)] px-3 py-1 text-[11px] font-mono text-[color:var(--ink-200)]">
              <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--mint-400)]" />
              Use less. Remember more. Get more done.
            </div>
            <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-semibold leading-[1.05] tracking-[-0.03em]">
              Are Your AI Tokens<br />
              <span className="bg-gradient-to-r from-[color:var(--teal-300)] via-[color:var(--mint-400)] to-[color:var(--teal-300)] bg-clip-text text-transparent">
                Finishing Too Fast?
              </span>
            </h1>
            <p className="mt-5 max-w-[560px] text-[color:var(--ink-200)] text-base sm:text-lg leading-relaxed">
              Your AI shouldn&rsquo;t have to reread everything every time. OverHaust remembers the important stuff,
              removes unnecessary repetition, and helps you get more from the AI credits you already have.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button
                size="lg"
                data-testid={LANDING.primaryCta}
                onClick={goApp}
                className="h-11 bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2"
              >
                Try It Free <ArrowRight className="w-4 h-4" />
              </Button>
              <Button
                size="lg"
                variant="secondary"
                data-testid={LANDING.secondaryCta}
                onClick={() => document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' })}
                className="h-11 bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-2"
              >
                See How It Works <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
            <div className="mt-5 text-[13px] text-[color:var(--ink-400)]">
              Make your AI credits go further — without buying a bigger plan.
            </div>
          </div>

          <MemoryLayerVisual testId={LANDING.flow} />
        </div>
      </section>

      {/* Before / after strip */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pb-6">
        <div className="rounded-[20px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-6 sm:p-8 grid grid-cols-1 lg:grid-cols-[1fr_1.2fr] gap-8 items-center">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">The difference</div>
            <h2 className="mt-2 text-2xl font-semibold">Same project. Far less waste.</h2>
            <p className="mt-2 text-sm text-[color:var(--ink-400)] max-w-[420px]">
              Instead of sending your AI everything every time, OverHaust sends only what it needs right now.
            </p>
          </div>
          <BeforeAfterBars reductionPct={65} />
        </div>
      </section>

      {/* Pain points */}
      <section data-testid={LANDING.painSection} className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Sound familiar?</div>
        <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">The problem isn&rsquo;t your AI. It&rsquo;s how much it has to process.</h2>
        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {PAINS.map((p) => (
            <div key={p.title} className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5 hover:border-[color:var(--border-650)] transition-colors">
              <div className="w-8 h-8 rounded-md bg-[rgba(246,193,119,0.10)] border border-[rgba(246,193,119,0.28)] flex items-center justify-center text-[color:var(--amber-500)]">
                <p.icon className="w-4 h-4" />
              </div>
              <div className="mt-4 text-base font-semibold">&ldquo;{p.title}&rdquo;</div>
              <div className="mt-1.5 text-sm text-[color:var(--ink-400)] leading-relaxed">{p.body}</div>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">How it works</div>
        <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">Three simple steps.</h2>
        <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { n: '01', icon: Plug, t: 'Connect', b: 'Connect your AI or start a project.' },
            { n: '02', icon: Layers, t: 'Remember', b: 'We organize the important information your AI needs.' },
            { n: '03', icon: TrendingDown, t: 'Use Less', b: 'Your AI gets what it needs without reprocessing everything else.' },
          ].map((s) => (
            <div key={s.n} className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
              <div className="flex items-center justify-between">
                <div className="w-9 h-9 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
                  <s.icon className="w-4 h-4" />
                </div>
                <span className="text-lg font-mono text-[color:var(--ink-600)]">{s.n}</span>
              </div>
              <div className="mt-4 text-lg font-semibold">{s.t}</div>
              <div className="mt-1 text-sm text-[color:var(--ink-400)]">{s.b}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Audience */}
      <section id="audience" data-testid={LANDING.audienceSection} className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Not just for developers</div>
        <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">Built for anyone who uses AI.</h2>
        <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {AUDIENCE.map((a) => (
            <div key={a.title} className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5 hover:border-[color:var(--border-650)] transition-colors">
              <div className="w-8 h-8 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
                <a.icon className="w-4 h-4" />
              </div>
              <div className="mt-4 text-base font-semibold">{a.title}</div>
              <div className="mt-1.5 text-sm text-[color:var(--ink-400)] leading-relaxed">{a.body}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Agents */}
      <section data-testid={LANDING.agentsSection} className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="rounded-[20px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-6 sm:p-8">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Works with your tools</div>
          <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">Connect the AI agents you already use.</h2>
          <p className="mt-2 text-sm text-[color:var(--ink-400)] max-w-[640px]">
            OverHaust is built as an open connection layer so new AI agents can be supported over time.
            Statuses below are honest — planned integrations are marked clearly.
          </p>
          <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {AGENTS.map((a) => (
              <div key={a.name} className="rounded-[12px] border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/50 p-3 flex flex-col gap-2">
                <div className="text-sm font-semibold text-[color:var(--ink-50)]">{a.name}</div>
                <Badge variant="outline" className={`w-fit rounded-full text-[10px] ${STATUS_META[a.status].cls}`}>
                  {STATUS_META[a.status].label}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" data-testid={LANDING.pricingSection} className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Pricing</div>
        <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">Start free. Grow when you&rsquo;re ready.</h2>
        <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
          {PLANS.map((p, i) => (
            <div
              key={p.name}
              className={`rounded-[16px] border p-6 ${
                p.highlight
                  ? 'border-[rgba(53,199,191,0.45)] bg-[rgba(32,178,170,0.06)]'
                  : 'border-[color:var(--border-700)] bg-[color:var(--surface-850)]'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-lg font-semibold">{p.name}</div>
                {p.highlight && (
                  <Badge className="rounded-full bg-[color:var(--teal-500)] text-[color:var(--bg-950)] text-[10px]">Popular</Badge>
                )}
              </div>
              <div className="mt-2 metric-num text-3xl">{p.price}</div>
              <div className="mt-1 text-sm text-[color:var(--ink-400)]">{p.tagline}</div>
              <ul className="mt-4 space-y-2">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-[color:var(--ink-200)]">
                    <Check className="w-4 h-4 text-[color:var(--mint-400)] mt-0.5" /> {f}
                  </li>
                ))}
              </ul>
              <Button
                onClick={goApp}
                data-testid={i === 0 ? LANDING.pricingCtaFree : undefined}
                className={`mt-6 w-full ${
                  p.highlight
                    ? 'bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)]'
                    : 'bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)]'
                }`}
                variant={p.highlight ? 'default' : 'secondary'}
              >
                {p.cta}
              </Button>
            </div>
          ))}
        </div>
        <p className="mt-4 text-[11px] font-mono text-[color:var(--ink-600)]">
          Prototype pricing — final plans are not locked. Savings shown across the app are estimates.
        </p>
      </section>

      {/* Final CTA */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pb-24">
        <div className="rounded-[20px] border border-[color:var(--border-700)] bg-gradient-to-br from-[color:var(--surface-850)] to-[color:var(--bg-900)] p-8 sm:p-10 flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <div className="flex-1">
            <h3 className="text-xl sm:text-2xl font-semibold">Why buy more AI credits when you could just use them better?</h3>
            <p className="mt-2 text-sm text-[color:var(--ink-400)] max-w-[560px]">
              Load the demo and watch a long AI conversation shrink to only what matters — in seconds.
            </p>
          </div>
          <Button size="lg" onClick={goApp} className="h-11 bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2">
            Try It Free <ArrowRight className="w-4 h-4" />
          </Button>
        </div>
        <div className="mt-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] font-mono text-[color:var(--ink-600)]">
          <div>OverHaust · A universal memory layer for AI</div>
          <div>Savings are estimated. OverHaust doesn&rsquo;t control third-party AI billing.</div>
        </div>
      </section>
    </div>
  );
}
