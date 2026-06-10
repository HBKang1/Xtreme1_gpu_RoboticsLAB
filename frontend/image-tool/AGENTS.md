<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# image-tool

## Purpose
2D image annotation tool of the Xtreme1 platform (package name `image-label-opt`), built with Vue 3 + TypeScript + Vite. Annotation shapes (bounding boxes, polygons, polylines, etc.) are rendered on an HTML canvas via **Konva** (^9.2.3), with geometry helpers from `polygon-clipping` and `point-in-polygon`; `three` ^0.142.0 is also a dependency. The codebase is split into a reusable canvas editor engine (`src/package/image-editor`), editor UI components (`src/package/image-ui`), and the platform-specific business layer (`src/businessNew`).

## Key Files
| File | Description |
|------|-------------|
| `src/main.ts` | Entry: calls `init(App)` from `base.ts` |
| `src/base.ts` | App bootstrap: creates Vue app, registers VueClipboard + Ant Design Vue (dark theme), optional router |
| `src/App.vue` | Root component |
| `src/router.ts` | Vue Router setup (router use is currently commented out in `main.ts`) |
| `src/businessNew/Editor.vue` | Business editor root component |
| `src/businessNew/registry.ts` | Business-layer registration |
| `src/businessNew/state.ts` / `context.ts` | Business state and provide/inject context |
| `src/package/image-editor/Editor.ts` | Core canvas editor class |
| `src/package/image-editor/index.ts` | Engine entry, imported via the `image-editor` alias |
| `vite.config.ts` | Dev config; aliases `/@` and `@` → `src/`, `image-editor` → `src/package/image-editor`, `image-ui` → `src/package/image-ui`; set `/api` proxy here |
| `vite.config.build.ts` | Production build: `base: '/tool/image/'`, `outDir: '../dist/image-tool'` |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/businessNew/` | Platform integration layer: `actions`, `api` (backend clients), `common` (`DataManager.ts`, `Editor.ts`, `LoadManager.ts`), `components`, `configs`, `hook`, `pages`, `types`, `utils` |
| `src/package/image-editor/` | Framework-agnostic canvas engine: `Editor.ts`, `ImageView/` (Konva rendering), `common/`, `configs/`, `lib/`, `types/`, `utils/`, `state.ts` |
| `src/package/image-ui/` | Editor UI layer: `components/`, `hook/`, `context.ts`, `vueEvent.ts` |
| `src/enum/` | Shared enums |
| `src/locales/` | i18n resources |
| `src/assets/`, `src/style/` | Static assets and Less styles |

## For AI Agents
### Working In This Directory
- `image-editor` and `image-ui` are vite aliases into `src/package/*` (see `vite.config.ts`), not npm packages.
- Keep concerns separated: rendering/shape logic belongs in `src/package/image-editor`, UI in `src/package/image-ui`, and Xtreme1 API/flow logic in `src/businessNew`.
- Note this app's structure differs from pc-tool/text-tool (`businessNew` + `package/` instead of `common` + `packages/`); do not copy patterns across tools blindly.

### Testing Requirements
- No test scripts exist. Verify with:
  - `npm run dev` — vite dev server (the main app links to it at `http://localhost:3300/tool/image` in dev)
  - `npm run build` — production build into `../dist/image-tool`
  - `npm run preview` — preview the build
  - `npm run lint:eslint` — eslint with `--max-warnings 0` over `{src,mock}/**/*.{vue,ts,tsx}`
- Set the `/api` dev proxy target in `vite.config.ts` before `npm run dev`.

### Common Patterns
- Business managers in `src/businessNew/common/` (`DataManager`, `LoadManager`) wrap the core `image-editor` Editor for platform data flow.
- Events via `eventemitter3`; hotkeys via `hotkeys-js`.
- Path aliases `@/` or `/@/` for `src/` imports.

## Dependencies
### Internal
- Launched from `frontend/main` (the platform UI) at path `/tool/image` — see `frontend/main/src/utils/business/index.ts` (dev: `http://localhost:3300/tool/image`).
- Built by `frontend/Dockerfile` into `dist/image-tool` and served by nginx alongside the other tools.

### External
- `konva` ^9.2.3 (canvas rendering), `vue` ^3.2.25, `ant-design-vue` 3.2.19, `three` ^0.142.0, `polygon-clipping` ^0.15.3, `point-in-polygon` ^1.1.0, `eventemitter3`, `hotkeys-js`, `@tweenjs/tween.js`, `interactjs`, `axios` ^0.26, `vue-i18n` ^9, `vue-router` ^4, `lodash`, `colord`. Build: `vite` ^2.9, `typescript` ^4.5.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
