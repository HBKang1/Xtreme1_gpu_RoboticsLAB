<!-- Generated: 2026-06-10 | Updated: 2026-06-10 -->

# Xtreme1 (GPU / Robotics Lab Fork)

## Purpose
Fork of [Xtreme1](https://github.com/xtreme1-io/xtreme1) v0.9.1, the open-source data labeling platform for multisensory AI training data (image, point cloud, and text annotation with model-assisted labeling), customized for a university Robotics Lab. Fork-specific changes: (1) the `point-cloud-object-detection` model service is replaced with a custom CUDA-upgraded image (`kanghanbin/my-custom-xtreme1:v5`, upgraded from CUDA 10.2 to CUDA 11.3 so AI annotation runs on newer GPUs) running an OpenPCDet CenterPoint checkpoint (`cbgs_voxel0075_centerpoint_nds_6648.pth`) with `runtime: nvidia` and 8 GB shared memory; (2) a local lab dataset (`/home/a/dataset_custom/zenix_dataset/dataset_0124`) is bind-mounted into the backend at `/app/data/zenix_snow`; (3) multi-frame copy support was added to the point cloud tool (`frontend/pc-tool` TimeLine toolbar, ActionManager, DataManager, hotkeys — commit 7473cb5). The detailed CUDA 10.2→11.3 upgrade walkthrough formerly lived in `README.md` but was emptied in commit c6995aa; recover it via `git show 6d7927c:README.md` if needed.

## Key Files
| File | Description |
|------|-------------|
| `docker-compose.yml` | Defines the full stack: nginx (entry, host port 8190), mysql 5.7 (8191), redis 6.2 (8192), minio (8193/8194), backend (8290, image `basicai/xtreme1-backend:v0.9.1` + lab dataset bind mount), frontend (8291, built locally from `./frontend`), pcd-tools (8295), image-vect-visualization (8294), plus GPU model services under the `model` profile: image-object-detection (8292) and the custom point-cloud-object-detection (8293) |
| `README.md` | Currently empty; previously held the CUDA 10.2→11.3 model-container upgrade guide (deleted in commit c6995aa, recoverable from git history) |
| `LICENSE.txt` | Apache License 2.0 |
| `CONTRIBUTING.md` | Upstream contribution guide; describes the Frontend (TypeScript/Vue) + Backend (Java) split and upstream PR workflow |
| `SECURITY.md` | Linux Foundation vulnerability reporting policy (upstream) |
| `CODE_OF_CONDUCT.md` | Linux Foundation code of conduct (upstream) |
| `.gitignore` | Ignores `target/`, `dist/`, `node_modules/`, `docker-compose.override.yml`, local app configs, and IDE files |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `backend/` | Java 11 / Spring Boot API service (Maven, MyBatis-Plus, Spring Security/Redis) using clean architecture (adapter/usecase/entity layers). See `backend/AGENTS.md` |
| `frontend/` | Four independent Vue 3 + TypeScript + Vite apps: `main` (web UI), `pc-tool` (point cloud annotation — fork's multi-frame copy lives here), `image-tool`, `text-tool`; assembled into one nginx image by `frontend/Dockerfile`. See `frontend/AGENTS.md` |
| `deploy/` | Runtime config mounted by docker-compose: `nginx/conf.d/default.conf` reverse proxy and `mysql/` (custom.cnf, schema migration SQL run at first DB init). See `deploy/AGENTS.md` |
| `docs/` | Backend docs and images (includes clean-architecture diagram referenced by `backend/README.md`). See `docs/AGENTS.md` |
| `.github/` | Issue templates and `workflows/main.yml` (mirrors the upstream repo to BasicAI GitLab; not relevant to this fork) |
| `.ops/` | BasicAI-internal CI/CD Dockerfiles and image push scripts; upstream README explicitly says contributors should not touch this |

## For AI Agents

### Working In This Directory
- The system is composed entirely via `docker-compose.yml`. nginx (port 8190) is the single user entry point, proxying to `frontend` and `backend`. Backend depends on healthy `mysql`, `redis`, and `minio` (object storage, bucket `xtreme1`); nginx waits on a healthy backend.
- The backend runs from the prebuilt Docker Hub image `basicai/xtreme1-backend:v0.9.1` (`pull_policy: always`) — local edits to `backend/` have no effect unless you switch the service to `build: ./backend` (commented toggle is in the compose file). The frontend is the opposite: it already uses `build: ./frontend`, so frontend changes take effect on `docker compose build frontend`.
- GPU model services (`image-object-detection`, `point-cloud-object-detection`) only start with `--profile model` and require the NVIDIA container runtime. The point cloud model service is fork-customized: image `kanghanbin/my-custom-xtreme1:v5`, `working_dir: /app/pcdet_open`, entrypoint `python app.py ../cbgs_voxel0075_centerpoint_nds_6648.pth`. Do not revert it to the upstream `basicai/xtreme1-point-cloud-object-detection` image — that one is CUDA 10.2 and fails on the lab's GPUs.
- The backend volume mount `/home/a/dataset_custom/zenix_dataset/dataset_0124:/app/data/zenix_snow` is machine-specific lab data; preserve it when editing the compose file.
- Frontend annotation-tool behavior changes (e.g., the multi-frame copy feature) go in `frontend/pc-tool/src/`, particularly `packages/pc-editor/` (DataManager, ActionManager, hotkey config, state) and `components/TimeLine/`.
- DB schema changes go in `deploy/mysql/migration/` (executed by the mysql container's `docker-entrypoint-initdb.d` on first init only). Routing changes go in `deploy/nginx/conf.d/default.conf`.

### Testing Requirements
- Full stack: `docker compose up` from the repo root; with GPU model services: `docker compose --profile model up`. Verify at `http://localhost:8190` (backend health: `http://localhost:8290/actuator/health`).
- Frontend: each app under `frontend/` builds independently with `npm install && npm run build` (Node 16 per `frontend/Dockerfile`); rebuild the image with `docker compose build frontend`.
- Backend: `mvn package` (Maven 3.8, JDK 11 per `backend/Dockerfile`); no separate test suite is documented in this repo.
- No CI runs tests — `.github/workflows/main.yml` only mirrors to GitLab.

### Common Patterns
- Service config is overridden via compose volume mounts rather than image rebuilds (e.g., commented `application.yml` override hook on the backend service, nginx/mysql config mounts from `deploy/`).
- Compose healthchecks + `depends_on: condition: service_healthy` enforce startup order (mysql/redis/minio → backend → nginx).
- Fork commits include Korean inline comments in `docker-compose.yml` (e.g., on the custom model image line); the four-commit history (`git log --oneline`) is the authoritative record of what diverges from upstream v0.9.1.
- Backend follows clean architecture (adapter → usecase → entity, dependencies point inward only); frontend apps share the Vue 3 + TS + Vite stack with per-tool `packages/` editors.

## Dependencies
### External
- **MySQL 5.7** — primary datastore (DB `xtreme1`, init SQL from `deploy/mysql/migration`), host port 8191
- **Redis 6.2** — cache (Spring Data Redis), host port 8192
- **MinIO** (`bitnamilegacy/minio:2022.9.1`) — S3-compatible object storage for datasets/exports, buckets `xtreme1:download`, ports 8193 (API) / 8194 (console)
- **nginx 1.22** — reverse proxy entry point on port 8190 (config from `deploy/nginx/conf.d/default.conf`)
- **basicai/xtreme1-pcd-tools** — point cloud processing helper service, port 8295
- **basicai/xtreme1-image-vect-visualization** — image vector visualization service, port 8294
- **basicai/xtreme1-image-object-detection** — GPU image model service (`model` profile, nvidia runtime), port 8292
- **kanghanbin/my-custom-xtreme1:v5** — fork's CUDA 11.3 point cloud detection service (OpenPCDet CenterPoint, `model` profile, nvidia runtime, 8 GB shm), port 8293
- **NVIDIA container runtime** — required on the host for the `model` profile services
- **xtreme1-sdk** (pinned commit `6b53a73`) — installed into the backend image by `backend/Dockerfile`

<!-- MANUAL: Any manually added notes below this line are preserved on regeneration -->
