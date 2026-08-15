import React, { useEffect, useState, useCallback } from 'react';
import { getLocalStats } from '@/lib/idb';
import { formatRelativeTime, bytesFormat } from '@/lib/tokens';
import { HardDrive, RefreshCw } from 'lucide-react';
import { SETTINGS } from '@/constants/testIds';

export default function LocalCacheStatus() {
  const [stats, setStats] = useState({
    projects_with_cache: 0,
    task_runs: 0,
    knowledge_items: 0,
    approx_size_bytes: 0,
    last_updated: null,
  });
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const s = await getLocalStats();
      setStats(s);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const active = stats.projects_with_cache > 0;

  return (
    <div
      data-testid={SETTINGS.status}
      className="rounded-lg border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-3"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HardDrive className="w-3.5 h-3.5 text-[color:var(--ink-400)]" />
          <span className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Local cache</span>
        </div>
        <button
          data-testid={SETTINGS.refresh}
          className="p-1 rounded hover:bg-[rgba(233,238,245,0.06)] text-[color:var(--ink-400)]"
          onClick={refresh}
          aria-label="Refresh local cache stats"
        >
          <RefreshCw className={`w-3 h-3 ${busy ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full border ${
            active
              ? 'bg-[rgba(93,226,180,0.12)] text-[color:var(--mint-400)] border-[rgba(93,226,180,0.28)]'
              : 'bg-[rgba(233,238,245,0.05)] text-[color:var(--ink-400)] border-[color:var(--border-700)]'
          }`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-[color:var(--mint-400)]' : 'bg-[color:var(--ink-600)]'}`} />
          {active ? 'Active' : 'Idle'}
        </span>
        <span className="text-[10px] text-[color:var(--ink-600)]">{formatRelativeTime(stats.last_updated)}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] font-mono tabular text-[color:var(--ink-200)]">
        <div>{stats.knowledge_items} items</div>
        <div className="text-right text-[color:var(--ink-400)]">{bytesFormat(stats.approx_size_bytes)}</div>
      </div>
    </div>
  );
}
