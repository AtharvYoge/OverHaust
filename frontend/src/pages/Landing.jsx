import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowUpRight, Cpu, Braces, ChevronRight, Boxes, Layers, ShieldCheck, Zap, Gauge, Waves } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LANDING } from '@/constants/testIds';
import FlowDiagram from '@/components/FlowDiagram';

export default function Landing() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen bg-[color:var(--bg-950)] text-[color:var(--ink-50)] relative overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-grid bg-grid-fade opacity-30" />
        <div className="absolute inset-x-0 top-0 h-[70vh] bg-[radial-gradient(900px_circle_at_20%_10%,rgba(32,178,170,0.18),transparent_55%),radial-gradient(700px_circle_at_80%_20%,rgba(93,226,180,0.10),transparent_60%)]" />
      </div>

      {/* Nav */}
      <header className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pt-6 flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-[color:var(--teal-400)] to-[color:var(--teal-500)] flex items-center justify-center shadow-[0_0_0_1px_rgba(53,199,191,0.35),0_6px_20px_rgba(32,178,170,0.35)]">
            <Layers className="w-4 h-4 text-[color:var(--bg-950)]" strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">OverHaust</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-[color:var(--ink-600)]">Context Runtime</div>
          </div>
        </Link>
        <div className="flex-1" />
        <nav className="hidden md:flex items-center gap-6 text-sm text-[color:var(--ink-300)]">
          <a href="#how" className="hover:text-[color:var(--ink-50)]">How it works</a>
          <a href="#architecture" className="hover:text-[color:var(--ink-50)]">Architecture</a>
          <a href="#mcp" className="hover:text-[color:var(--ink-50)]">MCP</a>
        </nav>
        <Button
          variant="secondary"
          className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)]"
          onClick={() => navigate('/login')}
        >
          Sign in
        </Button>
      </header>

      {/* Hero */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pt-16 sm:pt-24 pb-14">
        <div className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-700)] bg-[color:var(--surface-850)] px-3 py-1 text-[11px] font-mono text-[color:var(--ink-300)]">
          <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--mint-400)]" />
          Prototype — Context Runtime for AI coding agents
        </div>
        <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-semibold leading-[1.05] tracking-[-0.03em]">
          Less context.<br />
          <span className="bg-gradient-to-r from-[color:var(--teal-300)] via-[color:var(--mint-400)] to-[color:var(--teal-300)] bg-clip-text text-transparent">
            More intelligence.
          </span>
        </h1>
        <p className="mt-5 max-w-[640px] text-[color:var(--ink-300)] text-base sm:text-lg leading-relaxed">
          OverHaust turns your project&rsquo;s conversations, code, documentation, and decisions into
          a compact, persistent knowledge layer for AI coding agents. Compress once. Serve only what matters.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button
            size="lg"
            data-testid={LANDING.primaryCta}
            onClick={() => navigate('/login')}
            className="h-11 bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2"
          >
            Try the prototype <ArrowRight className="w-4 h-4" />
          </Button>
          <Button
            size="lg"
            variant="secondary"
            data-testid={LANDING.secondaryCta}
            onClick={() => document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' })}
            className="h-11 bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-2"
          >
            See how it works <ChevronRight className="w-4 h-4" />
          </Button>
        </div>

        <div className="mt-12 sm:mt-16 rounded-[20px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)]/60 backdrop-blur">
          <FlowDiagram testId={LANDING.flow} />
        </div>
      </section>

      {/* Feature strip */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14 grid grid-cols-1 md:grid-cols-3 gap-4">
        <Feature icon={Braces} title="Persistent Context Cache" body="Structured Project Knowledge stored locally in IndexedDB and on the server. Ready for any task." />
        <Feature icon={Gauge} title="Task-specific relevance" body="Ask about a bug or feature and OverHaust returns only the components, decisions, and memory that matter." />
        <Feature icon={Zap} title="Estimated 70–95% reduction" body="On realistic prototype data. Token counts shown are estimated (chars/4) and clearly labeled." />
      </section>

      {/* How it works */}
      <section id="how" className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-8">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">How it works</div>
            <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">A runtime, not a wrapper.</h2>
            <p className="mt-3 text-sm text-[color:var(--ink-400)] max-w-[280px]">
              Bring your raw project. We keep only the durable knowledge.
            </p>
          </div>
          <ol className="space-y-3">
            {[
              ['01', 'Ingest', 'Paste conversations. Drop project files. Add docs and notes.'],
              ['02', 'Analyze', 'The Context Runtime extracts identity, architecture, components, decisions, current state, and memory.'],
              ['03', 'Compress', 'Redundant chatter and irrelevant marketing are dropped. Memory is bucketed distinctly.'],
              ['04', 'Assemble', 'Per task, only the relevant subset is returned as a copyable context block.'],
            ].map(([n, t, b]) => (
              <li key={n} className="grid grid-cols-[48px_1fr] gap-4 rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-4">
                <div className="text-lg font-mono text-[color:var(--teal-300)]">{n}</div>
                <div>
                  <div className="text-sm font-semibold">{t}</div>
                  <div className="text-sm text-[color:var(--ink-400)] mt-0.5">{b}</div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Architecture */}
      <section id="architecture" className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Architecture</div>
        <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">Clean abstractions. Swappable models.</h2>
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {[
            ['LLMProvider', 'Emergent LLM Key (default)'],
            ['ContextAnalyzer', 'Extracts structured knowledge'],
            ['ContextCompressor', 'Drops noise & duplicates'],
            ['ProjectIndexer', 'Files, docs, conversations'],
            ['MemoryEngine', '5 memory buckets'],
            ['ContextAssembler', 'Task-relevance selection'],
            ['TokenEstimator', 'Deterministic estimation'],
            ['CacheManager', 'Mongo + IndexedDB'],
          ].map(([n, s]) => (
            <div key={n} className="rounded-[12px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-3">
              <div className="text-[13px] font-mono text-[color:var(--ink-50)]">{n}</div>
              <div className="text-[11px] text-[color:var(--ink-400)] font-mono mt-0.5">{s}</div>
            </div>
          ))}
        </div>
      </section>

      {/* MCP */}
      <section id="mcp" className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 py-14">
        <div className="rounded-[20px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-6 sm:p-10 relative overflow-hidden">
          <div className="absolute -top-16 -right-24 w-[420px] h-[420px] bg-[radial-gradient(circle,rgba(32,178,170,0.16),transparent_60%)] pointer-events-none" />
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-8 relative">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Coming soon</div>
              <h2 className="mt-2 text-2xl sm:text-3xl font-semibold">Ship context via MCP.</h2>
              <p className="mt-3 text-sm text-[color:var(--ink-400)] max-w-[520px]">
                Your AI agent will be able to request project knowledge on demand — no more manual copy/paste.
              </p>
              <div className="mt-6 rounded-[12px] bg-black/40 border border-[color:var(--border-700)] p-4 font-mono text-sm text-[color:var(--ink-200)]">
                <span className="text-[color:var(--ink-600)]">$</span> npx context-runtime-mcp
              </div>
            </div>
            <ul className="space-y-1.5 text-sm font-mono">
              {['get_project_context()', 'get_relevant_context(task)', 'search_project_knowledge()', 'get_memory()', 'update_memory()'].map((t) => (
                <li key={t} className="flex items-center gap-2 text-[color:var(--ink-200)]">
                  <ArrowUpRight className="w-3.5 h-3.5 text-[color:var(--teal-300)]" /> {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 lg:px-8 pb-24">
        <div className="rounded-[20px] border border-[color:var(--border-700)] bg-gradient-to-br from-[color:var(--surface-850)] to-[color:var(--bg-900)] p-8 sm:p-10 flex flex-col sm:flex-row items-start sm:items-center gap-6">
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Try it now</div>
            <h3 className="mt-2 text-xl sm:text-2xl font-semibold">Preloaded LabKOT project. One click.</h3>
            <p className="mt-2 text-sm text-[color:var(--ink-400)] max-w-[520px]">
              Explore a realistic Flutter/Dart/SQLite/WebSocket codebase with a messy conversation history and see the compression in action.
            </p>
          </div>
          <Button
            size="lg"
            onClick={() => navigate('/login')}
            className="h-11 bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2"
          >
            Open the prototype <ArrowRight className="w-4 h-4" />
          </Button>
        </div>

        <div className="mt-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] font-mono text-[color:var(--ink-600)]">
          <div>OverHaust · Context Runtime prototype</div>
          <div>Numbers shown are estimated. No production data is stored.</div>
        </div>
      </section>
    </div>
  );
}

function Feature({ icon: Icon, title, body }) {
  return (
    <div className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-5">
      <div className="w-8 h-8 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
        <Icon className="w-4 h-4" />
      </div>
      <div className="mt-4 text-base font-semibold">{title}</div>
      <div className="mt-1.5 text-sm text-[color:var(--ink-400)] leading-relaxed">{body}</div>
    </div>
  );
}
