<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# frontend

## Purpose
Frontend of the Xtreme1 data labeling platform, composed of four independent Vue 3 + TypeScript + Vite single-page applications: `main` (the web platform: datasets, ontology, models, teams) and three annotation tools (`pc-tool` for point clouds, `image-tool` for images, `text-tool` for text). Each app is developed and built separately; their static builds are all emitted into a shared `frontend/dist/` directory and served by nginx under different paths (`main` at `/`, `pc-tool` at `/tool/pc`, `image-tool` at `/tool/image`, `text-tool` at `/tool/text`). The main app launches the annotation tools by navigating to those `/tool/*` URLs (see `main/src/utils/business/index.ts`, which builds tool paths and, in local dev, points at `http://localhost:3200/tool/pc` and `http://localhost:3300/tool/image|text`).

## Key Files
| File | Description |
|------|-------------|
| `README.md` | Overview of the four apps and the nginx path mapping for deployed builds |
| `Dockerfile` | Two-stage build: `node:16` runs `npm install && npm run build` in each of the four app dirs, then `nginx:1.22` serves the combined `dist/` |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `main/` | Main web platform (vben-admin-based): dataset management, ontology, models, team/user admin; launches the tools (see `main/AGENTS.md`) |
| `pc-tool/` | 3D point cloud annotation tool, three.js-based (see `pc-tool/AGENTS.md`) |
| `image-tool/` | Image annotation tool: Konva-based canvas editing, polygon clipping (see `image-tool/AGENTS.md`) |
| `text-tool/` | Text annotation tool, forked from pc-tool; its `package.json` name is still `"pc-tool"` (see `text-tool/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Treat each app as a separate project: each has its own `package.json`, `tsconfig.json`, `vite.config.ts`, and `prettier.config.js`. There is no root workspace/monorepo tooling at this level — `cd` into the specific app before installing or building.
- The three tool apps each have a second Vite config, `vite.config.build.ts`, used only by their `npm run build` script; `vite.config.ts` is for dev (where you configure the `/api` proxy target per each tool's README).
- The Dockerfile pins Node 16; `main/package.json` declares `engines.node: "^12 || >=14"`. Both `package-lock.json` and `yarn.lock` exist in `main/` (and `yarn.lock` in `image-tool/`, `text-tool/`), but the Docker build uses `npm install` — prefer npm for reproducing CI behavior.
- Tool versions diverge between apps (e.g. `ant-design-vue` 2.2.8 in main/pc-tool/text-tool vs 3.2.19 in image-tool; `three` 0.136 in pc-tool vs 0.142 in image-tool vs 0.147 in main). Do not assume a dependency change in one app applies to the others.

### Testing Requirements
- Only `main/` has a test setup (Jest, see `main/jest.config.mjs` and `main/tests/`); the tool apps have no test infrastructure.
- All four apps lint via ESLint + Prettier (`prettier.config.js` per app); `image-tool` exposes `npm run lint:eslint`.

### Common Patterns
- All apps: Vue 3 SFCs + TypeScript + Vite + Less + ant-design-vue + vue-router + vue-i18n.
- Builds output outside the app directory into `frontend/dist/<app>` (e.g. `main/build/constant.ts` sets `OUTPUT_DIR = '../dist/main'`); deployment routing is described in `README.md` and `.ops/**/frontend-deployment.yml`.
- Apps communicate with the backend through the same `/api` prefix, proxied in dev and routed by nginx in production.

## Dependencies

### Internal
- Backend REST API at `/api` (dev proxy targets `http://localhost:8190` in `main/.env.development`).
- `main` → tools: cross-app navigation only (URL handoff to `/tool/pc|image|text`), no shared code or package imports between the four apps.

### External
- Vue 3, Vite 2, TypeScript, ant-design-vue, vue-router 4, vue-i18n 9 (all apps); three.js (pc-tool, text-tool, main), Konva (image-tool), Pinia (main only).

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
