<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# text-tool

## Purpose
Text/LLM-conversation annotation tool of the Xtreme1 platform, built with Vue 3 + TypeScript + Vite. It is a **derived copy of `frontend/pc-tool`** adapted for text: its `package.json` is byte-identical to pc-tool's (still named `"pc-tool"`, still listing three.js) and its `README.md`/`docs/camera_config.md` are stale copies from pc-tool. The actual text functionality lives in DOM-rendered components — `src/components/Editor/text-main.vue` and `text-item.vue` render a list of `ITextItem` entries (prompter/answer roles) with thumbs-up/thumbs-down rating per item (`editor.dataManager.getTextItemsByFrame()` / `onTextChange(item, 'up'|'down'|'')`), plus `src/components/MainView/sub/TextLong.vue`. pc-tool's `TimeLine` and `Instance` components were removed; the `pc-editor`/`pc-render` packages are retained as the underlying editor framework.

## Key Files
| File | Description |
|------|-------------|
| `src/main.ts` | App entry: creates Vue app, registers Ant Design Vue + Vue3ColorPicker, mounts `App.vue` |
| `src/components/Editor/text-main.vue` | Text annotation main view: lists `ITextItem`s for the current frame, listens for `Event.ANNOTATE_LOADED` |
| `src/components/Editor/text-item.vue` | Single conversation item (role `prompter`/answer) with thumbs-up/down direction rating |
| `src/components/MainView/sub/TextLong.vue` | Long-text sub view (text-tool only) |
| `src/registry.ts` | Registers hotkeys and actions into the editor |
| `src/state.ts` | Business-level state |
| `src/packages/pc-editor/` | Editor framework (`ITextItem`, `Event`, DataManager with `getTextItemsByFrame`/`onTextChange`) — diverged from pc-tool's copy |
| `vite.config.ts` | Dev config with `pc-render`/`pc-editor` aliases; set `/api` proxy here |
| `vite.config.build.ts` | Production build: `base: '/tool/text/'`, `outDir: '../dist/text-tool'` |
| `README.md` | STALE — copied from pc-tool, still describes point-cloud annotation |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/actions/` | Business actions registered via `registry.ts` |
| `src/api/` | Backend API clients (`common.ts`, `model.ts`, `flow.ts`, `base.ts`) |
| `src/common/` | Business subclasses: `BusinessManager.ts`, `DataManager.ts`, `Editor.ts` |
| `src/components/` | Vue UI: `Editor` (incl. text-main/text-item), `MainView`, `SideView`, `ImgView`, `Operation`, `EditClass`, `Header`, `Tool`, `Layout`, `Modal`, `Collapse`, `Common` (no `TimeLine`/`Instance` — removed vs pc-tool) |
| `src/config/`, `src/hook/`, `src/lang/` | Action config, composables (`useTool`, `useFlow`, ...), i18n |
| `src/packages/pc-editor/` | Editor framework (aliased as `pc-editor`), extended with text-item APIs |
| `src/packages/pc-render/` | three.js render engine inherited from pc-tool (aliased as `pc-render`) |
| `src/pages/` | Page modes: `execute.ts`, `view.ts` |
| `src/assets/`, `src/style/`, `src/utils/` | Assets (incl. thumbs icons), styles, utilities |

## For AI Agents
### Working In This Directory
- Treat this as a pc-tool fork, not a fresh codebase: most files mirror `frontend/pc-tool` with text-specific divergence concentrated in `src/components/Editor/text-*.vue`, `src/components/MainView/sub/TextLong.vue`, `src/common/`, and `src/packages/pc-editor/`. When fixing shared bugs, check whether pc-tool needs the same fix (and vice versa) — the trees are NOT kept in sync automatically.
- `pc-editor`/`pc-render` are vite aliases to `src/packages/*`, not npm packages.
- Do not trust `README.md` or `docs/camera_config.md` here; they describe pc-tool.

### Testing Requirements
- No test scripts exist. Verify with:
  - `npm run dev` — vite dev server (the main app links to it at `http://localhost:3300/tool/text` in dev)
  - `npm run build` — production build into `../dist/text-tool`
- Set the `/api` dev proxy target in `vite.config.ts` before `npm run dev`.

### Common Patterns
- Text items flow through the editor's DataManager: `getTextItemsByFrame()` to read, `onTextChange(item, direction)` to record up/down ratings (see `text-main.vue`).
- Editor events via `editor.addEventListener(Event.ANNOTATE_LOADED, ...)` from `pc-editor`.
- Action/hotkey registration mirrors pc-tool (`registry.ts` + `src/config/action.ts` + `pc-editor/config/hotkey.ts`).

## Dependencies
### Internal
- Launched from `frontend/main` (the platform UI) at path `/tool/text` — see `frontend/main/src/utils/business/index.ts` (dev: `http://localhost:3300/tool/text`).
- Built by `frontend/Dockerfile` into `dist/text-tool` and served by nginx alongside the other tools.
- Code lineage: forked from `frontend/pc-tool` (shared `pc-editor`/`pc-render` packages, identical `package.json`).

### External
- `vue` ^3.2.25, `ant-design-vue` 2.2.8, `vue-i18n` ^9, `vue-router` ^4, `hotkeys-js`, `axios` ^0.26, `lodash`, `colord`, `vue3-colorpicker`; `three` ^0.136.0 and `@tweenjs/tween.js` remain in deps via the pc-tool lineage. Build: `vite` ^2.8, `typescript` ^4.5.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
