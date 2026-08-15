import React from 'react';
import { INTEGRATIONS } from '@/constants/testIds';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ArrowUpRight, Terminal, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

const AGENTS = [
  { key: 'cursor', name: 'Cursor', tagline: 'Terminal-native AI coding agent', tid: INTEGRATIONS.cursor },
  { key: 'replit', name: 'Replit', tagline: 'Cloud IDE agent' },
  { key: 'claude', name: 'Claude Code', tagline: 'Anthropic’s CLI agent' },
  { key: 'windsurf', name: 'Windsurf', tagline: 'Editor × agent' },
  { key: 'vscode', name: 'VS Code', tagline: 'MCP-capable editor' },
];

const TOOLS = [
  { name: 'get_project_context', desc: 'Return the full compressed Context Cache.' },
  { name: 'get_relevant_context(task)', desc: 'Assemble only the pieces relevant to a coding task.' },
  { name: 'search_project_knowledge()', desc: 'Search across identity, architecture, memory buckets.' },
  { name: 'get_memory()', desc: 'Read the 5 memory buckets.' },
  { name: 'update_memory()', desc: 'Append or resolve items in memory buckets.' },
];

export default function Integrations() {
  const copyInstall = async () => {
    try {
      await navigator.clipboard.writeText('npx context-runtime-mcp');
      toast.success('Copied install command');
    } catch { toast.error('Copy failed'); }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Integrations</div>
      <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">Ship context via MCP</h1>
      <p className="mt-1 text-sm text-[color:var(--ink-400)] max-w-[720px]">
        Your AI coding agent will be able to query OverHaust for the exact context it needs — no more copy-paste.
        This page is a preview of the future MCP integration.
      </p>

      <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {AGENTS.map((a) => (
          <Card key={a.key} data-testid={a.tid} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="font-semibold text-[color:var(--ink-50)]">{a.name}</div>
                <Badge variant="outline" className="bg-[rgba(246,193,119,0.10)] text-[color:var(--amber-500)] border-[rgba(246,193,119,0.28)] rounded-full text-[10px]">Coming soon</Badge>
              </div>
              <div className="mt-1 text-xs text-[color:var(--ink-400)]">{a.tagline}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
          <CardContent className="p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Prototype install</div>
            <div data-testid={INTEGRATIONS.install} className="mt-2 rounded-[12px] bg-black/40 border border-[color:var(--border-700)] p-4 font-mono text-sm text-[color:var(--ink-200)] flex items-center gap-2">
              <Terminal className="w-3.5 h-3.5 text-[color:var(--ink-400)]" />
              <span className="flex-1">npx context-runtime-mcp</span>
              <Button size="sm" onClick={copyInstall} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-1">
                <Copy className="w-3 h-3" /> Copy
              </Button>
            </div>
            <p className="mt-3 text-xs text-[color:var(--ink-400)]">
              The command above is a placeholder for the prototype. The MCP server will publish once the runtime SDK is public.
            </p>
          </CardContent>
        </Card>

        <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
          <CardContent className="p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">MCP tools</div>
            <ul data-testid={INTEGRATIONS.tools} className="mt-2 space-y-1.5">
              {TOOLS.map((t) => (
                <li key={t.name} className="flex items-start gap-2">
                  <ArrowUpRight className="w-3.5 h-3.5 text-[color:var(--teal-300)] mt-0.5" />
                  <div>
                    <div className="font-mono text-sm text-[color:var(--ink-50)]">{t.name}</div>
                    <div className="text-xs text-[color:var(--ink-400)]">{t.desc}</div>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
