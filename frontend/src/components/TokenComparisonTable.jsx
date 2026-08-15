import React from 'react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatTokens, formatPct } from '@/lib/tokens';
import { PROJECT } from '@/constants/testIds';

export default function TokenComparisonTable({ metrics }) {
  if (!metrics) return null;
  const rows = [
    { label: 'Tokens (estimated)', original: formatTokens(metrics.original_tokens), optimized: formatTokens(metrics.optimized_tokens) },
    { label: 'Context items', original: metrics.original_items, optimized: metrics.optimized_items },
    { label: 'Conversation messages', original: metrics.original_messages, optimized: metrics.optimized_messages },
    { label: 'Files referenced', original: metrics.original_files, optimized: metrics.optimized_files },
  ];

  return (
    <div data-testid={PROJECT.comparisonTable} className="rounded-[14px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="border-[color:var(--border-700)] hover:bg-transparent">
            <TableHead className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Metric</TableHead>
            <TableHead className="text-right text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Original</TableHead>
            <TableHead className="text-right text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Optimized</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.label} className="border-[color:var(--border-700)] hover:bg-[rgba(233,238,245,0.03)]">
              <TableCell className="text-sm text-[color:var(--ink-200)]">{r.label}</TableCell>
              <TableCell className="text-right font-mono tabular text-[color:var(--ink-400)]">{r.original ?? '—'}</TableCell>
              <TableCell className="text-right font-mono tabular text-[color:var(--ink-50)]">{r.optimized ?? '—'}</TableCell>
            </TableRow>
          ))}
          <TableRow className="border-[color:var(--border-700)] bg-[color:var(--bg-900)]/50">
            <TableCell className="text-sm text-[color:var(--ink-200)] font-medium">Estimated reduction</TableCell>
            <TableCell className="text-right font-mono tabular text-[color:var(--ink-400)]">—</TableCell>
            <TableCell className="text-right font-mono tabular text-[color:var(--mint-400)]">{formatPct(metrics.reduction_pct)}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}
