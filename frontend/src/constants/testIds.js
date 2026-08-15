// Simple constants for e2e/testing (kebab-case, role-based).

export const LANDING = {
  hero: 'landing-hero',
  primaryCta: 'landing-hero-primary-cta-button',
  secondaryCta: 'landing-hero-secondary-cta-button',
  signIn: 'landing-nav-signin-button',
  flow: 'landing-memory-layer-visual',
  painSection: 'landing-pain-points',
  audienceSection: 'landing-audience',
  agentsSection: 'landing-agents',
  pricingSection: 'landing-pricing',
  pricingCtaFree: 'landing-pricing-free-cta',
};

export const LOGIN = {
  email: 'login-email-input',
  submit: 'login-submit-button',
  disclaimer: 'login-prototype-disclaimer',
};

export const NAV = {
  home: 'sidebar-nav-home-link',
  projects: 'sidebar-nav-projects-link',
  memory: 'sidebar-nav-memory-link',
  usage: 'sidebar-nav-usage-link',
  connections: 'sidebar-nav-connections-link',
  settings: 'sidebar-nav-settings-link',
  newProject: 'topbar-new-project-button',
  addKnowledge: 'topbar-add-knowledge-button',
  seedDemo: 'topbar-seed-demo-button',
};

export const HOME = {
  heroCard: 'home-hero-card',
  kpiSaved: 'home-kpi-information-saved',
  kpiReduced: 'home-kpi-usage-reduced',
  kpiProjects: 'home-kpi-projects',
  kpiAgents: 'home-kpi-connected-agents',
};

export const PROJECT = {
  createButton: 'projects-create-button',
  table: 'projects-table',
  createNameInput: 'project-create-name-input',
  createDescInput: 'project-create-description-input',
  createStackInput: 'project-create-stack-input',
  createSubmit: 'project-create-submit',
  ingestionTabs: 'ingestion-tabs',
  ingestionTextarea: 'ingestion-textarea',
  ingestionAdd: 'ingestion-add-button',
  ingestionDropzone: 'ingestion-files-dropzone',
  buildCache: 'build-memory-button',
  compressionMetric: 'usage-reduction-metric',
  simpleToggle: 'project-simple-advanced-toggle',
  taskInput: 'prepare-for-ai-input',
  taskSubmit: 'prepare-for-ai-submit-button',
  optimizedBlock: 'prepared-context-codeblock',
  copyContext: 'copy-for-ai-button',
  comparisonTable: 'context-comparison-table',
};

export const MEMORY = {
  page: 'ai-memory-page',
  categories: 'ai-memory-categories',
  recent: 'ai-memory-recent-updates',
};

export const USAGE = {
  page: 'usage-page',
  viewToggle: 'usage-view-toggle',
  simpleMetric: 'usage-simple-savings-metric',
  creditCard: 'usage-credit-savings-card',
  planAdvisor: 'usage-plan-advisor-card',
  advancedOriginal: 'usage-advanced-original-tokens',
  advancedOptimized: 'usage-advanced-optimized-tokens',
};

export const CONNECTIONS = {
  page: 'connections-page',
  grid: 'connections-agent-grid',
  connectBtn: (key) => `connection-connect-${key}-button`,
  card: (key) => `connection-card-${key}`,
};

export const SETTINGS = {
  refresh: 'settings-local-cache-refresh-button',
  status: 'settings-local-cache-status',
};
