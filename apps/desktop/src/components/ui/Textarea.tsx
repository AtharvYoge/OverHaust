import type { TextareaHTMLAttributes } from "react";
import "./ui.css";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
}

export function Textarea({ label, className = "", id, ...props }: TextareaProps) {
  const textareaId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <label className="ui-field" htmlFor={textareaId}>
      {label ? <span className="ui-field__label">{label}</span> : null}
      <textarea id={textareaId} className={`ui-textarea ${className}`.trim()} {...props} />
    </label>
  );
}
