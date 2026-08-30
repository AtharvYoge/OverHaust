import type { HTMLAttributes } from "react";
import "./ui.css";

type BadgeVariant = "default" | "accent" | "muted";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ variant = "default", className = "", children, ...props }: BadgeProps) {
  return (
    <span className={`ui-badge ui-badge--${variant} ${className}`.trim()} {...props}>
      {children}
    </span>
  );
}
