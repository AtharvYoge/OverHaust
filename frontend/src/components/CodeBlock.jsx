import React, { useState } from 'react';
import { Copy, Check, AlignLeft, WrapText } from 'lucide-react';
import { toast } from 'sonner';

export default function CodeBlock({ content, testId, copyTestId, ariaLabel, mono = true }) {
  const [copied, setCopied] = useState(false);
  const [wrap, setWrap] = useState(true);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content || '');
      setCopied(true);
      toast.success('Copied optimized context to clipboard');
      setTimeout(() => setCopied(false), 1200);
    } catch {
      toast.error('Copy failed');
    }
  };

  return (
    <div
      data-testid={testId}
      className="relative rounded-[14px] border border-[color:var(--border-700)] bg-black/40 overflow-hidden"
      aria-label={ariaLabel || 'Code block'}
    >
      <div className="absolute top-2 right-2 flex items-center gap-1 z-10">
        <button
          type="button"
          aria-label="Toggle line wrap"
          onClick={() => setWrap((w) => !w)}
          className="px-2 py-1 text-[11px] rounded-md bg-[color:var(--surface-800)] border border-[color:var(--border-700)] hover:border-[color:var(--border-650)] text-[color:var(--ink-300)]"
        >
          {wrap ? <WrapText className="w-3 h-3" /> : <AlignLeft className="w-3 h-3" />}
        </button>
        <button
          type="button"
          data-testid={copyTestId}
          onClick={handleCopy}
          aria-label="Copy context"
          className="px-2 py-1 text-[11px] rounded-md bg-[color:var(--teal-500)] text-[color:var(--bg-950)] hover:bg-[color:var(--teal-400)] inline-flex items-center gap-1"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy context'}
        </button>
      </div>
      <pre
        className={`${mono ? 'font-mono' : ''} text-[13px] leading-6 text-[color:var(--ink-200)] p-4 pr-24 max-h-[520px] overflow-auto ${
          wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre'
        }`}
      >
        {content && content.length > 0 ? content : 'No context assembled yet.'}
      </pre>
    </div>
  );
}
