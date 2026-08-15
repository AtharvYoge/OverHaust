{
  "brand": {
    "product_name": "OverHaust",
    "tagline": "Less context. More intelligence.",
    "positioning": "Serious developer infrastructure for AI coding agents: a Context Runtime that builds a persistent Context Cache and returns only relevant context per task.",
    "tone": {
      "attributes": [
        "precise",
        "skeptical",
        "engineering-first",
        "quietly premium",
        "prototype-honest"
      ],
      "language_rules": {
        "use": [
          "Context Runtime",
          "Context Cache",
          "Project Knowledge",
          "Persistent Context",
          "Relevant Context",
          "Context Reduction"
        ],
        "avoid": [
          "Prompt Optimizer",
          "AI Assistant",
          "chat",
          "conversation with the AI"
        ],
        "claims": "Use 'prototype / estimated' phrasing for metrics and savings. Never overclaim accuracy."
      }
    },
    "aesthetic_references": [
      "Linear",
      "Vercel",
      "Raycast",
      "Stripe",
      "Supabase",
      "Cursor"
    ]
  },

  "design_tokens": {
    "theme": {
      "default": "dark",
      "implementation_note": "App must default to dark. Add `class=\"dark\"` on the root html/body wrapper at boot. Light theme optional; do not spend design budget on it."
    },

    "color": {
      "notes": [
        "Dark-first, layered surfaces (bg → surface-1 → surface-2) with low-contrast borders.",
        "Single chromatic accent (teal) + mint for success. Avoid purple.",
        "Numbers/metrics are hero elements: ensure high contrast and tabular numerals."
      ],

      "primitives": {
        "ink_0": "#FFFFFF",
        "ink_50": "#E9EEF5",
        "ink_200": "#C9D3E1",
        "ink_400": "#A8B3C2",
        "ink_600": "#7C8797",
        "ink_800": "#3A4350",

        "bg_950": "#0B0D10",
        "bg_900": "#0F1318",
        "surface_850": "#151A21",
        "surface_800": "#1C2330",
        "surface_750": "#222B3A",
        "border_700": "#273140",
        "border_650": "#2E3A4C",

        "teal_500": "#20B2AA",
        "teal_400": "#35C7BF",
        "teal_300": "#6FE3DD",
        "mint_500": "#5DE2B4",
        "mint_400": "#7AF0C7",

        "amber_500": "#F6C177",
        "red_500": "#FF6B6B",
        "blue_500": "#6AA9FF"
      },

      "semantic": {
        "background": "var(--bg-950)",
        "foreground": "var(--ink-50)",
        "muted_foreground": "var(--ink-400)",

        "card": "var(--surface-850)",
        "card_raised": "var(--surface-800)",
        "popover": "var(--surface-800)",

        "border": "var(--border-700)",
        "border_strong": "var(--border-650)",

        "primary": "var(--teal-500)",
        "primary_foreground": "#071012",

        "secondary": "var(--surface-800)",
        "secondary_foreground": "var(--ink-50)",

        "accent": "var(--teal-400)",
        "accent_soft_bg": "rgba(32,178,170,0.10)",

        "success": "var(--mint-500)",
        "warning": "var(--amber-500)",
        "danger": "var(--red-500)",

        "focus_ring": "rgba(53,199,191,0.55)",
        "selection_bg": "rgba(32,178,170,0.18)"
      },

      "gradients_and_texture": {
        "rules": {
          "max_viewport_coverage": "<= 20%",
          "allowed_usage": [
            "hero background only",
            "section background accents",
            "large decorative overlays",
            "very large CTA background (rare)"
          ],
          "prohibited": [
            "purple/pink gradients",
            "gradients on text-heavy reading areas",
            "gradients on small UI elements (<100px)",
            "stacking multiple gradients in same viewport"
          ]
        },
        "approved_gradients": {
          "hero_subtle": "radial-gradient(900px circle at 20% 10%, rgba(32,178,170,0.18), transparent 55%), radial-gradient(700px circle at 80% 20%, rgba(93,226,180,0.10), transparent 60%)",
          "panel_glow": "radial-gradient(600px circle at 100% 0%, rgba(53,199,191,0.14), transparent 55%)",
          "divider_sheen": "linear-gradient(90deg, transparent, rgba(233,238,245,0.10), transparent)"
        },
        "noise_overlay_css": "background-image: url('data:image/svg+xml,%3Csvg xmlns=\"http://www.w3.org/2000/svg\" width=\"160\" height=\"160\"%3E%3Cfilter id=\"n\"%3E%3CfeTurbulence type=\"fractalNoise\" baseFrequency=\"0.8\" numOctaves=\"3\" stitchTiles=\"stitch\"/%3E%3C/filter%3E%3Crect width=\"160\" height=\"160\" filter=\"url(%23n)\" opacity=\"0.08\"/%3E%3C/svg%3E'); mix-blend-mode: overlay;"
      }
    },

    "typography": {
      "font_pairing": {
        "ui": "Space Grotesk (Google Fonts)",
        "mono": "IBM Plex Mono (Google Fonts)",
        "fallbacks": "system-ui, -apple-system, Segoe UI, Roboto"
      },
      "css_notes": [
        "Use tabular numerals for metrics: `font-variant-numeric: tabular-nums;`",
        "Use mono for tokens, code blocks, and numeric-heavy KPI values.",
        "Avoid oversized marketing typography; keep it technical and dense like Linear/Vercel."
      ],
      "scale_tailwind": {
        "h1": "text-4xl sm:text-5xl lg:text-6xl",
        "h2": "text-base md:text-lg",
        "body": "text-sm md:text-base",
        "small": "text-xs"
      },
      "weights": {
        "regular": 400,
        "medium": 500,
        "semibold": 600
      },
      "tracking": {
        "headings": "tracking-[-0.02em]",
        "mono": "tracking-[-0.01em]"
      }
    },

    "spacing": {
      "principles": [
        "Use 2–3x more spacing than feels comfortable.",
        "Prefer consistent vertical rhythm: section padding and card padding are predictable."
      ],
      "scale": {
        "page_x": "px-4 sm:px-6 lg:px-8",
        "page_y": "py-6 sm:py-8",
        "section_y": "py-14 sm:py-18",
        "card": "p-4 sm:p-5",
        "card_dense": "p-3 sm:p-4",
        "gap": "gap-4 sm:gap-6",
        "sidebar_width": "w-[260px]",
        "topbar_height": "h-14"
      }
    },

    "radius": {
      "system": {
        "sm": "6px",
        "md": "10px",
        "lg": "14px"
      },
      "usage": {
        "buttons": "10px",
        "cards": "14px",
        "inputs": "10px",
        "chips": "999px (pill)"
      }
    },

    "elevation": {
      "rules": [
        "In dark UI, prefer borders + subtle highlights over heavy shadows.",
        "Use 1px borders with low contrast; add a faint inner highlight for premium feel."
      ],
      "shadows": {
        "card": "0 1px 0 rgba(255,255,255,0.04), 0 12px 30px rgba(0,0,0,0.35)",
        "popover": "0 1px 0 rgba(255,255,255,0.05), 0 18px 50px rgba(0,0,0,0.55)"
      },
      "borders": {
        "card": "border border-[color:var(--border)]",
        "card_hover": "hover:border-[color:var(--border-strong)]"
      }
    },

    "motion": {
      "personality": "Restrained, infrastructure-grade. No playful bounces. Prefer subtle fades, 1–2px shifts, and progress-driven motion.",
      "durations_ms": {
        "fast": 120,
        "base": 180,
        "slow": 260
      },
      "easing": {
        "standard": "cubic-bezier(0.2, 0.8, 0.2, 1)",
        "out": "cubic-bezier(0.16, 1, 0.3, 1)"
      },
      "framer_motion_guidelines": {
        "page_enter": "opacity 0→1 + y 6→0 over 180ms",
        "card_hover": "y 0→-1 over 120ms",
        "pipeline_step": "progress bar width + subtle glow pulse on active step",
        "reduced_motion": "Respect prefers-reduced-motion: disable transforms and pulses."
      }
    }
  },

  "data_visualization": {
    "library": "recharts",
    "chart_style": {
      "grid": "stroke rgba(233,238,245,0.08)",
      "axis": "stroke rgba(233,238,245,0.18)",
      "tick": "fill rgba(233,238,245,0.65)",
      "tooltip": {
        "container": "bg-[color:var(--surface-800)] border border-[color:var(--border)] rounded-[14px] shadow-[var(--shadow-popover)]",
        "label": "text-xs text-[color:var(--muted-foreground)]",
        "value": "font-mono text-sm text-[color:var(--foreground)]"
      },
      "series_colors": {
        "before": "rgba(233,238,245,0.35)",
        "after": "#20B2AA",
        "reduction": "#5DE2B4",
        "secondary": "#6AA9FF",
        "danger": "#FF6B6B"
      },
      "interaction": {
        "hover": "increase strokeWidth by 1; show dot with outer glow rgba(32,178,170,0.35)",
        "selection": "dim non-selected series to 0.35 opacity"
      }
    },
    "empty_states": {
      "principles": [
        "Never show blank charts; show a skeleton + a short explanation.",
        "Use 'prototype' tone: 'No analytics yet — run your first cache build.'"
      ],
      "components": [
        "Skeleton",
        "Alert"
      ]
    }
  },

  "component_path": {
    "shadcn_primary": {
      "layout": [
        "/app/frontend/src/components/ui/resizable.jsx",
        "/app/frontend/src/components/ui/scroll-area.jsx",
        "/app/frontend/src/components/ui/separator.jsx",
        "/app/frontend/src/components/ui/sheet.jsx",
        "/app/frontend/src/components/ui/drawer.jsx"
      ],
      "navigation": [
        "/app/frontend/src/components/ui/navigation-menu.jsx",
        "/app/frontend/src/components/ui/breadcrumb.jsx",
        "/app/frontend/src/components/ui/command.jsx",
        "/app/frontend/src/components/ui/dropdown-menu.jsx",
        "/app/frontend/src/components/ui/tooltip.jsx"
      ],
      "forms": [
        "/app/frontend/src/components/ui/form.jsx",
        "/app/frontend/src/components/ui/input.jsx",
        "/app/frontend/src/components/ui/textarea.jsx",
        "/app/frontend/src/components/ui/label.jsx",
        "/app/frontend/src/components/ui/select.jsx",
        "/app/frontend/src/components/ui/checkbox.jsx",
        "/app/frontend/src/components/ui/radio-group.jsx",
        "/app/frontend/src/components/ui/switch.jsx"
      ],
      "content": [
        "/app/frontend/src/components/ui/card.jsx",
        "/app/frontend/src/components/ui/badge.jsx",
        "/app/frontend/src/components/ui/tabs.jsx",
        "/app/frontend/src/components/ui/table.jsx",
        "/app/frontend/src/components/ui/progress.jsx",
        "/app/frontend/src/components/ui/skeleton.jsx",
        "/app/frontend/src/components/ui/collapsible.jsx",
        "/app/frontend/src/components/ui/accordion.jsx"
      ],
      "overlays": [
        "/app/frontend/src/components/ui/dialog.jsx",
        "/app/frontend/src/components/ui/alert-dialog.jsx",
        "/app/frontend/src/components/ui/popover.jsx",
        "/app/frontend/src/components/ui/hover-card.jsx"
      ],
      "feedback": [
        "/app/frontend/src/components/ui/sonner.jsx",
        "/app/frontend/src/components/ui/toaster.jsx"
      ]
    },
    "recommended_new_components_js": {
      "paths": [
        "/app/frontend/src/components/AppShell.jsx",
        "/app/frontend/src/components/SidebarNav.jsx",
        "/app/frontend/src/components/Topbar.jsx",
        "/app/frontend/src/components/KpiCard.jsx",
        "/app/frontend/src/components/FlowDiagram.jsx",
        "/app/frontend/src/components/PipelineOverlay.jsx",
        "/app/frontend/src/components/ContextCachePanels.jsx",
        "/app/frontend/src/components/TokenComparisonTable.jsx",
        "/app/frontend/src/components/CodeBlock.jsx",
        "/app/frontend/src/components/StatusPill.jsx",
        "/app/frontend/src/components/Dropzone.jsx"
      ],
      "note": "Project uses .js (not .tsx). Keep components in JS, use PropTypes only if needed."
    }
  },

  "layout_and_grids": {
    "global": {
      "app_shell": {
        "structure": "Left sidebar + topbar + scrollable main content",
        "sidebar": {
          "width": "260px",
          "behavior": "Fixed on desktop; Drawer/Sheet on mobile",
          "sections": [
            "Workspace/Project switcher",
            "Primary nav",
            "Secondary links (Integrations, Settings)",
            "Status footer (Local Cache)"
          ]
        },
        "topbar": {
          "height": "56px",
          "contents": [
            "Breadcrumb",
            "Global search / Command palette",
            "Quick actions (New Project, Build Cache)",
            "User menu"
          ]
        },
        "content_width": "max-w-[1200px] for marketing sections; app pages can be max-w-[1400px]",
        "grid": "Use 12-col grid on desktop; 4-col on mobile; 8-col on tablet"
      }
    },

    "page_recommendations": {
      "landing": {
        "pattern": "Z-pattern hero + technical diagram + feature strip + how-it-works steps",
        "hero": {
          "left": "Headline + subhead + 2 CTAs",
          "right": "FlowDiagram component (token reduction pipeline)",
          "cta": [
            "Request demo (email capture)",
            "Open prototype (go to /login)"
          ]
        },
        "diagram": {
          "copy": "500,000 tokens → Context Runtime → 8,000 tokens → AI Agent",
          "visual": "Use mono numerals, arrows, and a central 'Context Runtime' capsule with subtle teal glow."
        }
      },

      "login": {
        "pattern": "Centered card but left-aligned text inside; minimal fields",
        "elements": [
          "Email input",
          "Continue button",
          "Prototype disclaimer"
        ]
      },

      "dashboard_overview": {
        "top": "4 KPI cards in a responsive grid",
        "middle": "Recent Projects table (dense)",
        "right_optional": "Local Cache status card (or place in sidebar footer)"
      },

      "projects_list": {
        "pattern": "Header with filters + table/list; New Project button",
        "cards_or_table": "Prefer table for density; cards only on mobile"
      },

      "project_create_wizard": {
        "pattern": "2-step or 3-step wizard in a Dialog or dedicated page",
        "fields": [
          "Project name",
          "Description",
          "Tech stack chips (Badge + ToggleGroup)"
        ]
      },

      "project_detail": {
        "layout": "Two-column on desktop: left = ingestion/build/task; right = cache viewer panels",
        "tabs": [
          "Conversation",
          "Documentation",
          "Project Files",
          "Notes"
        ],
        "sections": [
          "Ingestion tabs with paste + Dropzone",
          "Build Context Cache button",
          "Compression visualization (before/after + reduction %)",
          "Task Context Generator",
          "Context Comparison table",
          "Context Cache viewer panels"
        ]
      },

      "pipeline_overlay": {
        "pattern": "Full-screen Dialog overlay with 8 sequential steps",
        "steps": [
          "Normalize inputs",
          "Deduplicate",
          "Extract entities",
          "Infer architecture",
          "Summarize components",
          "Derive decisions",
          "Build memory buckets",
          "Write Context Cache"
        ],
        "ui": "Left stepper list + right detail panel + progress bar + log lines (mono)."
      },

      "analytics": {
        "charts": [
          "Before vs After context size (bar)",
          "Reduction % over time (line)",
          "Most-used knowledge items (horizontal bar)",
          "Tasks/cache-updates counters"
        ],
        "layout": "Bento grid: 2 charts top, 1 wide chart, then table of events"
      },

      "integrations": {
        "pattern": "Card grid with Coming Soon badges + MCP tools list + install command",
        "mcp": {
          "install": "npx context-runtime-mcp",
          "tools": [
            "get_project_context",
            "get_relevant_context",
            "search_project_knowledge",
            "get_memory",
            "update_memory"
          ]
        }
      },

      "settings": {
        "pattern": "Simple sections: profile, local cache, preferences",
        "note": "Keep settings sparse; this is a prototype."
      }
    }
  },

  "component_specs": {
    "buttons": {
      "style": "Professional / Corporate with slight premium rounding",
      "tokens": {
        "radius": "10px",
        "height": "h-10 (md), h-9 (sm), h-11 (lg)",
        "focus": "ring-2 ring-[color:var(--focus-ring)] ring-offset-0"
      },
      "variants": {
        "primary": "bg-[color:var(--primary)] text-[color:var(--primary-foreground)] hover:bg-[color:var(--teal-400)]",
        "secondary": "bg-[color:var(--secondary)] text-[color:var(--foreground)] border border-[color:var(--border)] hover:border-[color:var(--border-strong)]",
        "ghost": "bg-transparent hover:bg-[rgba(233,238,245,0.06)]"
      },
      "micro_interactions": [
        "Hover: translateY(-1px) on desktop only",
        "Active: scale(0.98)",
        "Loading: inline spinner + keep width stable"
      ]
    },

    "inputs": {
      "style": "Dark inset fields with clear focus ring",
      "classes": "bg-[rgba(255,255,255,0.03)] border border-[color:var(--border)] focus-visible:ring-2 focus-visible:ring-[color:var(--focus-ring)]",
      "states": {
        "error": "border-[color:var(--danger)] focus-visible:ring-[rgba(255,107,107,0.35)]",
        "disabled": "opacity-60 cursor-not-allowed"
      }
    },

    "cards": {
      "base": "rounded-[14px] bg-[color:var(--card)] border border-[color:var(--border)] shadow-[var(--shadow-card)]",
      "hover": "hover:border-[color:var(--border-strong)]",
      "header": "text-xs uppercase tracking-[0.12em] text-[color:var(--muted-foreground)]",
      "kpi_value": "font-mono text-2xl sm:text-3xl tracking-[-0.02em] [font-variant-numeric:tabular-nums]"
    },

    "badges_and_chips": {
      "tech_stack_chip": "Badge variant=secondary + rounded-full + border; selected state uses accent_soft_bg",
      "status_pill": {
        "active": "bg-[rgba(93,226,180,0.12)] text-[color:var(--mint-400)] border border-[rgba(93,226,180,0.25)]",
        "inactive": "bg-[rgba(233,238,245,0.06)] text-[color:var(--muted-foreground)] border border-[color:var(--border)]",
        "warning": "bg-[rgba(246,193,119,0.12)] text-[color:var(--amber-500)] border border-[rgba(246,193,119,0.25)]"
      }
    },

    "tables": {
      "density": "Compact like developer tools; row height ~44px",
      "header": "text-xs text-[color:var(--muted-foreground)]",
      "cells": "font-mono for numeric columns; truncate long strings",
      "interaction": "row hover background rgba(233,238,245,0.04)"
    },

    "code_block": {
      "use": "Optimized AI Context output + install commands",
      "style": "bg-[rgba(0,0,0,0.35)] border border-[color:var(--border)] rounded-[14px] p-4 font-mono text-sm leading-6",
      "features": [
        "Copy button top-right",
        "Line wrap toggle (optional)",
        "Syntax highlight optional; keep minimal"
      ]
    },

    "flow_diagram": {
      "landing_hero": {
        "layout": "Four nodes in a row with arrows; center node emphasized",
        "nodes": {
          "token_before": "500,000 tokens",
          "runtime": "Context Runtime",
          "token_after": "8,000 tokens",
          "agent": "AI Agent"
        },
        "style": "Mono numerals, subtle teal glow on runtime node, arrows as thin strokes."
      }
    },

    "pipeline_overlay": {
      "structure": "Dialog full-screen; left stepper + right details",
      "progress": "Use Progress component + step completion checkmarks",
      "log": "ScrollArea with mono lines; newest lines fade in"
    }
  },

  "screen_specific_testing_ids": {
    "rules": [
      "All interactive and key informational elements MUST include data-testid.",
      "Use kebab-case describing role, not appearance."
    ],
    "examples": {
      "landing": [
        "landing-hero-primary-cta-button",
        "landing-hero-secondary-cta-button",
        "landing-flow-diagram"
      ],
      "login": [
        "login-email-input",
        "login-submit-button",
        "login-prototype-disclaimer"
      ],
      "app_shell": [
        "sidebar-nav-overview-link",
        "sidebar-nav-projects-link",
        "topbar-command-palette-button",
        "topbar-new-project-button"
      ],
      "projects": [
        "projects-create-button",
        "projects-table",
        "project-create-name-input",
        "project-create-tech-stack-chip-react"
      ],
      "project_detail": [
        "ingestion-tabs",
        "ingestion-conversation-textarea",
        "ingestion-files-dropzone",
        "build-cache-button",
        "compression-reduction-metric",
        "task-generator-input",
        "task-generator-submit-button",
        "optimized-context-codeblock",
        "optimized-context-copy-button",
        "context-comparison-table"
      ],
      "analytics": [
        "analytics-before-after-bar-chart",
        "analytics-reduction-line-chart",
        "analytics-most-used-items-bar-chart"
      ],
      "integrations": [
        "integrations-cursor-card",
        "integrations-mcp-install-codeblock",
        "integrations-mcp-tools-list"
      ],
      "settings": [
        "settings-local-cache-refresh-button",
        "settings-local-cache-status"
      ]
    }
  },

  "image_urls": {
    "notes": "Avoid stock photos of people. Prefer abstract/noise gradients and product diagrams. Use images sparingly in dark UI.",
    "backgrounds": [
      {
        "category": "landing-hero-background",
        "description": "Subtle teal/blue abstract background used behind hero (apply with low opacity + blur).",
        "url": "https://images.unsplash.com/photo-1708305729900-906f34a7d49d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzNzl8MHwxfHNlYXJjaHwzfHxkYXJrJTIwYWJzdHJhY3QlMjBzdWJ0bGUlMjBncmFkaWVudCUyMG5vaXNlJTIwYmFja2dyb3VuZCUyMHRlYWx8ZW58MHx8fHRlYWx8MTc4Njc3Mzc1N3ww&ixlib=rb-4.1.0&q=85"
      },
      {
        "category": "section-accent-background",
        "description": "Horizontal-line teal texture for subtle section separators (use as masked overlay).",
        "url": "https://images.unsplash.com/photo-1563518839049-f44a5e423f12?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzNzl8MHwxfHNlYXJjaHwyfHxkYXJrJTIwYWJzdHJhY3QlMjBzdWJ0bGUlMjBncmFkaWVudCUyMG5vaXNlJTIwYmFja2dyb3VuZCUyMHRlYWx8ZW58MHx8fHRlYWx8MTc4Njc3Mzc1N3ww&ixlib=rb-4.1.0&q=85"
      }
    ]
  },

  "instructions_to_main_agent": {
    "global_css_changes": [
      "Remove any centered App header styles from App.css usage; do not center the entire app container.",
      "In index.css, replace shadcn default tokens with the semantic palette above (dark-first).",
      "Add global utilities: tabular numerals, selection color, subtle noise overlay class, and code block styling.",
      "Ensure root has `className=\"dark\"` by default."
    ],
    "implementation_priorities": [
      "Build AppShell (sidebar + topbar) first; everything else plugs into it.",
      "Implement KPI cards + tables + charts with consistent tokens.",
      "Implement Project Detail page as the flagship: ingestion → pipeline overlay → cache viewer → task generator → comparison.",
      "Keep animations restrained; focus on progress feedback and hover polish."
    ],
    "libraries": {
      "required": [
        "recharts",
        "framer-motion",
        "idb (or native IndexedDB wrapper)"
      ],
      "install": "npm i recharts framer-motion idb",
      "notes": "Use sonner for toasts (already present)."
    },
    "accessibility": [
      "All focusable elements must have visible focus ring.",
      "Charts must have text alternatives (summary below chart).",
      "Do not rely on color alone for status; pair with icon + label."
    ],
    "testing": {
      "data_testid": "Add data-testid to all interactive and key informational elements (buttons, inputs, nav links, KPI values, charts containers, error messages)."
    }
  },

  "general_ui_ux_design_guidelines_appendix": "<General UI UX Design Guidelines>  \n    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n</General UI UX Design Guidelines>"
}
