# OverHaust Desktop

Tauri 2 + React + TypeScript shell for the OverHaust desktop application.

This app is separate from the demo web UI in `apps/web`. The Python backend is unchanged; future phases will connect to the existing local API.

## Prerequisites

- Node.js 18+
- [Rust toolchain](https://www.rust-lang.org/learn/get-started) (required for `tauri dev` / `tauri build`)
- macOS prerequisites: [Tauri prerequisites](https://tauri.app/start/prerequisites/)

## Development

```bash
cd apps/desktop
npm install
npm run tauri dev
```

Frontend-only (Vite, no native window):

```bash
npm run dev
```

## Build

```bash
npm run build
npm run tauri build
```
