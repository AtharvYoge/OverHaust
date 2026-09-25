# OverHaust Integration Manager

> "Users choose OverHaust. OverHaust chooses how to connect to their AI environment."

The Integration Manager is a thin onboarding layer above the host adapter
registry. It gives users one CLI and never touches host configuration itself.

```
overhaust doctor          integration diagnostics
overhaust status          core health + registered projects + connected hosts
overhaust integrations    every registered adapter and its lifecycle state
overhaust connect         install OverHaust into detected hosts
overhaust disconnect      remove OverHaust-owned host configuration
```

Run via `scripts/overhaust <command>` (or `python3 scripts/overhaust_cli.py`).
Add `--json` for machine-readable output, `--host <adapter-id>` to scope,
`--probe-emission` to run local hook probes.

## Architecture

```
CLI / future GUI                 scripts/overhaust_cli.py
      ↓
Integration Manager              packages/integrations/manager.py
      ↓
Adapter Registry                 packages/integrations/adapters/registry.py
      ↓
Host Adapter                     packages/integrations/adapters/{cursor,codex,claude,continue_host,cline_host}.py
      ↓
Native host mechanism            hooks.json / settings.json / mcp.json / .continue / .clinerules
      ↓
invoke_context_request()         packages/context (unchanged)
      ↓
Context Engine
```

Rules the manager obeys:

- It only calls the adapter protocol: `detect / capabilities / install / verify / uninstall`
  plus the optional `probe_emission`.
- It never branches on product names for behaviour (enforced by
  `test_manager_has_no_product_if_elif_chain`).
- One adapter raising is recorded as `UNKNOWN` with the error; the loop continues.
- Idempotency and preservation of unrelated user config are adapter/install
  responsibilities (merge, never overwrite). The manager just decides *which*
  adapters run.

## Lifecycle states (`IntegrationState`)

| State               | Meaning                                                          |
|---------------------|------------------------------------------------------------------|
| `NOT_DETECTED`      | Adapter registered, host not found on this machine               |
| `DETECTED`          | Host found, no OverHaust configuration                           |
| `CONFIGURED`        | OverHaust config present, readiness not yet established          |
| `TRUST_REQUIRED`    | Config present but host requires user trust (e.g. Codex hooks)   |
| `ACTION_REQUIRED`   | Something the user must do; see `actions`                        |
| `INTEGRATION_READY` | Config + script + trust all look correct                         |
| `CONTEXT_EMITTING`  | Local probe proved the hook emits OverHaust context (`--probe-emission`) |
| `CONTEXT_VERIFIED`  | Live model consumption confirmed by an explicit external source  |
| `NOT_SUPPORTED`     | Adapter says this host/runtime cannot be integrated              |
| `UNKNOWN`           | Adapter detect/verify raised; error is reported                  |

`INTEGRATION_READY` is deliberately **not** the top state: Codex Desktop and
Cline both taught us configuration success ≠ model consumption. Nothing in
this repo sets `CONTEXT_VERIFIED` by default; the manager accepts a
`consumption_verified(adapter_id) -> bool` callable for a future verified-run
store, and reports `unverified` otherwise. `CONTEXT_EMITTING` is only reachable
for adapters exposing `probe_emission()` (Codex, Claude, Cline); MCP-based
hosts (Cursor, Continue) report `emission=n/a` because the host pulls context.

## Future distribution boundary

The manager exposes plain dataclasses (`HostRecord`, `ConnectOutcome`,
`DisconnectOutcome`, `StatusReport`) with `to_dict()`. Any front end —
terminal installer, IDE extension, MCP marketplace listing, native plugin,
desktop app — drives the same `IntegrationManager` and renders those records.
None of those front ends are implemented here.

## Repository sources are not hosts

```
Repository Sources                Host Adapters
├── local filesystem  (today)     ├── cursor
├── GitHub            (future)    ├── codex
├── GitLab            (future)    ├── claude
└── other             (future)    ├── continue
                                  └── cline
```

A repository is a *project* the context engine indexes; an AI host is a
*consumer* of context. GitHub OAuth/App work belongs to a future
`packages/sources/` boundary feeding project registration/indexing, and must
not be modelled as an `IntegrationAdapter`. Not implemented in this task.

## Explicitly not built

GitHub integration, IDE marketplace plugins, telemetry, auto-reindexing,
additional host adapters, token-savings metrics.
