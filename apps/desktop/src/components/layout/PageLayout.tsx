import type { ReactNode } from "react";
import type { AppView } from "../../types/navigation";
import "./layout.css";

interface NavItemProps {
  label: string;
  icon: ReactNode;
  active: boolean;
  onClick: () => void;
}

export function NavItem({ label, icon, active, onClick }: NavItemProps) {
  return (
    <button
      type="button"
      className={`nav-item${active ? " nav-item--active" : ""}`}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
    >
      <span className="nav-item__icon">{icon}</span>
      <span>{label}</span>
    </button>
  );
}

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header__content">
        <h1 className="page-header__title">{title}</h1>
        {description ? <p className="page-header__description">{description}</p> : null}
      </div>
      {action}
    </header>
  );
}

interface PageContentProps {
  children: ReactNode;
  narrow?: boolean;
  wide?: boolean;
}

export function PageContent({ children, narrow, wide }: PageContentProps) {
  const className = [
    "page-content",
    narrow ? "page-content--narrow" : "",
    wide ? "page-content--wide" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return <div className={className}>{children}</div>;
}

export function viewTitle(view: AppView): string {
  switch (view) {
    case "home":
      return "Home";
    case "projects":
      return "Projects";
    case "chat":
      return "Chat";
    case "settings":
      return "Settings";
  }
}
