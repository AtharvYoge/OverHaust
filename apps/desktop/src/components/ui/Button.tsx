import type { ButtonHTMLAttributes, ReactNode } from "react";
import "./ui.css";

type ButtonVariant = "primary" | "secondary" | "ghost" | "subtle";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
  iconPosition?: "left" | "right";
}

export function Button({
  variant = "primary",
  size = "md",
  icon,
  iconPosition = "left",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`ui-btn ui-btn--${variant} ui-btn--${size} ${className}`.trim()}
      {...props}
    >
      {icon && iconPosition === "left" ? <span className="ui-btn__icon">{icon}</span> : null}
      {children ? <span className="ui-btn__label">{children}</span> : null}
      {icon && iconPosition === "right" ? <span className="ui-btn__icon">{icon}</span> : null}
    </button>
  );
}
