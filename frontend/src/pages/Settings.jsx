import React, { useState } from 'react';
import { useAuth } from '@/lib/auth';
import LocalCacheStatus from '@/components/LocalCacheStatus';
import { clearAllLocal } from '@/lib/idb';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Card, CardContent } from '@/components/ui/card';
import { LogOut, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Settings() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const clearLocal = async () => {
    if (!window.confirm('Clear local IndexedDB cache? Server-side data will remain intact.')) return;
    setBusy(true);
    try {
      await clearAllLocal();
      toast.success('Local cache cleared');
    } finally { setBusy(false); }
  };

  return (
    <div className="px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-[900px] mx-auto space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Settings</div>
        <h1 className="mt-1 text-2xl sm:text-3xl font-semibold">Your workspace</h1>
      </div>

      <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
        <CardContent className="p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Account</div>
          <div className="mt-2 flex items-center justify-between">
            <div>
              <div className="text-sm text-[color:var(--ink-50)] font-mono">{user?.email}</div>
              <div className="text-xs text-[color:var(--ink-400)]">Signed in with email</div>
            </div>
            <Button variant="secondary" onClick={() => { logout(); navigate('/'); }} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
              <LogOut className="w-3.5 h-3.5" /> Sign out
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
        <CardContent className="p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Your AI memory (on this device)</div>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">Your knowledge stays close to you and is ready whenever your AI needs it — kept in your browser for fast, private access.</p>
          <div className="mt-3">
            <LocalCacheStatus />
          </div>
          <div className="mt-3">
            <Button variant="secondary" onClick={clearLocal} disabled={busy} className="bg-[color:var(--surface-800)] border border-[color:var(--border-700)] gap-2">
              <Trash2 className="w-3.5 h-3.5" /> Clear local memory
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="bg-[color:var(--surface-850)] border-[color:var(--border-700)]">
        <CardContent className="p-5">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">About</div>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">
            OverHaust is a universal AI memory layer. It helps your AI remember what matters so you use fewer tokens and
            get more from the AI you already use. Savings shown are estimates; nothing is shared beyond the AI calls needed
            to organize your information.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
