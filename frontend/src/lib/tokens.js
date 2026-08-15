// Small deterministic helpers used across the app.
// TokenEstimator abstraction: chars/4 heuristic — clearly labeled "estimated" in UI.

export function estimateTokens(text) {
  if (!text) return 0;
  return Math.max(1, Math.floor(text.length / 4));
}

export function formatTokens(n) {
  if (n == null || isNaN(n)) return '—';
  const num = Math.round(n);
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(num >= 10_000_000 ? 0 : 2) + 'M';
  if (num >= 1_000) return (num / 1_000).toFixed(num >= 10_000 ? 0 : 1) + 'k';
  return String(num);
}

export function formatPct(n, digits = 1) {
  if (n == null || isNaN(n)) return '—';
  return n.toFixed(digits) + '%';
}

export function formatRelativeTime(iso) {
  if (!iso) return 'never';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 'never';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

export function bytesFormat(n) {
  if (n == null) return '—';
  if (n < 1024) return n + ' B';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
  return (n / (1024 * 1024)).toFixed(2) + ' MB';
}
