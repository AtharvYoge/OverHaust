import type { HTMLAttributes, ReactNode } from "react";
import "./ui.css";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padding?: "sm" | "md" | "lg";
  elevated?: boolean;
}

export function Card({
  children,
  padding = "md",
  elevated = false,
  className = "",
  ...props
}: CardProps) {
  return (
    <div
      className={`ui-card ui-card--${padding}${elevated ? " ui-card--elevated" : ""} ${className}`.trim()}
      {...props}
    >
      {children}
    </div>
  );
}

interface CardHeaderProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function CardHeader({ title, description, action }: CardHeaderProps) {
  return (
    <div className="ui-card__header">
      <div>
        <h3 className="ui-card__title">{title}</h3>
        {description ? <p className="ui-card__description">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
