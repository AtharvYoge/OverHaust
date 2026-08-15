import React, { useEffect, useState } from 'react';
import { ConnectionAPI } from '@/lib/api';
import { CONNECTIONS } from '@/constants/testIds';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Plug, Check, Loader2, Info } from 'lucide-react';
import { toast } from 'sonner';

const STATUS_META = {
  available: { label: 'Available', cls: 'bg-[rgba(93,226,180,0.12)] text-[color:var(--mint-400)] border-[rgba(93,226,180,0.28)]' },
  agent_connection: { label: 'Agent Connection', cls: 'bg-[rgba(106,169,255,0.12)] text-[color:var(--blue-500)] border-[rgba(106,169,255,0.28)]' },
  coming_soon: { label: 'Coming Soon', cls: 'bg-[rgba(246,193,119,0.12)] text-[color:var(--amber-500)] border-[rgba(246,193,119,0.28)]' },
};

export default function Connections() {
  const [catalog, setCatalog] = useState([]);
  const [connected, setConnected] = useState([]); // list of Connection
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState(null);

  const load = async () => {
    try {
      const [cat, conns] = await Promise.all([ConnectionAPI.catalog(), ConnectionAPI.list()]);
      setCatalog(cat || []);
      setConnected(conns || []);
    } catch (e) {
      toast.error('Could not load connections');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const connFor = (key) => connected.find((c) => c.agent_key === key);

  const toggle = async (agent) => {
    const existing = connFor(agent.key);
    setBusyKey(agent.key);
    try {
      if (existing) {
        await ConnectionAPI.disconnect(existing.id);
        setConnected((prev) => prev.filter((c) => c.id !== existing.id));
        toast.success(`${agent.name} disconnected`);
      } else {
        const created = await ConnectionAPI.connect(agent.key, agent.name);
        setConnected((prev) => [created, ...prev]);
        toast.success(`${agent.name} connected`, { description: 'Prototype link — no live data pipe yet.' });
      }
    } catch (e) {
      toast.error('Action failed', { description: String(e?.response?.data?.detail || e?.message || e) });
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div data-testid={CONNECTIONS.page} className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[1400px] mx-auto">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-md bg-[rgba(53,199,191,0.10)] border border-[rgba(53,199,191,0.28)] flex items-center justify-center text-[color:var(--teal-300)]">
          <Plug className="w-4.5 h-4.5" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Connections</div>
          <h1 className="text-2xl sm:text-3xl font-semibold">Connect the AI agents you already use</h1>
        </div>
      </div>
      <p className="mt-3 text-sm text-[color:var(--ink-400)] max-w-[720px]">
        OverHaust is built as an open connection layer, so your AI memory can work with many agents over time.
        We keep statuses honest — planned tools are clearly marked and connecting is a prototype link.
      </p>

      {loading ? (
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-[12px] bg-[color:var(--surface-800)]" />
          ))}
        </div>
      ) : (
        <div data-testid={CONNECTIONS.grid} className="mt-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {catalog.map((a) => {
            const meta = STATUS_META[a.status] || STATUS_META.coming_soon;
            const connectable = a.status === 'available' || a.status === 'agent_connection';
            const isConnected = !!connFor(a.key);
            const busy = busyKey === a.key;
            return (
              <Card key={a.key} data-testid={CONNECTIONS.card(a.key)} className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
                <CardContent className="p-4 flex flex-col gap-3 h-full">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-semibold text-[color:var(--ink-50)]">{a.name}</div>
                      <div className="text-[11px] text-[color:var(--ink-400)]">{a.category}</div>
                    </div>
                    <Badge variant="outline" className={`rounded-full text-[10px] ${meta.cls}`}>{meta.label}</Badge>
                  </div>
                  <div className="mt-auto">
                    {connectable ? (
                      <Button
                        size="sm"
                        onClick={() => toggle(a)}
                        disabled={busy}
                        data-testid={CONNECTIONS.connectBtn(a.key)}
                        variant={isConnected ? 'secondary' : 'default'}
                        className={isConnected
                          ? 'w-full bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] gap-2'
                          : 'w-full bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2'}
                      >
                        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : isConnected ? <Check className="w-3.5 h-3.5" /> : <Plug className="w-3.5 h-3.5" />}
                        {isConnected ? 'Connected' : 'Connect'}
                      </Button>
                    ) : (
                      <Button size="sm" disabled className="w-full bg-[color:var(--surface-800)] border border-[color:var(--border-700)] opacity-60 cursor-not-allowed">
                        Coming soon
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Card className="mt-6 bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
        <CardContent className="p-5 flex items-start gap-3">
          <Info className="w-4 h-4 text-[color:var(--ink-400)] mt-0.5" />
          <div>
            <div className="text-sm text-[color:var(--ink-50)]">What is &ldquo;Agent Connection&rdquo;?</div>
            <p className="mt-1 text-sm text-[color:var(--ink-400)] max-w-[720px]">
              Some tools can access your AI memory through a generic agent connection today. Others are on the way.
              Future connection methods may include desktop, browser and editor integrations. Connecting here creates a
              prototype link only — it does not yet stream live data to a third-party provider.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
