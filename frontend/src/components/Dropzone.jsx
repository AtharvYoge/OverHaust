import React, { useCallback, useRef, useState } from 'react';
import { UploadCloud, FileText, X } from 'lucide-react';
import { PROJECT } from '@/constants/testIds';

const ALLOWED = ['.txt', '.md', '.json', '.js', '.jsx', '.ts', '.tsx', '.dart', '.py', '.yaml', '.yml', '.xml'];

export default function Dropzone({ onFiles }) {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = useCallback(
    async (fileList) => {
      const files = Array.from(fileList || []);
      const items = [];
      for (const f of files) {
        const isAllowed = ALLOWED.some((ext) => f.name.toLowerCase().endsWith(ext));
        if (!isAllowed && f.type && !f.type.startsWith('text/')) {
          // Silently skip binary
          continue;
        }
        // eslint-disable-next-line no-await-in-loop
        const text = await f.text();
        items.push({ name: f.name, content: text });
      }
      if (items.length && onFiles) onFiles(items);
    },
    [onFiles],
  );

  return (
    <div
      data-testid={PROJECT.ingestionDropzone}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); handleFiles(e.dataTransfer.files); }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-[14px] border-2 border-dashed p-6 text-center transition-colors ${
        drag
          ? 'border-[color:var(--teal-400)] bg-[rgba(32,178,170,0.06)]'
          : 'border-[color:var(--border-700)] hover:border-[color:var(--border-650)] bg-[color:var(--bg-900)]/40'
      }`}
      role="button"
      tabIndex={0}
      aria-label="Drop files or click to browse"
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        accept={ALLOWED.join(',')}
        onChange={(e) => handleFiles(e.target.files)}
      />
      <div className="flex flex-col items-center gap-2 text-[color:var(--ink-300)]">
        <UploadCloud className="w-6 h-6 text-[color:var(--teal-300)]" />
        <div className="text-sm">Drop files here or <span className="text-[color:var(--teal-300)]">browse</span></div>
        <div className="text-[11px] font-mono text-[color:var(--ink-600)]">.txt · .md · .json · .js · .ts · .dart · .py · .yaml · .xml</div>
      </div>
    </div>
  );
}
