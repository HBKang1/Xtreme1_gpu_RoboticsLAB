<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# frontend/main

## Purpose
The main Xtreme1 web platform: a Vue 3 + TypeScript + Vite 2 SPA forked from [vue-vben-admin](https://github.com/anncwb/vue-vben-admin) (the `repository` field in `package.json` still points there). It provides dataset management (list/detail/content/class/ontology/overview/search under `src/views/datasets/`), ontology management, model management, team/user administration, profile, recents, and claim flows, and launches the annotation tools by navigating to `/tool/pc`, `/tool/image`, `/tool/text` (`src/utils/business/index.ts`). UI is ant-design-vue 2.2.8 plus WindiCSS; state is Pinia 2; deployed build is served by nginx at `/`.

## Key Files
| File | Description |
|------|-------------|
| `package.json` | Name `x1`; scripts: `dev` (vite), `dev:local` (`vite --mode localDev`), `test` (`vite --mode test` — starts dev server in test mode, does NOT run Jest), `build` (vite build + `esno ./build/script/postBuild.ts`), `type:check` (`vue-tsc --noEmit --skipLibCheck`), `preview`, `clean:cache`, `clean:lib`; `engines.node: "^12 || >=14"` |
| `vite.config.ts` | Path aliases (`/@/` → `src/`, `/#/` → `types/`, `/@@/` → `src/components/BasicCustom/`), dev proxy from `VITE_PROXY` env, Less `modifyVars`, plugins delegated to `build/vite/plugin/` |
| `src/main.ts` | App bootstrap: design Less + WindiCSS virtual imports, svg-icons register, store/router/guards/i18n/directives setup; registers V3ColorPicker, vue3-lazyload, vue3-json-viewer |
| `.env` / `.env.development` / `.env.production` / `.env.test` | `VITE_PORT = 3100`, `VITE_GLOB_API_URL=/api`, dev proxy `/api` and `/upload` → `http://localhost:8190` |
| `jest.config.mjs` | ts-jest preset, jsdom, roots `tests/`, maps `/@/` alias to `src/` |
| `windi.config.ts` | WindiCSS configuration |
| `index.html` | SPA entry HTML (processed by vite-plugin-html) |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `src/api/` | API layer: `business/` (dataset.ts, ontology.ts, class.ts/classes.ts, models.ts, team.ts, task.ts, role.ts, group.ts, claim.ts, api.ts, plus `dataset/` and `model/`), `sys/` (user.ts, menu.ts, upload.ts), `model/` types, `demo/` (vben leftovers) |
| `src/views/` | Page components: `datasets/`, `ontology/`, `models/`, `team/`, `profile/`, `recents/`, `claim/`, `texttool/`, `sys/` |
| `src/router/` | vue-router 4 setup: `routes/modules/` (dataset.ts, ontology.ts, models.ts, team.ts, profile.ts, recents.ts, claim.ts, api.ts, biling.ts), `guard/` (route guards), `menus/`, `helper/` |
| `src/store/` | Pinia: `index.ts` creates the pinia instance; `modules/` has app, user, permission, locale, lock, multipleTab, errorLog stores |
| `src/components/` | Large vben component library (Basic, Form, Table, Modal, Drawer, Tree, Upload, Icon, ...) plus project-specific `BasicCustom/` (aliased as `/@@/`) |
| `src/locales/` | vue-i18n 9 setup (`setupI18n.ts`, `useLocale.ts`); `lang/en/`, `lang/zh-CN/` message files |
| `src/utils/` | `http/axios/` (exports `defHttp`, the axios wrapper used by all of `src/api/`), `business/` (tool-launch URL building), `auth/`, `cache/`, helpers |
| `src/layouts/`, `src/logics/`, `src/directives/`, `src/hooks/`, `src/enums/`, `src/settings/`, `src/design/`, `src/assets/` | vben app scaffolding: layouts, app-init logic (`initAppConfig`, error-handle), custom directives, composables, enums, app settings, global Less |
| `build/` | Build tooling: `constant.ts` (`OUTPUT_DIR = '../dist/main'`, `GLOB_CONFIG_FILE_NAME = '_app.config.js'`), `vite/` (plugin/, proxy.ts, optimizer.ts), `script/postBuild.ts` (runs after vite build), `generate/` (Less modifyVars) |
| `mock/` | vite-plugin-mock data (`sys/`, `demo/`, `_createProductionServer.ts`); enabled via `VITE_USE_MOCK` (false in checked-in `.env.development`) |
| `tests/` | Jest specs (`test.spec.ts`), `__mocks__/` (file/style/worker stubs), `server/` (excluded from test runs) |
| `types/` | Ambient TS declarations (global.d.ts, config.d.ts, store.d.ts, axios.d.ts, vue-router.d.ts), aliased as `/#/` |
| `public/` | Static assets (`favicon.ico`, `resource/`) copied verbatim to the build |

## For AI Agents

### Working In This Directory
- Always use the path aliases in imports: `/@/...` for `src/`, `/#/...` for `types/`, `/@@/...` for `src/components/BasicCustom/` (defined in `vite.config.ts` and mirrored in `jest.config.mjs` only for `/@/`).
- All HTTP calls go through `defHttp` from `/@/utils/http/axios` — follow the existing pattern in `src/api/business/dataset.ts` (typed params/result models imported from `src/api/business/model/` or sibling model files).
- New pages need three touches: a view under `src/views/`, a route module under `src/router/routes/modules/`, and locale entries under `src/locales/lang/{en,zh-CN}/`.
- Dev server runs on port 3100 (`.env`); backend proxy targets `http://localhost:8190` (`.env.development`). Launching tools from dev expects pc-tool on 3200 and image/text-tool on 3300 (`src/utils/business/index.ts`).
- `npm run build` needs significant memory (`--max_old_space_size=16384` is hard-coded) and emits to `../dist/main`, then runs `build/script/postBuild.ts` (generates the runtime `_app.config.js`).
- Much of `src/components/`, `mock/demo/`, and `src/api/demo/` is inherited vben-admin scaffolding; project-specific code concentrates in `src/views/`, `src/api/business/`, `src/utils/business/`, and `src/components/BasicCustom/`.

### Testing Requirements
- Jest is configured in `jest.config.mjs` (ts-jest, jsdom, tests under `tests/`), but there is no npm script wired to it — `npm run test` starts Vite in `test` mode instead. Run unit tests with `npx jest`.
- Type-check with `npm run type:check` (`vue-tsc --noEmit --skipLibCheck`) before claiming a change builds.
- Lint/format via ESLint + Prettier (`prettier.config.js`) and stylelint (`stylelint.config.js`) configs at the app root.

### Common Patterns
- Pinia stores in `src/store/modules/` follow vben conventions (e.g. `user.ts`, `permission.ts` drive auth and route filtering through `src/router/guard/`).
- Styling: Less with theme variables injected via `build/generate/generateModifyVars` plus WindiCSS utility classes; ant-design-vue Less is imported whole only in dev (`src/main.ts`).
- Environment config is read through `build/utils.ts` `wrapperEnv` (converts string env values to typed values); runtime-configurable globals use the `VITE_GLOB_*` prefix and are emitted into `_app.config.js` at build time.

## Dependencies

### Internal
- Backend REST API under `/api` (proxied in dev, nginx-routed in prod); file upload endpoint `VITE_GLOB_UPLOAD_URL=/api/storage/storage/uploadFile`.
- Sibling tool apps via URL navigation only (`/tool/pc`, `/tool/image`, `/tool/text`); no code sharing.

### External
- Runtime: vue ^3.2.21, vue-router ^4.0.12, pinia 2.0.0, vue-i18n ^9.1.9, ant-design-vue 2.2.8, axios ^0.24.0, echarts, @antv/g2plot, three ^0.147.0, aws-sdk, lodash-es, dayjs/moment, mockjs.
- Build/dev: vite ^2.6.13, typescript ^4.4.4, vue-tsc, esno, less, windicss (vite-plugin-windicss), vite-plugin-mock, vite-plugin-svg-icons, vite-plugin-theme, jest ^27 + ts-jest, eslint + prettier + stylelint.

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->

## Manual Notes (2026-06-11)

### Dataset content list (frame grid) & infinite scroll
- Page: `src/views/datasets/datasetContent/index.vue` — `fetchList()` posts to `/data/findByPage` via `datasetApi` (`src/api/business/dataset.ts`) with `pageSize: 64` (raised from 16 on 2026-06-11 for scroll speed), then a second `datasetObjectApi` call per batch for annotation objects, plus `fetchStatusNum()`.
- Scroll loading: shared util `src/utils/business/scrollListener.ts handleScroll()` — triggers `loadMore()` 150 ms after scroll when within 400 px of the bottom (was 500 ms / 50 px). Also used by dataset list, ontology, and model list pages, so changes there affect all infinite-scroll pages.
- Thumbnails are pre-generated at upload (MinIO; point clouds get a backend-rendered image) and lazy-loaded via `v-lazyload` — they don't block list loading.
- Known remaining bottleneck: backend `DataInfoUseCase.findByPage` runs per-item queries (locked-user info, scene first-data) — N+1 pattern.
