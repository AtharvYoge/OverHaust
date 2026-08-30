import type { InputHTMLAttributes } from "react";
import "./ui.css";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
}

export function Input({ label, hint, className = "", id, ...props }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <label className="ui-field" htmlFor={inputId}>
      {label ? <span className="ui-field__label">{label}</span> : null}
      <input id={inputId} className={`ui-input ${className}`.trim()} {...props} />
      {hint ? <span className="ui-field__hint">{hint}</span> : null}
    </label>
  );
}
