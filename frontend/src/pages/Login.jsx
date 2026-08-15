import React, { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { Layers, ArrowRight, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';
import { LOGIN } from '@/constants/testIds';

export default function Login() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!email || !email.includes('@')) {
      toast.error('Enter a valid email');
      return;
    }
    setLoading(true);
    try {
      await login(email);
      const dest = location.state?.from?.pathname || '/app';
      navigate(dest, { replace: true });
    } catch (err) {
      toast.error('Login failed', { description: String(err?.response?.data?.detail || err?.message || err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[color:var(--bg-950)] text-[color:var(--ink-50)] flex flex-col">
      <header className="px-6 py-5">
        <Link to="/" className="inline-flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-gradient-to-br from-[color:var(--teal-400)] to-[color:var(--teal-500)] flex items-center justify-center">
            <Layers className="w-4 h-4 text-[color:var(--bg-950)]" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-semibold tracking-tight">OverHaust</span>
        </Link>
      </header>
      <div className="flex-1 grid place-items-center px-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-grid bg-grid-fade opacity-30" />
        <div className="absolute inset-0 bg-[radial-gradient(600px_circle_at_50%_20%,rgba(32,178,170,0.16),transparent_60%)]" />
        <form onSubmit={submit} className="relative w-full max-w-[420px] rounded-[16px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] p-6 shadow-[var(--shadow-popover)]">
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">AI Memory Layer</div>
          <h1 className="mt-1 text-2xl font-semibold">Continue with email</h1>
          <p className="mt-1 text-sm text-[color:var(--ink-400)]">No password needed. Start free in seconds.</p>

          <div className="mt-6 space-y-2">
            <label htmlFor="email" className="text-xs text-[color:var(--ink-400)]">Email</label>
            <Input
              id="email"
              type="email"
              data-testid={LOGIN.email}
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 bg-[rgba(255,255,255,0.03)] border-[color:var(--border-700)] focus-visible:ring-[color:var(--focus-ring)]"
            />
          </div>
          <Button
            type="submit"
            disabled={loading}
            data-testid={LOGIN.submit}
            className="mt-4 w-full h-11 bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowRight className="w-4 h-4" />} Continue
          </Button>
          <div
            data-testid={LOGIN.disclaimer}
            className="mt-4 text-[11px] font-mono text-[color:var(--ink-600)] leading-relaxed"
          >
            OverHaust remembers the important information so your AI uses fewer tokens. Your knowledge stays in this
            workspace and locally in your browser. Savings shown are estimates.
          </div>
        </form>
      </div>
    </div>
  );
}
