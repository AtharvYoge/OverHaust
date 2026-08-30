export type AppView = "home" | "projects" | "chat" | "settings";

export interface NavItemConfig {
  id: AppView;
  label: string;
}

export const MAIN_NAV: NavItemConfig[] = [
  { id: "home", label: "Home" },
  { id: "projects", label: "Projects" },
  { id: "chat", label: "Chat" },
];

export const SETTINGS_NAV: NavItemConfig = {
  id: "settings",
  label: "Settings",
};
