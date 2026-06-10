<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# pc-tool

## Purpose
3D point-cloud annotation tool of the Xtreme1 platform, built with Vue 3 + TypeScript + Vite and rendered with three.js (^0.136.0). It provides 3D cuboid annotation over LiDAR point clouds with synchronized 2D camera views, a frame timeline for sequence data, hotkey-driven actions, and object tracking/copy between frames. This fork (Robotics Lab) adds a **multi-frame copy** feature (commit `7473cb5`): a `copyAllForward` action that copies all annotation objects to the next frame, exposed as a "Copy All to Next Frame" toolbar button and the `Alt+Shift+Right` hotkey, and it enables the TimeLine plus copy-forward/backward actions for plain multi-frame datasets (`state.frames.length > 1`), not only series-frame datasets.

## Key Files
| File | Description |
|------|-------------|
| `src/main.ts` | App entry: creates Vue app, registers Ant Design Vue + Vue3ColorPicker, mounts `App.vue` |
| `src/App.vue` | Root component |
| `src/registry.ts` | Registers hotkeys (`src/config/hotkey` via pc-editor) and all actions from `src/actions` into the editor's hotkeyManager/actionManager |
| `src/state.ts` | Business-level state definitions |
| `src/config/action.ts` | Declares business action names (`generalActions`, `executeActions`) — includes fork-added `copyAllForward` |
| `src/hook/useTool.ts` | Flow setup; fork sets `state.isMultiFrame = !isSeriesFrame && dataInfos.length > 1` |
| `src/components/TimeLine/toolbar.vue` | Timeline toolbar; fork adds the `CopyAllForward` button ("Copy All to Next Frame (Alt+Shift+→)") |
| `src/components/Editor/main.vue` | Main editor layout; fork shows TimeLine when `state.isSeriesFrame \|\| state.frames.length > 1` |
| `src/packages/pc-editor/common/DataManager.ts` | Frame data manager; fork adds `copyAllForward()` calling `track({direction:'FORWARD', object:'all', method:'copy', frameN:1})` |
| `src/packages/pc-editor/common/ActionManager/action/general.ts` | Action definitions; fork adds `copyAllForward` and relaxes `copyForward`/`copyBackWard` validity to multi-frame data |
| `src/packages/pc-editor/config/hotkey.ts` | Hotkey map; fork adds `alt+shift+right → copyAllForward` |
| `src/packages/pc-editor/state.ts` | Editor `IState`; fork adds `isMultiFrame: boolean` |
| `vite.config.ts` | Dev config; defines `pc-render`/`pc-editor` path aliases to `src/packages/*`; set the `/api` proxy target here |
| `vite.config.build.ts` | Production build: `base: '/tool/pc/'`, `outDir: '../dist/pc-tool'` |
| `docs/camera_config.md` | Camera parameter documentation |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/actions/` | Business actions (`flow.ts`, `index.ts`) registered via `registry.ts` |
| `src/api/` | Backend API clients (`base.ts`, `common.ts`, `flow.ts`, `model.ts`) |
| `src/common/` | Business-layer subclasses: `BusinessManager.ts`, `DataManager.ts`, `Editor.ts` |
| `src/components/` | Vue UI: `Editor`, `TimeLine`, `MainView`, `SideView`, `ImgView`, `Operation`, `Instance`, `EditClass`, `Header`, `Tool`, `Layout`, `Modal`, `Collapse`, `Common` |
| `src/config/` | Business config incl. `action.ts` |
| `src/hook/` | Composables: `useTool`, `useFlow`, `useData`, `useQuery`, `useToken`, `useUI`, `useLang`, `useContextMenu` |
| `src/lang/` | i18n strings (`en.ts`, `zh.ts`) |
| `src/packages/pc-editor/` | Editor framework (imported as `pc-editor`): ActionManager, DataManager, HotkeyManager, state, configs |
| `src/packages/pc-render/` | three.js rendering engine (imported as `pc-render`): renderView, points, materials, loaders, objects, actions |
| `src/pages/` | Page modes: `execute.ts` (annotate), `view.ts` (view-only) |
| `src/style/`, `src/utils/` | Less styles; shared utilities |

## For AI Agents
### Working In This Directory
- `pc-editor` and `pc-render` are vite aliases to `src/packages/*` (see `vite.config.ts`), not npm packages. Import from them by alias name.
- New user-triggered behavior follows the pattern: define action in `src/packages/pc-editor/common/ActionManager/action/general.ts`, list its name in `src/config/action.ts`, optionally bind a hotkey in `src/packages/pc-editor/config/hotkey.ts`, and wire UI in components (see the `copyAllForward` diff in commit `7473cb5` as the canonical example).
- Editor state lives in `src/packages/pc-editor/state.ts` (`IState` + `getDefaultState()`); extend both when adding flags.

### Testing Requirements
- No test scripts exist. Verify with:
  - `npm run dev` — vite dev server (the main app links to it at `http://localhost:3200/tool/pc` in dev)
  - `npm run build` — production build via `vite.config.build.ts` into `../dist/pc-tool`
- Set the `/api` dev proxy target in `vite.config.ts` before `npm run dev`.

### Common Patterns
- Action dispatch: UI components call `editor.actionManager` / `editor.dataManager` methods (e.g., `toolbar.vue` `onAction('CopyAllForward')` → `editor.dataManager.copyAllForward()`).
- Frame copy/track operations funnel through `DataManager.track({method, object, direction, frameN})`.
- Hotkeys via `hotkeys-js` config arrays in `pc-editor/config/hotkey.ts`.

## Dependencies
### Internal
- Launched from `frontend/main` (the platform UI) at path `/tool/pc` — see `frontend/main/src/utils/business/index.ts` (dev: `http://localhost:3200/tool/pc`).
- Built by `frontend/Dockerfile` into `dist/pc-tool` and served by nginx alongside `main`, `image-tool`, `text-tool`.
- `frontend/text-tool` is a derived copy of this codebase (shares `pc-editor`/`pc-render` and an identical `package.json`).

### External
- `three` ^0.136.0 (3D rendering), `vue` ^3.2.25, `ant-design-vue` 2.2.8, `vue-router` ^4, `vue-i18n` ^9, `hotkeys-js`, `@tweenjs/tween.js`, `interactjs`, `axios` ^0.26, `lodash`, `colord`, `vue3-colorpicker`. Build: `vite` ^2.8, `typescript` ^4.5, `@vitejs/plugin-vue`.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
